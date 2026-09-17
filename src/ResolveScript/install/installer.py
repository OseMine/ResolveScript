"""Atomic install of a Resolve script / extension into a Scripts root.

Design:

- Files are selected from the package tree via ``install.include`` /
  ``install.exclude`` patterns (default: everything except caches).
- A staging directory is built inside the destination's parent (same volume),
  the staged entry file is ``py_compile``-checked, and only then the tree is
  renamed into place. Any failure discards the stage — no partial installs.
- The registry is consulted before writing: if another extension already owns
  a destination file, the install is refused unless ``force`` is set.
"""

from __future__ import annotations

import hashlib
import py_compile
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..manifest.model import Manifest, ManifestError
from .registry import add_or_update_entry, get_extension, installed_at_now, read_registry


def _validate_name(name: str) -> str:
    """Return a safe name, raising InstallError if it contains path traversal."""
    if ".." in name:
        raise InstallError(f"invalid manifest name '{name}': path traversal not allowed")
    if name.startswith("/") or name.startswith("\\"):
        raise InstallError(f"invalid manifest name '{name}': absolute path not allowed")
    return name


def validate_registry_name(name: str) -> str:
    """Validate a name from the registry (extension name, key) for safe path use."""
    if not name:
        raise InstallError("registry name is empty")
    if ".." in name:
        raise InstallError(f"invalid registry name '{name}': path traversal not allowed")
    if name.startswith("/") or name.startswith("\\"):
        raise InstallError(f"invalid registry name '{name}': absolute path not allowed")
    # Only allow alphanumeric, hyphen, underscore, dot
    import re
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise InstallError(f"invalid registry name '{name}': contains invalid characters")
    return name


def validate_registry_relpath(rel: str) -> str:
    """Validate a relative file path from the registry for safe path use."""
    if not rel:
        raise InstallError("registry relative path is empty")
    # Normalize and check for path traversal
    p = Path(rel)
    if p.is_absolute():
        raise InstallError(f"registry path '{rel}' is absolute")
    # Check each part for traversal
    for part in p.parts:
        if part == "..":
            raise InstallError(f"registry path '{rel}' contains path traversal")
    return rel


class InstallError(Exception):
    pass


@dataclass
class InstallOptions:
    """Tunables for an install run."""

    scripts_root: Path
    targets: tuple[str, ...] = ()
    force: bool = False
    dry_run: bool = False
    source: str = "local"
    resolved: str = ""
    integrity: str = ""  # sha256 of the downloaded artifact (source verify)

    def __post_init__(self) -> None:
        self.scripts_root = Path(self.scripts_root)


@dataclass
class InstalledFile:
    rel: str  # path of the file relative to the extension's install container
    sha256: str
    size: int


@dataclass
class InstallResult:
    key: str
    name: str
    version: str
    targets: tuple[str, ...]
    files: list[InstalledFile]
    installed_at: str
    dry_run: bool = False
    container: Path | None = None

    def describe(self) -> list[str]:
        lines = [
            f"Installed {self.name} {self.version} -> {self.container}"
            if self.container
            else f"Would install {self.name} {self.version}",
            f"  targets: {', '.join(self.targets)}",
        ]
        for file in self.files:
            lines.append(f"  {file.rel}  ({file.size} bytes)")
        return lines


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Convert a ``**``-aware glob pattern to a full-path regex."""
    if not pattern:
        return re.compile(r"$^")
    if pattern == "**":
        return re.compile(r"^.+$")
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        inner = _glob_regex(prefix).pattern
        # strip the ^ and $ anchors from inner and append the recursive tail
        core = inner[1:-1] if inner.startswith("^") and inner.endswith("$") else inner
        return re.compile(f"^{core}(?:/.*)?$")
    parts = pattern.split("/")
    rx: list[str] = []
    for part in parts:
        if part == "**":
            rx.append("(?:[^/]+/)*")
        else:
            rx.append(part.replace("*", "[^/]*").replace("?", "[^/]"))
    return re.compile("^" + "".join(rx) + "$")


def _matches_any(patterns: list[str], rel: str) -> bool:
    return any(_glob_regex(p).match(rel) for p in patterns)


def select_files(package_dir: Path, include: list[str] | None = None, exclude: list[str] | None = None) -> list[Path]:
    """Return install files (relative to ``package_dir``) selected by include/exclude."""
    include = include or []
    exclude = exclude or []
    result: list[Path] = []
    for file in sorted(package_dir.rglob("*")):
        if not file.is_file():
            continue
        rel = file.relative_to(package_dir)
        if any(part in ("__pycache__", ".git", ".resolvescript") for part in rel.parts):
            continue
        rel_str = rel.as_posix()
        if include and not _matches_any(include, rel_str):
            continue
        if exclude and _matches_any(exclude, rel_str):
            continue
        result.append(rel)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_entrypoint(package_dir: Path, manifest: Manifest) -> Path | None:
    """Locate the runnable entry file, if any.

    Priority: ``manifest.entrypoint``, a root ``<name>.py`` script, or the
    consolidated ``dist/<consolidate.output>`` build.
    """
    if manifest.entrypoint:
        candidate = package_dir / manifest.entrypoint
        if not candidate.is_file():
            raise InstallError(f"manifest entrypoint not found: {candidate}")
        return candidate
    direct = package_dir / f"{manifest.name}.py"
    if direct.is_file():
        return direct
    if manifest.consolidate.output:
        candidate = package_dir / "dist" / manifest.consolidate.output
        if candidate.is_file():
            return candidate
    return None


def _compile_entry(staged_entry: Path) -> None:
    """Syntax-check the staged entry file; raises InstallError on failure.

    The bytecode is written outside the staging tree so it never ships.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="resolvescript-pycheck-") as tmp:
            py_compile.compile(
                str(staged_entry),
                cfile=str(Path(tmp) / "check.pyc"),
                doraise=True,
            )
    except py_compile.PyCompileError as exc:
        raise InstallError(f"entry file is not valid Python: {exc}") from exc


def _occupied_map(registry: dict[str, Any], scripts_root: Path):
    """Map ``(target, relative-path)`` → owning extension name."""

    occupied: dict[tuple[str, str], str] = {}
    for ext_name, entry in registry.get("extensions", {}).items():
        owner = entry.get("name") or ext_name
        for target in entry.get("targets", []):
            for rel in entry.get("files", []):
                occupied[(target, str(rel))] = owner
    return occupied


def install_package(
    package_dir: Path | str,
    manifest: Manifest,
    options: InstallOptions,
) -> InstallResult:
    """Install a materialized package dir (manifest + files) into a Scripts root."""
    from .discovery import target_dir

    package_dir = Path(package_dir).resolve()
    scripts_root = Path(options.scripts_root).resolve()
    targets = tuple(options.targets) or tuple(manifest.targets) or ("Comp",)
    as_directory = manifest.install.as_directory

    # Validate manifest.name prevents path traversal (critical)
    _validate_name(manifest.name)

    rel_files = select_files(package_dir, manifest.install.include, manifest.install.exclude)
    entrypoint = discover_entrypoint(package_dir, manifest)
    entry_rel = entrypoint.relative_to(package_dir).as_posix() if entrypoint is not None else None
    if entry_rel is not None and not any(r.as_posix() == entry_rel for r in rel_files):
        rel_files.append(Path(entry_rel))

    if not as_directory and entry_rel is None:
        raise InstallError(
            f"cannot install {manifest.name} as a single file: no entrypoint "
            "(set manifest 'entrypoint' or provide a <name>.py)"
        )

    # containers[target] = folder that will hold the installed files
    containers: dict[str, Path] = {}
    for target in targets:
        base = target_dir(scripts_root, target)
        containers[target] = base / manifest.name if as_directory else base

    # dest layout: for directory installs preserve relative structure; for
    # single-file installs install just the entrypoint under its basename
    layout: dict[str, str] = {r.as_posix(): r.as_posix() for r in rel_files}
    if not as_directory:
        assert entry_rel is not None
        layout = {entry_rel: Path(entry_rel).name}

    dest_entries: list[tuple[Path, Path, str]] = []  # (source, dest, target)
    for target in targets:
        container = containers[target]
        target_base_rel = target_dir(scripts_root, target)
        for rel, dest_rel in layout.items():
            src = package_dir / rel
            dest = container / dest_rel
            dest_entries.append((src, dest, target))
            assert dest.is_relative_to(target_base_rel), (dest, target_base_rel)

    registry = read_registry(scripts_root)
    occupied = _occupied_map(registry, scripts_root)
    if not options.force:
        for _src, dest, target in dest_entries:
            rel = dest.relative_to(target_dir(scripts_root, target)).as_posix()
            owner = occupied.get((target, rel))
            if owner is not None and owner != manifest.name:
                raise InstallError(
                    f"install would overwrite '{rel}' in '{target}' which is owned by "
                    f"'{owner}' (use --force to overwrite)"
                )

    if options.dry_run:
        seen: set[tuple[str, str]] = set()
        files: list[InstalledFile] = []
        for src, dest, target in dest_entries:
            rel = dest.relative_to(target_dir(scripts_root, target)).as_posix()
            if (target, rel) in seen:
                continue
            seen.add((target, rel))
            files.append(InstalledFile(rel, sha256="", size=src.stat().st_size))
        return InstallResult(
            key=manifest.id or manifest.name,
            name=manifest.name,
            version=manifest.version,
            targets=targets,
            files=files,
            installed_at=installed_at_now(),
            dry_run=True,
            container=containers[targets[0]],
        )

    installed_files: list[InstalledFile] = []
    for target in targets:
        container = containers[target]
        container.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=".resolvescript-stage-", dir=str(container.parent))
        )
        try:
            for src, dest, entry_target in dest_entries:
                if entry_target != target:
                    continue
                staged = stage / dest.relative_to(container)
                staged.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, staged)
                installed_files.append(
                    InstalledFile(
                        rel=dest.relative_to(container).as_posix(),
                        sha256=_sha256(src),
                        size=src.stat().st_size,
                    )
                )
            if entry_rel is not None:
                staged_entry = stage / (
                    Path(entry_rel).name if not as_directory else Path(entry_rel)
                )
                _compile_entry(staged_entry)
            if as_directory:
                if container.exists():
                    shutil.rmtree(container)
                stage.replace(container)
            else:
                for staged_file in stage.rglob("*"):
                    if staged_file.is_file():
                        dest_file = container / staged_file.relative_to(stage)
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(staged_file, dest_file)
                shutil.rmtree(stage, ignore_errors=True)
        except InstallError:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        except OSError as exc:
            shutil.rmtree(stage, ignore_errors=True)
            raise InstallError(f"failed to install into {container}: {exc}") from exc

    entry_sha = _sha256(entrypoint) if entrypoint is not None else ""
    result = InstallResult(
        key=manifest.id or manifest.name,
        name=manifest.name,
        version=manifest.version,
        targets=targets,
        files=installed_files,
        installed_at=installed_at_now(),
        container=containers[targets[0]],
    )
    entry = {
        "id": manifest.id or manifest.name,
        "name": manifest.name,
        "version": manifest.version,
        "kind": manifest.kind,
        "as_directory": as_directory,
        "source": options.source
        if options.source != "local"
        else (manifest.release.github_spec or manifest.release.url or "local"),
        "resolved": options.resolved,
        "integrity": options.integrity or entry_sha,
        "files": sorted(
            {f"{manifest.name}/{f.rel}" if as_directory else f.rel for f in installed_files}
        ),
        "targets": list(targets),
        "compat": manifest.compat.as_dict(),
        "installed_at": result.installed_at,
    }
    if manifest.release.owner or manifest.release.repo or manifest.release.url:
        entry["release"] = manifest.release.as_dict()
    add_or_update_entry(scripts_root, result.key, entry)
    return result


def install_project(
    root: Path | str,
    options: InstallOptions,
    manifest: Manifest | None = None,
) -> InstallResult:
    """Author flow: install the project in ``root`` (``resolvescript install``)."""
    root = Path(root).resolve()
    if manifest is None:
        from ..manifest.json_reader import load_manifest

        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            from ..manifest.xml_reader import load_manifest as load_xml

            manifest_path = root / "manifest.xml"
            if not manifest_path.is_file():
                raise ManifestError(
                    f"no manifest.json or manifest.xml in {root} (run 'resolvescript create')"
                )
            manifest = load_xml(manifest_path)
        else:
            manifest = load_manifest(manifest_path)
    return install_package(root, manifest, options)


def uninstall_package(name: str, options: InstallOptions) -> list[str]:
    """Remove an extension's installed files via the registry; returns removed paths."""
    from .discovery import target_dir

    scripts_root = Path(options.scripts_root).resolve()
    registry = read_registry(scripts_root)
    entry = get_extension(registry, name)
    if entry is None:
        raise InstallError(f"'{name}' is not installed in {scripts_root}")

    removed: list[str] = []
    as_directory = bool(entry.get("as_directory", True))
    key = validate_registry_name(entry.get("id") or name)
    for target in entry.get("targets", []):
        base = target_dir(scripts_root, target)
        if as_directory:
            container_name = validate_registry_name(entry.get("name") or key)
            container = base / container_name
            if container.is_dir():
                shutil.rmtree(container)
                removed.append(str(container))
        else:
            for rel in entry.get("files", []):
                safe_rel = validate_registry_relpath(str(rel))
                path = base / safe_rel
                if path.is_file() or path.is_symlink() and not path.exists():
                    path.unlink()
                    removed.append(str(path))
        # clean up now-empty directories up to the Scripts root
        current = container.parent if as_directory else base
        while current != scripts_root and current.is_dir() and not any(current.iterdir()):
            current.rmdir()
            current = current.parent

    remove_entry_from_registry(scripts_root, key)
    return removed or [f"registry entry '{name}'"]


def remove_entry_from_registry(scripts_root: Path, key: str) -> None:
    from .registry import remove_entry

    safe_key = validate_registry_name(key)
    remove_entry(scripts_root, safe_key) or remove_entry(scripts_root, safe_key.split(":")[-1])
