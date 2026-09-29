"""Configuration: environment overrides and user-level path discovery."""

from __future__ import annotations

import os
import platform
from pathlib import Path

ENV_SCRIPTS_ROOT = "RESOLVESCRIPT_SCRIPTS_ROOT"
ENV_WORKFLOWS_ROOT = "RESOLVESCRIPT_WORKFLOWS_ROOT"
ENV_FUSES_ROOT = "RESOLVESCRIPT_FUSES_ROOT"
ENV_FUSION_PLUGINS_ROOT = "RESOLVESCRIPT_FUSION_PLUGINS_ROOT"
ENV_ALLOW_REMOTE = "RESOLVESCRIPT_ALLOW_REMOTE"

__all__ = [
    "ENV_SCRIPTS_ROOT",
    "ENV_WORKFLOWS_ROOT",
    "ENV_FUSES_ROOT",
    "ENV_FUSION_PLUGINS_ROOT",
    "ENV_ALLOW_REMOTE",
    "PROG",
    "resolve_env",
    "user_config_dir",
    "plugins_dir",
    "scripts_root_override",
    "allow_remote",
    "normalize_path",
    "is_editable_install",
    "python_spec",
]

PROG = "resolvescript"


def resolve_env(name: str) -> str | None:
    """Return a non-empty env var value, if set."""
    value = os.environ.get(name, "")
    return value.strip() if value.strip() else None


def user_config_dir() -> Path:
    """Return the CLI's own config directory (not Resolve's)."""
    if platform.system() == "Windows":
        root = os.environ.get("APPDATA") or str(Path.home())
        return Path(root) / PROG
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / PROG


def plugins_dir() -> Path:
    """Directory where framework extensions (plugins) are installed."""
    return user_config_dir() / "plugins"


def scripts_root_override() -> Path | None:
    """Return the user-set Resolve Scripts root override, if any."""
    value = resolve_env(ENV_SCRIPTS_ROOT)
    return Path(value).expanduser() if value else None


def allow_remote(default: bool = True) -> bool:
    """Supply-chain policy for URL/git installs (npm 12 allow-remote analog)."""
    value = resolve_env(ENV_ALLOW_REMOTE)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def normalize_path(value: str) -> Path:
    """Expand user/home markers and resolve to an absolute path."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def is_editable_install() -> bool:
    """True when the CLI runs from a source checkout (dev mode)."""
    return "src" in str(Path(__file__).parent) and Path(__file__).parent.parent.name == "src"


def python_spec() -> str:
    """Human-readable interpreter info (for diagnostics)."""
    return f"{platform.python_implementation()} {platform.python_version()}"
