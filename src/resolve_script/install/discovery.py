"""Per-OS DaVinci Resolve Scripts-root discovery.

The Scripts root is the parent of the well-known target folders
(``Comp``, ``Utility``, ``Tool``, …) that appear in Resolve's Workspace menus.
The standard layout is ``…/Fusion/Scripts`` on every OS.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from ..config import ENV_SCRIPTS_ROOT
from ..manifest.model import TARGET_SUGGESTIONS, ManifestError, Target


def default_scripts_root() -> Path:
    """Return the OS-default DaVinci Resolve Scripts root (no override)."""
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        appdata = os.environ.get("APPDATA") or str(home)
        return Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Scripts"
    if system == "Darwin":
        return (
            home
            / "Library"
            / "Application Support"
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Fusion"
            / "Scripts"
        )
    # Linux and anything else
    return home / ".local" / "share" / "DaVinci Resolve" / "Fusion" / "Scripts"


def resolve_scripts_root(override: str | Path | None = None) -> Path:
    """Effective Scripts root: explicit override, then env var, then OS default."""
    if override:
        return Path(override).expanduser()
    env_value = os.environ.get(ENV_SCRIPTS_ROOT, "")
    if env_value.strip():
        return Path(env_value).expanduser()
    return default_scripts_root()


def target_dir(scripts_root: Path, target: str) -> Path:
    """Validate a target name and return its folder under the Scripts root."""
    if target == Target.ROOT.value:
        return Path(scripts_root)
    if target not in Target.valid_names():
        suggestion = TARGET_SUGGESTIONS.get(target.lower())
        hint = f" (did you mean '{suggestion}'?)" if suggestion else ""
        raise ManifestError(f"unknown script target '{target}'{hint}")
    return Path(scripts_root) / target
