"""Plugin configuration paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_config_dir() -> Path:
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


def get_plugins_dir(config_dir: Path | None = None) -> Path:
    """Return the plugin installation directory."""
    return (config_dir or get_config_dir()) / "plugins"
