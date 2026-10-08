"""Specifier resolution and materialization pipeline.

Dispatch order (design §6): path -> file-archive -> archive -> manifest ->
github (incl. ``name`` looked up in the known table).
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from .errors import ResolveScriptError
from .fetch import fetch, sha256_file
from .manifest.json_reader import load_manifest
from .semver import SemVerError, Version
from .sources import known, unpack_archive
from .sources.git import download_github
from .sources.release import ReleaseSpec, asset_download_url
from .spec import Spec, SpecError, parse_specifier

# Cache filenames may only be a single safe path segment; anything else
# (path separators, traversal like "..", URL-encoded bytes) is scrubbed.
_UNSAFE_SLUG_CHARS = re.compile(r"[^A-Za-z0-9._-]")

logger = logging.getLogger(__name__)


class ResolveError(ResolveScriptError, RuntimeError):
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


def _spec_location(spec: Spec) -> Path:
    """Return the local path for path/file-archive specs (narrowed access)."""
    if spec.location is None:
        raise ResolveError(f"{spec.source}: specifier carries no local path")
    return spec.location


def resolve_spec(
    spec_text: str,
    *,
    cwd: Path | None = None,
    work_dir: Path,
) -> Resolved:
    """Resolve a specifier to a concrete, unpacked package directory."""
    cwd = cwd or Path.cwd()
    spec = parse_specifier(spec_text, cwd=cwd)
    logger.debug("resolving %r -> kind=%s source=%s", spec_text, spec.kind, spec.source)

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
        package_dir = _require_package_root(_spec_location(spec))
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
        location = _spec_location(spec)
        unzip_dir = work_dir / "unpacked"
        package_dir = unpack_archive(location, unzip_dir)
        package_dir = _require_package_root(package_dir)
        manifest = _manifest(package_dir)
        return Resolved(
            name=manifest.name,
            version=manifest.version,
            kind="archive",
            package_dir=package_dir,
            source=spec.source,
            integrity=sha256_file(location),
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
        if not url.lower().startswith("https://"):
            raise ResolveError(
                f"refusing to download executable package over plaintext http: {url}"
            )
        archive = work_dir / "cache" / _slug(url)
        if archive.is_file():
            logger.debug("cache hit %s", archive)
        else:
            logger.info("downloading %s", url)
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
    """Return a safe cache-filename fragment derived from ``url``.

    The tail segment is URL-decoded and stripped to ``[A-Za-z0-9._-]`` only
    so path separators (``/`` or ``\\``) and traversal (``..``) can never
    escape the cache directory.  Falls back to a content-based hash when the
    tail is empty or entirely stripped.
    """
    import hashlib

    if "/" in url:
        tail = unquote(url.rsplit("/", 1)[-1])
        if tail and tail not in (".", ".."):
            cleaned = _UNSAFE_SLUG_CHARS.sub("_", tail)
            if cleaned and ".." not in cleaned.split("_"):
                return cleaned
    return hashlib.sha256(url.encode()).hexdigest()[:16] + ".tgz"


def _asset_url(spec: Spec) -> str:
    url = spec.url
    if url is None:
        raise ResolveError(f"{spec.source}: specifier carries no URL")
    if spec.kind == "archive":
        return url
    # manifest URL: fetch the manifest, then follow release info
    with tempfile.TemporaryDirectory() as tmp:
        payload = Path(tmp) / "manifest.json"
        try:
            if not url.lower().startswith("https://"):
                raise ResolveError(
                    f"refusing to fetch package manifest over plaintext http: {url}"
                )
            fetch(url=url, dest=payload)
        except Exception as exc:
            raise ResolveError(f"failed to fetch manifest {url}: {exc}") from exc
        try:
            data = json.loads(payload.read_text("utf-8"))
        except json.JSONDecodeError as exc:
            raise ResolveError(f"{url} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ResolveError(f"{url} is not an object")
    name = data.get("name") or "extension"
    version = data.get("version") or "0.1.0"
    release = data.get("release")
    if not isinstance(release, dict):
        raise ResolveError(f"manifest at {url} has no 'release' entry")
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
