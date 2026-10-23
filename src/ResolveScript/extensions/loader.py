"""Plugin module loading and command registration."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from .errors import PluginError
from .manifest import PluginEntry


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
