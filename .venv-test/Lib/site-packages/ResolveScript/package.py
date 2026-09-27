"""Packaging an extension into a release artifact (M7).

Produces a ``<name>-<version>.tgz`` in the exact shape ``add``/``install <spec>``
consumes: single top-level layer with ``manifest.json``, entry ``<name>.py`` and
the ``<name>/`` package directory (no wrapper folder). A ``SHA256SUMS.txt`` is
written alongside the archive.
"""

from __future__ import annotations

import hashlib
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from .install.installer import select_files
from .manifest.model import Manifest
from .manifest.validation import validate_manifest


class PackageError(RuntimeError):
    pass


@dataclass
class PackageResult:
    archive: Path
    sha256: str
    files: list[str] = field(default_factory=list)
    checksum_file: Path | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_file(root: Path, manifest: Manifest) -> Path | None:
    if manifest.entrypoint:
        candidate = root / manifest.entrypoint
        if candidate.is_file():
            return candidate
    direct = root / f"{manifest.name}.py"
    return direct if direct.is_file() else None


def package_project(root: Path | str, dist_dir: Path | None = None) -> PackageResult:
    root = Path(root).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        manifest_path = root / "manifest.xml"
        if not manifest_path.is_file():
            raise PackageError(
                f"no manifest.json or manifest.xml in {root} (run 'resolvescript create')"
            )
    if manifest_path.suffix == ".xml":
        from .manifest.xml_reader import load_manifest

        manifest = load_manifest(manifest_path)
    else:
        from .manifest.json_reader import load_manifest

        manifest = load_manifest(manifest_path)
    errors = validate_manifest(manifest)
    if errors:
        raise PackageError(errors[0])

    dist_dir = (dist_dir or root / "dist").resolve()
    dist_dir.mkdir(parents=True, exist_ok=True)

    include = list(manifest.install.include) if manifest.install.include else ["*.py", "manifest.json"]
    rel_files = select_files(root, include, manifest.install.exclude)

    entry = _entry_file(root, manifest)
    if entry is not None:
        entry_rel = entry.relative_to(root).as_posix()
        if not any(r.as_posix() == entry_rel for r in rel_files):
            rel_files.append(entry.relative_to(root))

    manifest_rel = manifest_path.relative_to(root).as_posix()
    if not any(r.as_posix() == manifest_rel for r in rel_files):
        rel_files.append(manifest_path.relative_to(root))

    archive_name = f"{manifest.name}-{manifest.version}.tar.gz"
    archive = dist_dir / archive_name
    with tarfile.open(archive, "w:gz") as tf:
        for rel in sorted(set(rel_files), key=lambda p: p.as_posix()):
            arcname = rel.as_posix()
            tf.add(root / rel, arcname=arcname)

    sha = _sha256(archive)
    checksum_file = dist_dir / "SHA256SUMS.txt"
    checksum_file.write_text(f"{sha}  {archive_name}\n", encoding="utf-8")

    return PackageResult(
        archive=archive,
        sha256=sha,
        files=sorted({r.as_posix() for r in rel_files}),
        checksum_file=checksum_file,
    )
