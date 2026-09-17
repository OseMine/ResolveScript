"""tar.gz / zip unpacking with a single-top-level-dir strip and path safety."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path


class ArchiveError(RuntimeError):
    pass


ARCHIVE_SUFFIXES = (".tgz", ".tar.gz", ".zip")


def is_archive_path(path: str | Path) -> bool:
    text = str(path).lower()
    return (
        text.endswith(".tar.gz")
        or text.endswith(".tgz")
        or text.endswith(".zip")
    )


def _safe_members(names: list[str]) -> None:
    for name in names:
        if name.startswith(("/", "\\")) or ".." in Path(name).parts:
            raise ArchiveError(f"archive contains unsafe path: {name!r}")


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _validate_tar_links(members: list[tarfile.TarInfo], dest_dir: Path) -> None:
    """Reject absolute / escaping symlink and hard link targets (tar-slip).

    Must run BEFORE ``extractall`` so hostile links can never be written.
    """
    resolved = dest_dir.resolve()
    for member in members:
        if not (member.issym() or member.islnk()):
            continue
        target = member.linkname
        if Path(target).is_absolute():
            raise ArchiveError(
                f"tar link has absolute target: {member.name!r} -> {target!r}"
            )
        if member.issym():
            link_target = (resolved / member.name).parent / target
        else:
            link_target = resolved / target
        if not _is_within(resolved, link_target):
            raise ArchiveError(
                f"tar link escapes destination: {member.name!r} -> {target!r}"
            )


def _validate_zip_members(zf: zipfile.ZipFile, dest_dir: Path) -> None:
    """Reject absolute / escaping paths and symlink targets (zip-slip).

    Must run BEFORE ``extractall`` so hostile links can never be written.
    """
    resolved = dest_dir.resolve()
    for info in zf.infolist():
        name = info.filename
        if not _is_within(resolved, resolved / Path(name)):
            raise ArchiveError(f"zip member escapes destination: {name!r}")
    for info in zf.infolist():
        mode = (info.external_attr >> 16) & 0xFFFF
        if (mode & 0xF000) != 0xA000:  # not a symlink entry
            continue
        link_target = zf.read(info).decode("utf-8", errors="replace")
        if Path(link_target).is_absolute():
            raise ArchiveError(
                f"zip symlink has absolute target: "
                f"{info.filename!r} -> {link_target!r}"
            )
        target_path = (resolved / Path(info.filename)).parent / link_target
        if not _is_within(resolved, target_path):
            raise ArchiveError(
                f"zip symlink escapes destination: "
                f"{info.filename!r} -> {link_target!r}"
            )


def _validate_extracted_paths(dest_dir: Path, names: list[str]) -> None:
    """Ensure every extracted member resolves inside ``dest_dir`` after
    ``extractall`` – protects against zip‑slip via resolved symlinks or
    case‑insensitive ``..`` that survived the name check."""
    resolved = dest_dir.resolve()
    for name in names:
        target = (resolved / Path(name)).resolve()
        if not _is_within(resolved, target):
            raise ArchiveError(
                f"archive member escapes destination: {name!r} -> {target}"
            )


def _find_root(candidates: list[str]) -> str:
    """Return the single root layer, or "" if files sit at the archive root."""
    roots = sorted({parts[0] for parts in (Path(c).parts for c in candidates) if parts})
    if len(roots) != 1:
        return ""
    root = roots[0]
    for name in candidates:
        if Path(name).parts[0] != root:
            return ""
    return root


def unpack_archive(archive: Path, dest_dir: Path) -> Path:
    """Extract ``archive`` under ``dest_dir`` and return the package root.

    The package root is the directory (archive root or the single stripped
    top-level dir) that contains ``manifest.json``.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        if str(archive).lower().endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
                _safe_members(names)
                _validate_zip_members(zf, dest_dir)
                zf.extractall(dest_dir)
                _validate_extracted_paths(dest_dir, names)
        else:
            with tarfile.open(archive, "r:*") as tf:
                names = tf.getnames()
                members = tf.getmembers()
                _safe_members(names)
                _validate_tar_links(members, dest_dir)
                if sys.version_info >= (3, 12):
                    tf.extractall(dest_dir, filter="data")
                else:
                    tf.extractall(dest_dir)
                _validate_extracted_paths(dest_dir, names)
    except (tarfile.TarError, zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError(f"failed to unpack {archive}: {exc}") from exc

    if (dest_dir / "manifest.json").is_file():
        return dest_dir
    root = _find_root(names)
    package_root = dest_dir / root if root else dest_dir
    if not (package_root / "manifest.json").is_file():
        raise ArchiveError(
            f"{archive} does not contain a package: no manifest.json "
            "(expected at the archive root or under a single top-level dir)"
        )
    return package_root


def make_archive(package_root: Path, dest: Path) -> Path:
    """Create ``dest`` (tar.gz) from a package dir (used by tests / packaging)."""
    dest = dest.with_suffix(".tar.gz") if not dest.suffix else dest
    with tarfile.open(dest, "w:gz") as tf:
        tf.add(package_root, arcname=package_root.name)
    return dest
