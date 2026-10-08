"""Framework extension (plugin) loader.

Plugins extend the CLI itself (new commands, sources, hooks, templates, mocks)
and install into the CLI config directory, never into Resolve.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ResolveScriptError
from .manifest.model import RequiresConfig


class PluginError(ResolveScriptError):
    """A plugin could not be loaded or installed."""
    pass


@dataclass
class PluginManifest:
    """Plugin metadata (loaded from plugin.json in the plugin package)."""

    name: str
    version: str
    kind: str = "extension"
    extension_kind: str = ""
    provides: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    hooks: dict[str, str] = field(default_factory=dict)
    templates: list[str] = field(default_factory=list)
    requires: RequiresConfig = field(default_factory=lambda: RequiresConfig())
    entry: str = ""

    def check_requires(self) -> None:
        """Verify environment satisfies requirements, raise PluginError if not."""
        if self.requires.resolvescript:
            from ResolveScript import __version__ as current_version
            from ResolveScript.semver import Version, matches
            if not matches(Version.parse(current_version), self.requires.resolvescript):
                raise PluginError(
                    f"plugin requires resolvescript {self.requires.resolvescript}, "
                    f"have {current_version}"
                )
        if self.requires.python:
            import sys
            py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            from ResolveScript.semver import Version, matches
            if not matches(Version.parse(py_version), self.requires.python):
                raise PluginError(
                    f"plugin requires python {self.requires.python}, have {py_version}"
                )


@dataclass
class PluginEntry:
    """Installed plugin metadata (stored in plugin registry)."""

    name: str
    version: str
    path: str
    manifest: PluginManifest
    installed_at: str
    source: str = ""
    integrity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "path": self.path,
            "source": self.source,
            "integrity": self.integrity,
            "manifest": {
                "name": self.manifest.name,
                "version": self.manifest.version,
                "kind": self.manifest.kind,
                "extension_kind": self.manifest.extension_kind,
                "provides": self.manifest.provides,
                "commands": self.manifest.commands,
                "sources": self.manifest.sources,
                "hooks": self.manifest.hooks,
                "templates": self.manifest.templates,
                "requires": self.manifest.requires.as_dict(),
                "entry": self.manifest.entry,
            },
            "installed_at": self.installed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginEntry:
        manifest = PluginManifest(
            name=data["manifest"]["name"],
            version=data["manifest"]["version"],
            kind=data["manifest"].get("kind", "extension"),
            extension_kind=data["manifest"].get("extension_kind", ""),
            provides=data["manifest"].get("provides", []),
            commands=data["manifest"].get("commands", []),
            sources=data["manifest"].get("sources", []),
            hooks=data["manifest"].get("hooks", {}),
            templates=data["manifest"].get("templates", []),
            requires=RequiresConfig(**data["manifest"].get("requires", {})),
            entry=data["manifest"].get("entry", ""),
        )
        return cls(
            name=data["name"],
            version=data["version"],
            path=data["path"],
            manifest=manifest,
            installed_at=data.get("installed_at", ""),
            source=data.get("source", ""),
            integrity=data.get("integrity", ""),
        )


class PluginRegistry:
    """Registry of installed plugins (stored in CLI config dir)."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.registry_file = config_dir / "plugins.json"

    def load(self) -> dict[str, PluginEntry]:
        if not self.registry_file.is_file():
            return {}
        try:
            data = json.loads(self.registry_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PluginError(f"corrupt plugin registry: {exc}") from exc
        return {name: PluginEntry.from_dict(entry) for name, entry in data.items()}

    def save(self, plugins: dict[str, PluginEntry]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {name: entry.to_dict() for name, entry in plugins.items()}
        self.registry_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def register(self, entry: PluginEntry) -> None:
        plugins = self.load()
        plugins[entry.name] = entry
        self.save(plugins)

    def unregister(self, name: str) -> bool:
        plugins = self.load()
        if name in plugins:
            del plugins[name]
            self.save(plugins)
            return True
        return False

    def get(self, name: str) -> PluginEntry | None:
        return self.load().get(name)


def _get_config_dir() -> Path:
    """Return the CLI config directory (platform-specific).

    ``RESOLVESCRIPT_CONFIG_DIR`` overrides the location (tests, portable
    installs); otherwise ``%APPDATA%\\ResolveScript`` on Windows and
    ``$XDG_CONFIG_HOME/ResolveScript`` (default ``~/.config/ResolveScript``)
    elsewhere.
    """
    override = os.environ.get("RESOLVESCRIPT_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or str(Path.home())
        return Path(root) / "ResolveScript"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "ResolveScript"


def _get_plugins_dir() -> Path:
    """Return the plugin installation directory."""
    return _get_config_dir() / "plugins"


def _get_registry() -> PluginRegistry:
    return PluginRegistry(_get_config_dir())


def discover_plugins() -> list[PluginEntry]:
    """Load all installed plugins from the registry."""
    return list(_get_registry().load().values())


def _module_name(entry: str) -> str:
    """Normalize a manifest entry (``plugin.py``, ``pkg/plugin.py``) to an import name."""
    name = entry.strip().replace("\\", ".")
    while name.endswith(".py"):
        name = name[:-3]
    if name.endswith(".__init__"):
        name = name[: -len(".__init__")]
    return name.strip(".")


def load_plugin_module(entry: PluginEntry) -> Any:
    """Import and return the plugin's entry module."""
    plugin_path = Path(entry.path)
    if not plugin_path.is_dir():
        raise PluginError(f"plugin path does not exist: {entry.path}")

    module_name = _module_name(entry.manifest.entry)
    if not module_name:
        raise PluginError(f"plugin '{entry.name}' has an empty entry module")

    # Drop any previously imported copy: after 'extensions add --force' the
    # installed files changed, so the cached module is stale.
    sys.modules.pop(module_name, None)

    # Add plugin directory to sys.path for import
    sys.path.insert(0, str(plugin_path))
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise PluginError(f"failed to import plugin entry '{entry.manifest.entry}': {exc}") from exc
    finally:
        sys.path.remove(str(plugin_path))


def register_plugin_commands(entry: PluginEntry, parser: Any) -> None:
    """Register a plugin's CLI commands with the main argument parser.

    The plugin's entry module must expose ``register_commands(parser)``,
    receiving the top-level subparser action. A plugin that declares
    ``commands`` in its manifest without providing the hook is an error so
    misconfigured plugins surface as warnings, not silent no-ops.
    """
    module = load_plugin_module(entry)
    register = getattr(module, "register_commands", None)
    if callable(register):
        register(parser)
    elif entry.manifest.commands:
        raise PluginError(
            f"plugin '{entry.name}' declares commands "
            f"{', '.join(entry.manifest.commands)} but its entry module "
            f"{entry.manifest.entry!r} has no register_commands(parser) function"
        )


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
        origin = "plugin.json"
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
        from .manifest import load_manifest as load_script_manifest

        script = load_script_manifest(manifest_path)
        origin = "manifest.json"
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
        raise PluginError(f"{origin} missing required 'name'")
    if not manifest.version:
        raise PluginError(f"{origin} missing required 'version'")
    if manifest.kind != "extension":
        raise PluginError("only 'extension' kind is supported for plugins")
    if not manifest.entry:
        raise PluginError(f"{origin} missing required 'entry'")
    return manifest


def install_plugin(
    source_path: Path,
    *,
    force: bool = False,
    source: str = "",
    integrity: str = "",
) -> PluginEntry:
    """Install a plugin from a local directory or package.

    The source must contain a ``plugin.json`` or a ``manifest.json`` with
    ``"kind": "extension"`` (see :func:`_load_plugin_manifest`).
    """
    source_path = source_path.resolve()
    manifest = _load_plugin_manifest(source_path)

    # Check version requirements
    manifest.check_requires()

    # Install to plugins directory
    plugins_dir = _get_plugins_dir()
    plugins_dir.mkdir(parents=True, exist_ok=True)
    target_dir = plugins_dir / manifest.name

    if target_dir.exists():
        if not force:
            raise PluginError(f"plugin '{manifest.name}' already installed (use --force to overwrite)")
        shutil.rmtree(target_dir)

    # Copy plugin package to plugins directory
    shutil.copytree(source_path, target_dir)

    # Register in registry
    from datetime import datetime, timezone
    entry = PluginEntry(
        name=manifest.name,
        version=manifest.version,
        path=str(target_dir),
        manifest=manifest,
        installed_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        integrity=integrity,
    )
    registry = _get_registry()
    registry.register(entry)

    return entry


def uninstall_plugin(name: str) -> bool:
    """Uninstall a plugin by name."""
    registry = _get_registry()
    entry = registry.get(name)
    if not entry:
        return False

    # Remove plugin directory
    plugin_dir = Path(entry.path)
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir, ignore_errors=True)

    return registry.unregister(name)


def list_plugins() -> list[PluginEntry]:
    """Return all installed plugins."""
    return discover_plugins()
