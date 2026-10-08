"""Where DaVinci Resolve looks for Workflow Integrations.

Workflow Integrations do **not** live in the Scripts root. Resolve scans a
separate *Workflow Integration Plugins* directory on startup, builds one
``Workspace > Workflow Integrations`` menu entry per module it finds there, and
only reads a module's metadata at that point. A Python/Lua script dropped into
that folder is launched with ``resolve`` and ``project`` already bound.

The location moved between Resolve releases, and the two macOS layouts in the
wild differ, so :func:`candidates` returns every plausible path in preference
order and :func:`plugins_root` picks the first that exists.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from ..config import ENV_WORKFLOWS_ROOT, resolve_env
from ..errors import ResolveScriptError

__all__ = [
    "PLUGINS_DIR_NAME",
    "WorkflowPathError",
    "candidates",
    "default_plugins_root",
    "developer_examples",
    "native_module_source",
    "plugins_root",
    "supported",
]

PLUGINS_DIR_NAME = "Workflow Integration Plugins"

_APP = "DaVinci Resolve"
_VENDOR = "Blackmagic Design"
_SAMPLE_PLUGINS = ("SamplePlugin", "SamplePromisePlugin", "ScriptTestPlugin")


class WorkflowPathError(ResolveScriptError):
    """Raised when no Workflow Integration plugins directory can be determined."""


def _support_dir() -> Path:
    """Resolve's ``Support`` directory (Windows) or its macOS equivalent."""
    if platform.system() == "Windows":
        program_data = os.environ.get("PROGRAMDATA") or str(Path.home())
        return Path(program_data) / _VENDOR / _APP / "Support"
    return Path.home() / "Library" / "Application Support" / _VENDOR / _APP


def candidates(system: str | None = None) -> list[Path]:
    """Every known Workflow Integration Plugins directory, best first.

    Windows and macOS only — Resolve does not load plugins on Linux, though it
    does run *scripts* there, so the path is still returned for the script
    artifact. An empty list means the platform has no documented location.
    """
    system = system or platform.system()
    if system == "Windows":
        return [_support_dir() / PLUGINS_DIR_NAME]
    if system == "Darwin":
        base = _support_dir()
        # Some builds ship the Fusion-nested path, others the flat one. Both are
        # listed so an existing directory always wins over a guess.
        return [base / "Fusion" / PLUGINS_DIR_NAME, base / PLUGINS_DIR_NAME]
    return []


def supported(system: str | None = None) -> bool:
    """Whether this platform has a documented plugins directory."""
    return bool(candidates(system))


def default_plugins_root() -> Path:
    """The first existing candidates directory, else the first candidate.

    Raises when the platform has no documented location, since guessing a path
    would produce an integration Resolve silently never loads.
    """
    options = candidates()
    if not options:
        raise WorkflowPathError(
            f"DaVinci Resolve has no documented Workflow Integration Plugins "
            f"directory on {platform.system()}. Plugins are not supported on "
            "Linux; the script artifact is, so pass an explicit root if you "
            f"know where yours lives (or set ${ENV_WORKFLOWS_ROOT})."
        )
    for path in options:
        if path.is_dir():
            return path
    return options[0]


def plugins_root(override: str | Path | None = None) -> Path:
    """Effective plugins root: explicit override, then env var, then the OS default."""
    if override:
        return Path(override).expanduser()
    env_value = resolve_env(ENV_WORKFLOWS_ROOT)
    if env_value:
        return Path(env_value).expanduser()
    return default_plugins_root()


def developer_examples(system: str | None = None) -> Path:
    """Resolve's bundled Workflow Integration examples.

    This is where ``WorkflowIntegration.node`` — the native addon the Electron
    artifact needs to talk to Resolve — ships. It is a Resolve installation
    file, not ours, so it is read in place rather than vendored.
    """
    system = system or platform.system()
    if system == "Windows":
        return _support_dir() / "Developer" / "Workflow Integrations" / "Examples"
    if system == "Darwin":
        return (
            Path("/Library/Application Support")
            / _VENDOR
            / _APP
            / "Developer"
            / "Workflow Integrations"
            / "Examples"
        )
    return Path("/usr/share/DaVinciResolve/Developer/Workflow Integrations/Examples")


def native_module_source(system: str | None = None) -> list[Path]:
    """Places ``WorkflowIntegration.node`` may be found, in preference order."""
    root = developer_examples(system)
    return [root / name / "WorkflowIntegration.node" for name in _SAMPLE_PLUGINS]
