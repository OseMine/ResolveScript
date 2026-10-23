"""Workspace file management: ``resolvescript.json`` dependency list."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import ResolveScriptError

WORKSPACE_FILE = "resolvescript.json"

logger = logging.getLogger(__name__)


class WorkspaceError(ResolveScriptError, RuntimeError):
    pass


@dataclass(frozen=True)
class InstallSettings:
    """The ``install`` block of ``resolvescript.json``.

    Only the keys this CLI actually honors are represented. ``targets`` is empty
    when the file does not override the extension's own targets, and
    ``allow_remote`` is ``None`` when the file is silent (the environment and
    then the default policy decide).
    """

    targets: tuple[str, ...] = ()
    allow_remote: bool | None = None
    scripts_root: str = ""


def install_settings(cwd: Path | None = None) -> InstallSettings:
    """Read and validate the workspace ``install`` block."""
    data = read_workspace(cwd)
    raw = data.get("install") or {}
    if not isinstance(raw, dict):
        raise WorkspaceError(f"{workspace_path(cwd)}: 'install' must be an object")

    targets_raw = raw.get("targets") or []
    if isinstance(targets_raw, str):
        targets_raw = [targets_raw]
    if not isinstance(targets_raw, list) or any(
        not isinstance(target, str) for target in targets_raw
    ):
        raise WorkspaceError(
            f"{workspace_path(cwd)}: 'install.targets' must be a list of strings"
        )

    allow_remote = raw.get("allow_remote")
    if allow_remote is not None and not isinstance(allow_remote, bool):
        raise WorkspaceError(
            f"{workspace_path(cwd)}: 'install.allow_remote' must be a boolean"
        )

    scripts_root = raw.get("scripts_root") or ""
    if not isinstance(scripts_root, str):
        raise WorkspaceError(
            f"{workspace_path(cwd)}: 'install.scripts_root' must be a string"
        )

    return InstallSettings(
        targets=tuple(targets_raw),
        allow_remote=allow_remote,
        scripts_root=scripts_root,
    )


def workspace_path(cwd: Path | None = None) -> Path:
    return Path(cwd or Path.cwd()) / WORKSPACE_FILE


def has_workspace(cwd: Path | None = None) -> bool:
    return workspace_path(cwd).is_file()


def read_workspace(cwd: Path | None = None) -> dict:
    path = workspace_path(cwd)
    if not path.is_file():
        return {"dependencies": {}}
    try:
        data = json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkspaceError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkspaceError(f"{path}: expected a JSON object")
    if "dependencies" not in data:
        data["dependencies"] = {}
    if not isinstance(data["dependencies"], dict):
        raise WorkspaceError(f"{path}: 'dependencies' must be an object")
    return {k: v for k, v in data.items() if v is not None}


def write_workspace(data: dict, cwd: Path | None = None) -> Path:
    path = workspace_path(cwd)
    logger.debug("writing %s", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{WORKSPACE_FILE}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2) + "\n")
        _atomic_replace(Path(tmp_name), path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


def add_dependency(name: str, spec_text: str, cwd: Path | None = None) -> dict:
    data = read_workspace(cwd)
    data.setdefault("dependencies", {})[name] = spec_text
    return data


def remove_dependency(name: str, cwd: Path | None = None) -> dict:
    data = read_workspace(cwd)
    data.setdefault("dependencies", {}).pop(name, None)
    return data


def save(data: dict, cwd: Path | None = None) -> Path:
    return write_workspace(data, cwd)


def _atomic_replace(src: Path, dest: Path) -> None:
    src.replace(dest)
