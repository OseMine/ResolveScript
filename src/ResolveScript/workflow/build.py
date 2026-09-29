"""Writing an integration to disk.

Three levels, in increasing order of consequence:

:func:`render`
    Pure. Produces every file as a string, so a build can be inspected,
    diffed or tested without touching a directory.

:func:`build`
    Writes into a directory you choose. Nothing outside it is touched.

:func:`install` / :func:`uninstall`
    Writes into the Workflow Integration Plugins root, which is the only
    directory Resolve actually scans. This is the step that makes an
    integration appear in ``Workspace > Workflow Integrations``.

The install path is deliberately *not* the project's general
:mod:`ResolveScript.install` machinery. That installs into the Fusion Scripts
root, tracks ownership in a registry, and refuses to overwrite another
extension's files — all correct there, and all wrong for a plugins root that
Resolve owns and re-reads on every launch.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import Integration, WorkflowError
from .paths import plugins_root as resolve_plugins_root
from .plugin import render_plugin
from .script import ScriptOptions, render_script

__all__ = [
    "REGISTRY_NAME",
    "BuildResult",
    "build",
    "describe_installed",
    "install",
    "install_plugin",
    "install_script",
    "list_installed",
    "render",
    "uninstall",
]

#: Records what is installed, so ``list``/``uninstall`` need not guess.
REGISTRY_NAME = ".resolvescript-workflows.json"
REGISTRY_VERSION = 1


@dataclass
class BuildResult:
    """What a build or install produced."""

    integration: Integration
    root: Path
    files: list[Path] = field(default_factory=list)
    script: Path | None = None
    plugin_dir: Path | None = None
    dry_run: bool = False

    def describe(self) -> list[str]:
        verb = "Would write" if self.dry_run else "Wrote"
        lines = [f"{verb} {self.integration.name} to {self.root}"]
        if self.plugin_dir is not None:
            lines.append(f"  plugin:  {self.plugin_dir}")
        if self.script is not None:
            lines.append(f"  script:  {self.script}")
        lines.append(f"  files:   {len(self.files)}")
        return lines


def render(
    integration: Integration,
    *,
    options: ScriptOptions | None = None,
    script: bool = True,
    electron: bool = True,
    script_rel: str = "",
    **plugin_kwargs: Any,
) -> dict[str, str]:
    """Return every file the integration needs, as ``{relative path: source}``.

    Paths are relative to the destination root, so the plugin's files are
    ``com.acme.deliver/main.js`` and the launcher is ``com.acme.deliver.py``.
    Both artifacts sit side by side in the plugins root, which is where Resolve
    expects to find them.

    :param script: write the Python launcher.
    :param electron: write the Electron shell. It is useless without the
        launcher, so ``electron=True, script=False`` only makes sense when
        reinstalling a shell over one that is already there.
    """
    if script and options is None:
        raise WorkflowError(
            "rendering the launcher needs the integration's module and attribute — "
            "pass options=ScriptOptions('my_pkg.integration')"
        )
    files: dict[str, str] = {}
    if script and options is not None:
        files[integration.script_name] = render_script(integration, options)
    if electron:
        files.update(
            {
                f"{integration.plugin_dir_name}/{rel}": source
                for rel, source in render_plugin(
                    integration, script_rel=script_rel, **plugin_kwargs
                ).items()
            }
        )
    return files


def build(
    integration: Integration,
    destination: str | Path,
    *,
    options: ScriptOptions | None = None,
    script: bool = True,
    electron: bool = True,
    clean: bool = False,
    dry_run: bool = False,
    **plugin_kwargs: Any,
) -> BuildResult:
    """Write the integration's files under ``destination``.

    :param clean: remove files an earlier build left behind, so a renamed
        source file does not linger in the plugin directory.
    :param dry_run: report what would be written without writing it.
    """
    root = Path(destination).expanduser()
    files = render(
        integration,
        options=options,
        script=script,
        electron=electron,
        **plugin_kwargs,
    )
    result = BuildResult(integration=integration, root=root, dry_run=dry_run)
    result.plugin_dir = root / integration.plugin_dir_name if electron else None
    result.script = root / integration.script_name if script else None

    if dry_run:
        result.files = [root / rel for rel in sorted(files)]
        return result

    for rel, source in sorted(files.items()):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
        result.files.append(target)

    if clean and electron and result.plugin_dir is not None and result.plugin_dir.is_dir():
        # Written files are already in place, so only the extras are removed.
        keep = set(files)
        for existing in sorted(result.plugin_dir.rglob("*"), reverse=True):
            if existing.is_file() and existing.relative_to(root).as_posix() not in keep:
                existing.unlink()
    return result


def _registry_path(root: Path) -> Path:
    return root / REGISTRY_NAME


def _read_registry(root: Path) -> dict[str, Any]:
    path = _registry_path(root)
    if not path.is_file():
        return {"version": REGISTRY_VERSION, "integrations": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A corrupt registry must not stop Resolve from being usable, and the
        # files it describes are still on disk, so start over.
        return {"version": REGISTRY_VERSION, "integrations": {}}
    if not isinstance(data, dict) or not isinstance(data.get("integrations"), dict):
        return {"version": REGISTRY_VERSION, "integrations": {}}
    return data


def _write_registry(root: Path, data: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _registry_path(root).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _record(
    root: Path,
    integration: Integration,
    *,
    script: Path | None,
    plugin_dir: Path | None,
) -> None:
    data = _read_registry(root)
    data["version"] = REGISTRY_VERSION
    data["integrations"][integration.id] = {
        "name": integration.name,
        "version": integration.version,
        "script": script.name if script is not None else "",
        "plugin": plugin_dir.name if plugin_dir is not None else "",
    }
    _write_registry(root, data)


def install(
    integration: Integration,
    plugins_root: str | Path | None = None,
    *,
    options: ScriptOptions | None = None,
    script: bool = True,
    electron: bool = True,
    clean: bool = True,
    dry_run: bool = False,
    **plugin_kwargs: Any,
) -> BuildResult:
    """Install the integration where Resolve will find it.

    With no ``plugins_root`` the OS default is used, overridable with the
    ``RESOLVESCRIPT_WORKFLOWS_ROOT`` environment variable. Resolve must be
    restarted to pick up a new integration — it scans the directory once, on
    launch.
    """
    root = Path(plugins_root).expanduser() if plugins_root else resolve_plugins_root()
    result = build(
        integration,
        root,
        options=options,
        script=script,
        electron=electron,
        clean=clean,
        dry_run=dry_run,
        **plugin_kwargs,
    )
    if not dry_run:
        _record(root, integration, script=result.script, plugin_dir=result.plugin_dir)
    return result


def install_script(
    integration: Integration,
    plugins_root: str | Path | None = None,
    **kwargs: Any,
) -> BuildResult:
    """Install only the Python launcher — no Electron shell.

    This is the portable artifact: it needs no npm, no Electron, and it works
    on Linux, where Resolve does not load plugins at all.
    """
    return install(integration, plugins_root, electron=False, **kwargs)


def install_plugin(
    integration: Integration,
    plugins_root: str | Path | None = None,
    **kwargs: Any,
) -> BuildResult:
    """Install only the Electron shell, leaving any launcher in place.

    The shell needs the launcher to talk to, so this is for iterating on the
    window without rewriting the Python that was generated from the project.
    """
    return install(integration, plugins_root, script=False, **kwargs)


def list_installed(plugins_root: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Every integration this tool installed into a plugins root.

    Only integrations installed by :mod:`ResolveScript.workflow` are listed.
    Anything else in the directory was put there by hand, by Resolve, or by
    another tool, and this makes no claims about it.
    """
    root = Path(plugins_root).expanduser() if plugins_root else resolve_plugins_root()
    data = _read_registry(root)
    entries: dict[str, dict[str, Any]] = {}
    for key, entry in data["integrations"].items():
        record = dict(entry)
        script = root / str(entry.get("script", ""))
        plugin = root / str(entry.get("plugin", ""))
        record["installed"] = (not entry.get("script") or script.is_file()) and (
            not entry.get("plugin") or plugin.is_dir()
        )
        entries[key] = record
    return entries


def uninstall(
    integration_or_id: str | Integration,
    plugins_root: str | Path | None = None,
) -> list[str]:
    """Remove an installed integration. Returns the paths removed."""
    key = (
        integration_or_id.id
        if isinstance(integration_or_id, Integration)
        else integration_or_id
    )
    root = Path(plugins_root).expanduser() if plugins_root else resolve_plugins_root()
    data = _read_registry(root)
    entry = data["integrations"].get(key)
    if entry is None:
        # Fall back to the layout, so an integration whose registry entry was
        # lost can still be cleaned up by name.
        entry = {"script": f"{key}.py", "plugin": key}

    removed: list[str] = []
    script = root / str(entry.get("script", ""))
    if script.is_file():
        script.unlink()
        removed.append(str(script))
    plugin = root / str(entry.get("plugin", ""))
    if plugin.is_dir():
        shutil.rmtree(plugin)
        removed.append(str(plugin))

    data["integrations"].pop(key, None)
    if data["integrations"]:
        _write_registry(root, data)
    elif _registry_path(root).is_file():
        _registry_path(root).unlink()
    return removed


def describe_installed(plugins_root: str | Path | None = None) -> list[str]:
    """Human-readable lines for the CLI's ``workflow list``."""
    entries = list_installed(plugins_root)
    if not entries:
        return ["No workflow integrations installed by ResolveScript."]
    lines: list[str] = []
    for key, entry in sorted(entries.items()):
        mark = "" if entry.get("installed") else "  (missing on disk)"
        lines.append(f"{entry.get('name', key)} {entry.get('version', '')}  [{key}]{mark}")
    return lines
