"""Workspace file management: ``resolvescript.json`` dependency list."""

from __future__ import annotations

import json
from pathlib import Path

WORKSPACE_FILE = "resolvescript.json"


class WorkspaceError(RuntimeError):
    pass


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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    _atomic_replace(tmp, path)
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
