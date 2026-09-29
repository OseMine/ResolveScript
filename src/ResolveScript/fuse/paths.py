"""Where Fusion and DaVinci Resolve look for fuses and plugins.

Neither format lives in Resolve's Scripts root. Both come from Fusion's PathMap
— the set of directories Fusion builds its plugin registry from at startup — and
the published locations differ per application, per platform, and per release:
the Fuse SDK lists a ``Fuses`` directory for both Fusion and Resolve, the
stand-alone app moved its user data under ``%APPDATA%`` at some point, and
Blackmagic's own forum answers still point at ``Documents\\Blackmagic Design``.

So :func:`candidates` returns every plausible directory in preference order and
:func:`default_root` picks the first that exists. An existing directory always
beats a guess, which is the only ordering rule that is reliably right.

The distinction between the two roots
-------------------------------------

``fuse``
    Scripted plugins. One Lua file each, named ``ToolName.fuse``, dropped
    directly into the directory. Fusion compiles them on the fly.

``plugin``
    Compiled native plugins — ``Krokodove.plugin`` and friends. A platform
    binary or bundle, and the one part of this pipeline that cannot be built
    from source here. :mod:`ResolveScript.fuse.build` deploys one; it does not
    produce one.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from ..config import ENV_FUSES_ROOT, ENV_FUSION_PLUGINS_ROOT, resolve_env

__all__ = [
    "FUSES_DIR_NAME",
    "PLUGINS_DIR_NAME",
    "FusionPathError",
    "candidates",
    "default_plugins_root",
    "default_root",
    "exists",
    "list_roots",
    "root",
]

FUSES_DIR_NAME = "Fuses"
PLUGINS_DIR_NAME = "Plugins"

_VENDOR = "Blackmagic Design"
_FUSION = "Fusion"
_RESOLVE = "DaVinci Resolve"


class FusionPathError(Exception):
    """Raised when no Fuses or Plugins directory can be determined."""


def _windows_program_data() -> Path:
    return Path(os.environ.get("PROGRAMDATA") or str(Path.home()))


def _application_dirs(system: str) -> list[Path]:
    """Every directory that *contains* a ``Fuses`` or ``Plugins`` folder.

    Fusion is listed before Resolve because a machine with the standalone app
    installed will usually have both, and the Fuses menu is reached from the
    Fusion page in either one — so Fusion is the more universal home and the
    first candidate.

    ``system`` is threaded through rather than read from the platform so the
    whole table is testable, and so a caller can ask about another OS's layout
    instead of only this machine's.
    """
    if system == "Windows":
        base = _windows_program_data() / _VENDOR
        return [base / _FUSION, base / _RESOLVE / "Support" / _FUSION]
    return [
        Path.home() / "Library" / "Application Support" / _VENDOR / _FUSION,
        Path.home() / "Library" / "Application Support" / _VENDOR / _RESOLVE / _FUSION,
        Path("/Library/Application Support") / _VENDOR / _RESOLVE / _FUSION,
    ]


def candidates(name: str = FUSES_DIR_NAME, system: str | None = None) -> list[Path]:
    """Every known ``name`` plugin directory, best first.

    ``name`` is ``"Fuses"`` or ``"Plugins"``; the two sit side by side in every
    layout below. An empty list means the platform has no documented location.
    """
    system = system or platform.system()
    if name not in {FUSES_DIR_NAME, PLUGINS_DIR_NAME}:
        raise FusionPathError(f"unknown plugin directory {name!r}")

    if system == "Windows":
        appdata = Path(os.environ.get("APPDATA") or str(Path.home())) / _VENDOR
        return [
            *(base / name for base in _application_dirs(system)),
            # Fusion 9 and earlier kept user data under the profile.
            appdata / _FUSION / name,
            Path(os.environ.get("PUBLIC") or str(Path.home() / "Public"))
            / "Documents"
            / _VENDOR
            / _FUSION
            / name,
        ]
    if system == "Darwin":
        return [base / name for base in _application_dirs(system)]
    # Linux: only the Resolve tree is documented. The standalone Fusion app has
    # no Linux release, so a Fusion-app path here would be an invention.
    return [
        Path.home() / ".local" / "share" / "DaVinciResolve" / "Fusion" / name,
        Path("/.local/share/DaVinciResolve/Fusion") / name,
    ]


def exists(name: str = FUSES_DIR_NAME, system: str | None = None) -> bool:
    """Whether the platform has a documented location for this directory."""
    return bool(candidates(name, system))


def default_root(name: str = FUSES_DIR_NAME, system: str | None = None) -> Path:
    """The first existing candidates directory, else the first candidate.

    Raises when nothing is known for the platform, since writing a fuse
    somewhere Fusion does not scan produces a tool that silently never appears.
    """
    options = candidates(name, system)
    if not options:
        raise FusionPathError(
            f"no documented {name} directory for {system or platform.system()}; "
            "pass an explicit root if you know where yours lives"
        )
    for path in options:
        if path.is_dir():
            return path
    return options[0]


def default_plugins_root(system: str | None = None) -> Path:
    """The compiled-plugin (``.plugin``) directory."""
    return default_root(PLUGINS_DIR_NAME, system)


def root(name: str = FUSES_DIR_NAME, override: str | Path | None = None) -> Path:
    """Effective root: explicit override, then env var, then the OS default."""
    if override:
        return Path(override).expanduser()
    env_name = ENV_FUSES_ROOT if name == FUSES_DIR_NAME else ENV_FUSION_PLUGINS_ROOT
    env_value = resolve_env(env_name)
    if env_value:
        return Path(env_value).expanduser()
    return default_root(name)


def list_roots() -> list[tuple[str, list[Path]]]:
    """Both candidate lists, for ``resolvescript fuse root --list``."""
    return [(name, candidates(name)) for name in (FUSES_DIR_NAME, PLUGINS_DIR_NAME)]
