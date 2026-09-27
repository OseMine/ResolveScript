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

from .manifest.model import RequiresConfig


class PluginError(Exception):
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "path": self.path,
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
    """Return the CLI config directory (platform-specific)."""
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


def load_plugin_module(entry: PluginEntry) -> Any:
    """Import and return the plugin's entry module."""
    plugin_path = Path(entry.path)
    if not plugin_path.is_dir():
        raise PluginError(f"plugin path does not exist: {entry.path}")

    # Add plugin directory to sys.path for import
    sys.path.insert(0, str(plugin_path))
    try:
        return importlib.import_module(entry.manifest.entry)
    except ImportError as exc:
        raise PluginError(f"failed to import plugin entry '{entry.manifest.entry}': {exc}") from exc
    finally:
        sys.path.remove(str(plugin_path))


def register_plugin_commands(entry: PluginEntry, parser: Any) -> None:
    """Register plugin's CLI commands with the main argument parser."""
    module = load_plugin_module(entry)
    if hasattr(module, "register_commands"):
        module.register_commands(parser)
    else:
        # Auto-discover: look for a 'cli' module or 'Command' classes
        for cmd_name in entry.manifest.commands:
            # Try to find the command in the module
            if hasattr(module, cmd_name):
                cmd_obj = getattr(module, cmd_name)
                # Assume it's a function that returns a subparser
                if callable(cmd_obj):
                    # This is a simplistic auto-registration
                    pass


def install_plugin(
    source_path: Path,
    *,
    force: bool = False,
) -> PluginEntry:
    """Install a plugin from a local directory or package.

    The source must contain a plugin.json manifest at its root.
    """
    source_path = source_path.resolve()
    manifest_path = source_path / "plugin.json"
    if not manifest_path.is_file():
        raise PluginError(f"no plugin.json found in {source_path}")

    import json
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Build PluginManifest from raw JSON
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
            resolvescript=raw.get("requires", {}).get("resolvescript", ""),
            python=raw.get("requires", {}).get("python", ""),
        ),
        entry=raw.get("entry", ""),
    )

    if not manifest.name:
        raise PluginError("plugin.json missing required 'name'")
    if not manifest.version:
        raise PluginError("plugin.json missing required 'version'")
    if manifest.kind != "extension":
        raise PluginError("only 'extension' kind is supported for plugins")
    if not manifest.entry:
        raise PluginError("plugin.json missing required 'entry'")

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
