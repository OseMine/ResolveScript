"""Plugin registry (persistence)."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import PluginError
from .manifest import PluginEntry


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


def get_registry(config_dir: Path | None = None) -> PluginRegistry:
    """Get the plugin registry for the given (or default) config directory."""
    from .config import get_config_dir
    return PluginRegistry(config_dir or get_config_dir())


def discover_plugins(config_dir: Path | None = None) -> list[PluginEntry]:
    """Load all installed plugins from the registry."""
    return list(get_registry(config_dir).load().values())
