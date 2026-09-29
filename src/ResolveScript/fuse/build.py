"""Writing fuses and compiled plugins to disk.

Three levels, in increasing order of consequence — the same ladder
:mod:`ResolveScript.workflow.build` uses, and for the same reasons:

:func:`render`
    Pure. Returns the ``.fuse`` source as a string, so a fuse can be inspected,
    diffed or linted without touching a directory.

:func:`build`
    Writes one file into a directory you choose. Nothing outside it is touched.

:func:`install` / :func:`install_binary`
    Writes into the Fuses or Plugins root — the only directories Fusion scans.
    Resolve or Fusion has to be restarted to see the change: the registry is
    built once, at startup.

:func:`package_fuse`
    Bundles a fuse (and optionally a compiled plugin) into a zip with a
    checksum, for handing to somebody else.

The install path is deliberately *not* the project's general
:mod:`ResolveScript.install` machinery. That installs into the Fusion Scripts
root, tracks ownership in a registry keyed by package name, and refuses to
overwrite another extension's files — correct there, and wrong for a directory
Fusion owns and re-reads wholesale on every launch.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import BinaryPlugin, Fuse, FuseError
from .paths import FUSES_DIR_NAME, PLUGINS_DIR_NAME
from .paths import root as resolve_root
from .render import FUSE_EXTENSION, render_fuse
from .validate import checked_with, problems

__all__ = [
    "REGISTRY_NAME",
    "REGISTRY_VERSION",
    "BinaryBuildResult",
    "FuseBuildResult",
    "PackageResult",
    "build",
    "describe_installed",
    "install",
    "install_binary",
    "list_installed",
    "package_fuse",
    "render",
    "uninstall",
]

#: Records what is installed, so ``list``/``uninstall`` need not guess. One
#: file per root, so a Fuses directory and a Plugins directory each get their
#: own and never have to be merged.
REGISTRY_NAME = ".resolvescript-fuses.json"
REGISTRY_VERSION = 1

_FUSE_SECTION = "fuses"
_PLUGIN_SECTION = "plugins"


@dataclass
class FuseBuildResult:
    """What :func:`render`, :func:`build` or :func:`install` produced for a fuse."""

    fuse: Fuse
    root: Path
    files: list[Path] = field(default_factory=list)
    fuse_file: Path | None = None
    dry_run: bool = False
    checked: str = ""

    def describe(self) -> list[str]:
        verb = "Would write" if self.dry_run else "Wrote"
        lines = [f"{verb} {self.fuse.name} to {self.root}"]
        if self.fuse_file is not None:
            lines.append(f"  file:   {self.fuse_file}")
        lines.append(f"  files:  {len(self.files)}")
        if self.checked:
            lines.append(f"  checked: {self.checked}")
        lines.append("  restart Fusion or Resolve to load it")
        return lines


@dataclass
class BinaryBuildResult:
    """What :func:`install_binary` deployed."""

    plugin: BinaryPlugin
    root: Path
    target: Path | None = None
    dry_run: bool = False

    def describe(self) -> list[str]:
        verb = "Would copy" if self.dry_run else "Copied"
        return [
            f"{verb} {self.plugin.name} to {self.root}",
            f"  target: {self.target}",
            "  restart Fusion or Resolve to load it",
        ]


@dataclass
class PackageResult:
    """A distributable bundle."""

    archive: Path
    sha256: str
    files: list[str] = field(default_factory=list)
    checksum_file: Path | None = None

    def describe(self) -> list[str]:
        lines = [
            f"Created {self.archive.name} ({self.archive.stat().st_size} bytes)",
            f"SHA-256: {self.sha256}",
            f"  files: {', '.join(self.files) or 'none'}",
        ]
        if self.checksum_file is not None:
            lines.append(f"Wrote {self.checksum_file.name}")
        return lines


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# -- fuses ---------------------------------------------------------------
def render(fuse: Fuse) -> dict[str, str]:
    """Return the fuse's files as ``{filename: source}``.

    A fuse is one file, so this is a one-entry dict rather than a bare string.
    It keeps :func:`build` and the packaging code on the same shape as every
    other artifact in this tool, and leaves room for a fuse that ships a
    companion file.
    """
    return {fuse.filename: render_fuse(fuse)}


def build(
    fuse: Fuse,
    destination: str | Path,
    *,
    clean: bool = False,
    dry_run: bool = False,
    check: bool = True,
) -> FuseBuildResult:
    """Write the fuse's files under ``destination``.

    :param clean: also remove a ``*.fuse`` file an *earlier install* of this tool
        left behind, so a renamed tool does not linger twice in the Fuses
        directory. Only files the registry in ``root`` records are eligible —
        the directory belongs to Fusion and to every other vendor, so a glob
        would delete other people's work. It is a no-op in a directory with no
        registry, which is what makes it safe on a fresh ``dist/``.
    :param dry_run: report what would be written without writing it. The fuse is
        still checked, because that is the part that is cheap and the part that
        catches real mistakes.
    :param check: run the structural and (when available) Lua-parse checks on
        what was written. Turn it off only to deliberately write a fuse that
        does not load.
    """
    root = Path(destination).expanduser()
    files = render(fuse)
    result = FuseBuildResult(
        fuse=fuse, root=root, fuse_file=root / fuse.filename, dry_run=dry_run
    )
    if dry_run:
        result.files = [root / rel for rel in sorted(files)]
        return result

    root.mkdir(parents=True, exist_ok=True)
    for rel, source in sorted(files.items()):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8", newline="\n")
        result.files.append(target)

    if check:
        found = problems(fuse, result.fuse_file)
        if found:
            # The file stays on disk: a fuse that fails to parse is usually one
            # small fix away, and the message names the line. Deleting it would
            # throw away the author's work to save them from a stderr line.
            raise FuseError(
                f"{fuse.filename} was written but is not a loadable fuse:\n  "
                + "\n  ".join(found)
            )
        result.checked = checked_with(result.fuse_file)  # type: ignore[arg-type]

    if clean:
        for stale in _stale_fuses(root, keep=set(files)):
            stale.unlink()
            result.files.append(stale)
    return result


def _stale_fuses(root: Path, *, keep: set[str]) -> list[Path]:
    """Fuses this tool installed into ``root`` that the current build replaces.

    The Fuses directory is *shared* — it holds every vendor's tools, and Fusion
    re-reads it wholesale — so cleaning by glob would delete other people's
    work. Only files this tool recorded in the registry are eligible, and the
    registry is consulted rather than the directory listing for the same reason.
    """
    protected = {entry.get("file") for entry in _read_registry(root)[_FUSE_SECTION].values()}
    stale: list[Path] = []
    for name in sorted(protected - keep):
        if not name:
            continue
        candidate = root / str(name)
        if candidate.is_file():
            stale.append(candidate)
    return stale


def install(
    fuse: Fuse,
    fuses_root: str | Path | None = None,
    *,
    clean: bool = True,
    dry_run: bool = False,
    check: bool = True,
) -> FuseBuildResult:
    """Install the fuse where Fusion will find it.

    With no ``fuses_root`` the OS default is used, overridable with
    ``RESOLVESCRIPT_FUSES_ROOT``. Fusion builds its registry once, at startup,
    so a new file only appears after a restart.
    """
    root = Path(fuses_root).expanduser() if fuses_root else resolve_root(FUSES_DIR_NAME)
    result = build(fuse, root, clean=clean, dry_run=dry_run, check=check)
    if not dry_run:
        _record(root, _FUSE_SECTION, fuse.class_name, _fuse_record(fuse, result))
    return result


def _fuse_record(fuse: Fuse, result: FuseBuildResult) -> dict[str, Any]:
    return {
        "name": fuse.name,
        "version": fuse.version,
        "category": fuse.category,
        "tool_type": fuse.tool_type,
        "file": result.fuse_file.name if result.fuse_file else fuse.filename,
        "size": result.fuse_file.stat().st_size
        if result.fuse_file is not None and result.fuse_file.is_file()
        else 0,
    }


# -- compiled plugins ----------------------------------------------------
def install_binary(
    plugin: BinaryPlugin,
    plugins_root: str | Path | None = None,
    *,
    dry_run: bool = False,
    overwrite: bool = True,
) -> BinaryBuildResult:
    """Copy a prebuilt ``.plugin`` into the Plugins directory.

    A compiled plugin cannot be built here — see :class:`~ResolveScript.fuse.BinaryPlugin`
    — so this only moves bytes. ``overwrite=False`` refuses to replace an
    existing file, which is the one thing worth being careful about: Fusion
    loads whatever is in the directory, and a half-copied bundle is a plugin
    that fails to register.
    """
    root = Path(plugins_root).expanduser() if plugins_root else resolve_root(PLUGINS_DIR_NAME)
    target = root / plugin.target
    result = BinaryBuildResult(plugin=plugin, root=root, target=target, dry_run=dry_run)
    if dry_run:
        return result
    if target.exists() and not overwrite:
        raise FuseError(f"{target} already exists; omit --no-force to replace it")
    root.mkdir(parents=True, exist_ok=True)
    if plugin.path.is_dir():
        # A macOS bundle is a directory. Copied whole, and replaced whole, so a
        # stale file inside the old bundle cannot survive the update.
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(plugin.path, target)
    else:
        shutil.copy2(plugin.path, target)
    _record(
        root,
        _PLUGIN_SECTION,
        plugin.name,
        {
            "name": plugin.name,
            "target": plugin.target,
            "source": str(plugin.path),
            "notes": plugin.notes,
            "size": target.stat().st_size if target.is_file() else 0,
        },
    )
    return result


# -- packaging -----------------------------------------------------------
def package_fuse(
    fuse: Fuse,
    dist_dir: str | Path | None = None,
    *,
    plugin: BinaryPlugin | None = None,
    check: bool = True,
) -> PackageResult:
    """Bundle a fuse into a zip, with a checksum, for distribution.

    The archive holds the ``.fuse`` and a small ``resolvescript.json`` describing
    it, so whoever unpacks it can see what they got without a Fusion install.
    A ``plugin=`` is carried alongside — a scripted fuse and a compiled plugin
    that belong together is the common case for a vendor.

    :param check: validate before bundling. A fuse that does not load should not
        be handed to somebody else, and there is no downstream test that would
        catch it.
    """
    dist = Path(dist_dir).expanduser() if dist_dir else Path.cwd() / "dist"
    if check:
        found = problems(fuse)
        if found:
            raise FuseError(
                f"{fuse.filename} is not a loadable fuse, refusing to package:\n  "
                + "\n  ".join(found)
            )
    dist.mkdir(parents=True, exist_ok=True)

    files = render(fuse)
    descriptor = {
        "kind": "fuse",
        **fuse.as_dict(),
        "files": sorted(files),
    }
    if plugin is not None:
        descriptor["plugin"] = {
            "name": plugin.name,
            "target": plugin.target,
            "size": plugin.path.stat().st_size if plugin.path.is_file() else 0,
        }

    archive = dist / f"{fuse.class_name}-{fuse.version}.zip"
    entries: list[str] = []
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for rel, source in sorted(files.items()):
            bundle.writestr(rel, source)
            entries.append(rel)
        bundle.writestr("resolvescript.json", json.dumps(descriptor, indent=2) + "\n")
        entries.append("resolvescript.json")
        if plugin is not None:
            # Stored, not deflated: an already-compressed binary gains nothing
            # and a macOS bundle has to keep its executable bit and its nested
            # symlinks, which writestr would flatten.
            bundle.write(plugin.path, plugin.target)
            entries.append(plugin.target)

    sha = _sha256(archive)
    checksum_file = dist / "SHA256SUMS.txt"
    checksum_file.write_text(f"{sha}  {archive.name}\n", encoding="utf-8")
    return PackageResult(
        archive=archive,
        sha256=sha,
        files=sorted(entries),
        checksum_file=checksum_file,
    )


# -- registry ------------------------------------------------------------
def _registry_path(root: Path) -> Path:
    return root / REGISTRY_NAME


def _read_registry(root: Path) -> dict[str, Any]:
    path = _registry_path(root)
    empty: dict[str, Any] = {
        "version": REGISTRY_VERSION,
        _FUSE_SECTION: {},
        _PLUGIN_SECTION: {},
    }
    if not path.is_file():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A corrupt registry must not stop Fusion from being usable, and the
        # files it describes are still on disk, so start over rather than
        # refusing to read.
        return empty
    if not isinstance(data, dict):
        return empty
    for section in (_FUSE_SECTION, _PLUGIN_SECTION):
        if not isinstance(data.get(section), dict):
            data[section] = {}
    return data


def _write_registry(root: Path, data: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _registry_path(root).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _record(root: Path, section: str, key: str, entry: dict[str, Any]) -> None:
    data = _read_registry(root)
    data["version"] = REGISTRY_VERSION
    data[section][key] = entry
    _write_registry(root, data)


def list_installed(
    directory: str | Path | None = None,
    *,
    kind: str = "fuse",
) -> dict[str, dict[str, Any]]:
    """Every fuse or compiled plugin this tool installed into a directory.

    Only what :mod:`ResolveScript.fuse` put there is listed. Anything else in
    the directory was placed by hand, by Fusion, or by another manager, and
    this makes no claims about it — which is also why a fuse with no registry
    entry is still loadable, it just cannot be uninstalled by name.
    """
    if kind not in {"fuse", "plugin"}:
        raise FuseError(f"unknown kind {kind!r}; use 'fuse' or 'plugin'")
    name = FUSES_DIR_NAME if kind == "fuse" else PLUGINS_DIR_NAME
    root = Path(directory).expanduser() if directory else resolve_root(name)
    data = _read_registry(root)
    entries: dict[str, dict[str, Any]] = {}
    for key, entry in data[section_name(kind)].items():
        record = dict(entry)
        filename = str(entry.get("file") or entry.get("target") or "")
        record["installed"] = (root / filename).exists() if filename else False
        entries[key] = record
    return entries


def section_name(kind: str) -> str:
    """The registry section a kind is recorded under."""
    return _FUSE_SECTION if kind == "fuse" else _PLUGIN_SECTION


def uninstall(
    target: str | Fuse,
    directory: str | Path | None = None,
    *,
    kind: str = "fuse",
) -> list[str]:
    """Remove an installed fuse or compiled plugin. Returns the paths removed.

    A fuse is identified by its class name (``Posterize``) or its file name
    (``Posterize.fuse``); a compiled plugin by the name it was installed under.
    A :class:`~ResolveScript.fuse.Fuse` may be passed instead of a name, which
    saves the caller from having to remember which spelling it used.
    """
    if kind not in {"fuse", "plugin"}:
        raise FuseError(f"unknown kind {kind!r}; use 'fuse' or 'plugin'")
    if isinstance(target, Fuse):
        target = target.class_name
    name = FUSES_DIR_NAME if kind == "fuse" else PLUGINS_DIR_NAME
    root = Path(directory).expanduser() if directory else resolve_root(name)
    key = target[: -len(FUSE_EXTENSION)] if target.lower().endswith(FUSE_EXTENSION) else target
    data = _read_registry(root)
    entry = data[section_name(kind)].get(key)
    filename = str((entry or {}).get("file") or (entry or {}).get("target") or "")
    if not filename:
        # Fall back to the naming convention, so something whose registry entry
        # was lost can still be cleaned up by name.
        filename = key if kind == "plugin" else f"{key}{FUSE_EXTENSION}"

    removed: list[str] = []
    path = root / filename
    if path.is_dir():
        shutil.rmtree(path)
        removed.append(str(path))
    elif path.is_file():
        path.unlink()
        removed.append(str(path))

    if key in data[section_name(kind)]:
        data[section_name(kind)].pop(key)
    if any(data[section] for section in (_FUSE_SECTION, _PLUGIN_SECTION)):
        _write_registry(root, data)
    elif _registry_path(root).is_file():
        _registry_path(root).unlink()
    return removed


def describe_installed(
    directory: str | Path | None = None,
    *,
    kind: str = "fuse",
) -> list[str]:
    """Human-readable lines for the CLI's ``fuse list`` / ``plugin list``."""
    entries = list_installed(directory, kind=kind)
    if not entries:
        label = "fuses" if kind == "fuse" else "compiled plugins"
        return [f"No {label} installed by ResolveScript."]
    lines: list[str] = []
    for key, entry in sorted(entries.items()):
        mark = "" if entry.get("installed") else "  (missing on disk)"
        if kind == "fuse":
            lines.append(
                f"{entry.get('name', key)} {entry.get('version', '')}  "
                f"[{key}] in {entry.get('category', '')}{mark}"
            )
        else:
            lines.append(f"{entry.get('name', key)}  [{entry.get('target', key)}]{mark}")
    return lines
