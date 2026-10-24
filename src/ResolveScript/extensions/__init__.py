"""Framework extension (CLI plugin) management.

Plugins extend the `resolvescript` CLI itself (new commands, hooks, templates,
mocks) and install into the CLI config directory, never into Resolve.
"""

from .config import get_config_dir, get_plugins_dir
from .errors import PluginError
from .hooks import (
    dispatch_plugin_hooks,
    get_plugin_contributions,
    get_plugin_provides,
    get_plugin_sources,
    get_plugin_templates,
)
from .loader import load_plugin_module, register_plugin_commands
from .manager import install_plugin, list_plugins, uninstall_plugin
from .manifest import PluginEntry, PluginManifest
from .registry import PluginRegistry, discover_plugins, get_registry

__all__ = [
    "PluginError",
    "PluginManifest",
    "PluginEntry",
    "PluginRegistry",
    "discover_plugins",
    "get_registry",
    "get_config_dir",
    "get_plugins_dir",
    "load_plugin_module",
    "register_plugin_commands",
    "dispatch_plugin_hooks",
    "get_plugin_sources",
    "get_plugin_templates",
    "get_plugin_provides",
    "get_plugin_contributions",
    "install_plugin",
    "uninstall_plugin",
    "list_plugins",
]
