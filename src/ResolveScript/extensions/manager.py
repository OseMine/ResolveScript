"""Plugin installation, uninstallation, and listing."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..manifest.model import RequiresConfig
from .config import get_plugins_dir
from .errors import PluginError
from .manifest import PluginEntry, PluginManifest
from .registry import get_registry


def _load_plugin_manifest(package_dir: Path) -> PluginManifest:
    """Read plugin metadata from ``plugin.json`` or a ``kind="extension"`` manifest.

    A plugin package resolved through the specifier pipeline carries an
    ordinary ``manifest.json`` whose ``kind`` is ``"extension"`` (one
    pipeline, two targets); a standalone ``plugin.json`` is accepted for
    direct installs from a directory.
    """
    plugin_json = package_dir / "plugin.json"
    if plugin_json.is_file():
        try:
            raw = json.loads(plugin_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PluginError(f"corrupt plugin.json: {exc}") from exc
        requires_raw = raw.get("requires") or {}
        if not isinstance(requires_raw, dict):
            raise PluginError("plugin.json 'requires' must be an object")
        manifest = PluginManifest(
            name=raw.get("name", ""),
            version=raw.get("version", ""),
            kind=raw.get("kind", "extension"),
            extension_kind=raw.get("extension_kind", ""),
            provides=raw.get("provides", []),
            commands=raw.get("commands", []),
            sources=raw.get("sources", []),
            hooks=raw.get("hooks", {}),
            templates=raw.get("templates", []),
            requires=RequiresConfig(
                resolvescript=requires_raw.get("resolvescript", ""),
                python=requires_raw.get("python", ""),
            ),
            entry=raw.get("entry", ""),
        )
    else:
        manifest_path = package_dir / "manifest.json"
        if not manifest_path.is_file():
            raise PluginError(
                f"{package_dir} has no plugin.json or manifest.json - not a plugin"
            )
        from ..manifest import load_manifest as load_script_manifest

        script = load_script_manifest(manifest_path)
        if script.kind != "extension":
            raise PluginError(
                f"'{script.name}' is a Resolve script (kind {script.kind!r}), not a "
                "framework extension; use 'resolvescript add' to install it into Resolve"
            )
        ext = script.extension
        manifest = PluginManifest(
            name=script.name,
            version=script.version,
            kind="extension",
            extension_kind=ext.extension_kind,
            provides=list(ext.provides),
            commands=list(ext.commands),
            sources=list(ext.sources),
            hooks=dict(ext.hooks),
            templates=list(ext.templates),
            requires=ext.requires,
            entry=script.entrypoint or "",
        )

    if not manifest.name:
        raise PluginError("missing required 'name'")
    if not manifest.version:
        raise PluginError("missing required 'version'")
    if manifest.kind != "extension":
        raise PluginError("only 'extension' kind is supported for plugins")
    if not manifest.entry:
        raise PluginError("missing required 'entry'")
    return manifest


def install_plugin(
    source_path: Path,
    *,
    force: bool = False,
    source: str = "",
    integrity: str = "",
    config_dir: Path | None = None,
) -> PluginEntry:
    """Install a plugin from a local directory or package.

    The source must contain a ``plugin.json`` or a ``manifest.json`` with
    ``"kind": "extension"``.
    """
    source_path = source_path.resolve()
    manifest = _load_plugin_manifest(source_path)

    # Check version requirements
    manifest.check_requires()

    # Install to plugins directory
    plugins_dir = get_plugins_dir(config_dir)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    target_dir = plugins_dir / manifest.name

    if target_dir.exists():
        if not force:
            raise PluginError(f"plugin '{manifest.name}' already installed (use --force to overwrite)")
        shutil.rmtree(target_dir)

    # Copy plugin package to plugins directory
    shutil.copytree(source_path, target_dir)

    # Register in registry
    entry = PluginEntry(
        name=manifest.name,
        version=manifest.version,
        path=str(target_dir),
        manifest=manifest,
        installed_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        integrity=integrity,
    )
    registry = get_registry(config_dir)
    registry.register(entry)

    return entry


def uninstall_plugin(name: str, config_dir: Path | None = None) -> bool:
    """Uninstall a plugin by name."""
    registry = get_registry(config_dir)
    entry = registry.get(name)
    if not entry:
        return False

    # Remove plugin directory
    plugin_dir = Path(entry.path)
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir, ignore_errors=True)

    return registry.unregister(name)


def list_plugins(config_dir: Path | None = None) -> list[PluginEntry]:
    """Return all installed plugins."""
    from .registry import discover_plugins
    return discover_plugins(config_dir)
