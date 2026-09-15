"""Specifier resolution and materialization pipeline.

Dispatch order (design §6): path -> file-archive -> archive -> manifest ->
github (incl. ``name`` looked up in the known table).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .fetch import fetch, sha256_file
from .manifest.json_reader import load_manifest
from .semver import SemVerError, Version
from .sources import known, unpack_archive
from .sources.git import download_github
from .sources.release import ReleaseSpec, asset_download_url
from .spec import Spec, SpecError, parse_specifier


class ResolveError(RuntimeError):
    pass


@dataclass
class Resolved:
    name: str
    version: str
    kind: str
    package_dir: Path
    source: str
    integrity: str
    manifest: object

    def describe(self) -> str:
        if self.integrity:
            return f"resolved {self.name} {self.version} ({self.kind}, {self.integrity[:12]})"
        return f"resolved {self.name} {self.version} ({self.kind})"


def _manifest(directory: Path):
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ResolveError(f"{directory} is not an extension: missing manifest.json")
    return load_manifest(manifest_path)


def _require_package_root(package_dir: Path) -> Path:
    if not (package_dir / "manifest.json").is_file():
        raise ResolveError(f"{package_dir} has no manifest.json")
    return package_dir


def resolve_spec(
    spec_text: str,
    *,
    cwd: Path | None = None,
    work_dir: Path,
) -> Resolved:
    """Resolve a specifier to a concrete, unpacked package directory."""
    cwd = cwd or Path.cwd()
    spec = parse_specifier(spec_text, cwd=cwd)

    if spec.kind == "name":
        entry = known.lookup(spec.source)
        if not entry:
            raise ResolveError(
                f"unknown extension {spec.source!r} - use a github:owner/repo, "
                "a URL, or an archive/path"
            )
        spec = parse_specifier(entry["source"], cwd=cwd)

    # -- path source -------------------------------------------------------
    if spec.kind == "path":
        package_dir = _require_package_root(spec.location)
        manifest = _manifest(package_dir)
        return Resolved(
            name=manifest.name,
            version=manifest.version,
            kind="path",
            package_dir=package_dir,
            source=spec.source,
            integrity="",
            manifest=manifest,
        )

    # -- local archive -----------------------------------------------------
    if spec.kind == "file-archive":
        unzip_dir = work_dir / "unpacked"
        package_dir = unpack_archive(spec.location, unzip_dir)
        package_dir = _require_package_root(package_dir)
        manifest = _manifest(package_dir)
        return Resolved(
            name=manifest.name,
            version=manifest.version,
            kind="archive",
            package_dir=package_dir,
            source=spec.source,
            integrity=sha256_file(spec.location),
            manifest=manifest,
        )

    # -- remote archive / manifest URL / github ---------------------------
    if spec.kind == "github":
        if not spec.owner or not spec.repo:
            raise ResolveError(f"invalid github spec: {spec.source}")
        package_dir, integrity = download_github(
            spec.owner,
            spec.repo,
            ref=spec.ref,
            range_text=spec.range_text,
            cache_dir=work_dir / "cache",
        )
        package_dir = _require_package_root(package_dir)
        manifest = _manifest(package_dir)
        return Resolved(
            name=manifest.name,
            version=manifest.version,
            kind="github",
            package_dir=package_dir,
            source=spec.source,
            integrity=integrity,
            manifest=manifest,
        )

    if spec.kind in ("archive", "manifest"):
        url = _asset_url(spec)
        archive = work_dir / "cache" / _slug(url)
        if not archive.is_file():
            fetch(url=url, dest=archive)
        package_dir = unpack_archive(archive, work_dir / "unpacked")
        package_dir = _require_package_root(package_dir)
        manifest = _manifest(package_dir)
        return Resolved(
            name=manifest.name,
            version=manifest.version,
            kind="manifest" if spec.kind == "manifest" else "archive",
            package_dir=package_dir,
            source=spec.source,
            integrity=sha256_file(archive),
            manifest=manifest,
        )

    raise ResolveError(f"cannot resolve specifier {spec_text!r}")


def _slug(url: str) -> str:
    import hashlib

    if "/" in url:
        tail = url.rsplit("/", 1)[-1]
        if tail:
            return tail
    return hashlib.sha256(url.encode()).hexdigest()[:16] + ".tgz"


def _asset_url(spec: Spec) -> str:
    if spec.kind == "archive":
        return spec.url
    # manifest URL: fetch the manifest, then follow release info
    with tempfile.TemporaryDirectory() as tmp:
        payload = Path(tmp) / "manifest.json"
        try:
            fetch(url=spec.url, dest=payload)
        except Exception as exc:
            raise ResolveError(f"failed to fetch manifest {spec.url}: {exc}") from exc
        try:
            data = json.loads(payload.read_text("utf-8"))
        except json.JSONDecodeError as exc:
            raise ResolveError(f"{spec.url} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ResolveError(f"{spec.url} is not an object")
    name = data.get("name") or "extension"
    version = data.get("version") or "0.1.0"
    release = data.get("release")
    if not isinstance(release, dict):
        raise ResolveError(f"manifest at {spec.url} has no 'release' entry")
    try:
        return asset_download_url(ReleaseSpec.from_data(release), str(name), str(version))
    except Exception as exc:
        raise ResolveError(str(exc)) from exc


def lockfile_satisfies(entry: dict | None, spec_text: str, *, cwd: Path | None = None) -> bool:
    """§6.8 lockfile-wins: is the recorded entry good for the requested spec?"""
    if not entry:
        return False
    try:
        spec = parse_specifier(spec_text, cwd=cwd or Path.cwd())
    except SpecError:
        return False
    if entry.get("source") != spec.source:
        return False
    if not spec.range_text:
        return True
    try:
        version = Version.parse(str(entry["version"]))
    except (SemVerError, KeyError, ValueError):
        return False
    from .semver import matches

    return matches(version, spec.range_text)
