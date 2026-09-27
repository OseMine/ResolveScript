"""Install registry: ``Scripts/.resolvescript/install.json``.

Records every installed extension so ``manage list``, ``remove`` and conflict
detection know exactly which files belong to whom. Written atomically.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_REL = Path(".resolvescript") / "install.json"
SCHEMA_VERSION = 1

EMPTY_REGISTRY: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "extensions": {}}


class RegistryError(Exception):
    pass


def registry_path(scripts_root: Path | str) -> Path:
    return Path(scripts_root) / REGISTRY_REL


def read_registry(scripts_root: Path | str) -> dict[str, Any]:
    """Load the registry; a missing or empty file yields an empty registry."""
    path = registry_path(scripts_root)
    if not path.is_file():
        return copy.deepcopy(EMPTY_REGISTRY)
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RegistryError(f"registry is corrupt at {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RegistryError(f"registry at {path} is not a JSON object")
    raw.setdefault("schema_version", SCHEMA_VERSION)
    raw.setdefault("extensions", {})
    if not isinstance(raw["extensions"], dict):
        raise RegistryError(f"registry at {path} has a non-object 'extensions'")
    return raw


def write_registry(scripts_root: Path | str, registry: dict[str, Any]) -> None:
    """Persist the registry atomically (temp file + rename)."""
    root = Path(scripts_root)
    path = registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(registry, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".install-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        Path(tmp).replace(path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def get_extension(registry: dict[str, Any], key: str) -> dict[str, Any] | None:
    extensions = registry.get("extensions", {})
    for ext_key, entry in extensions.items():
        if ext_key == key or entry.get("id") == key or entry.get("name") == key:
            return entry
    return None


def extension_key(registry: dict[str, Any], name: str, manifest_id: str | None) -> str:
    existing = get_extension(registry, name)
    if existing is not None and manifest_id and existing.get("id") != manifest_id:
        return name
    return manifest_id or name


def add_or_update_entry(
    scripts_root: Path | str,
    key: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    registry = read_registry(scripts_root)
    registry["extensions"][key] = entry
    write_registry(scripts_root, registry)
    return registry


def remove_entry(scripts_root: Path | str, key: str) -> dict[str, Any] | None:
    """Delete an extension from the registry; returns the removed entry."""
    registry = read_registry(scripts_root)
    entry = registry["extensions"].pop(key, None)
    if entry is None:
        for ext_key, candidate in list(registry["extensions"].items()):
            if candidate.get("id") == key or candidate.get("name") == key:
                entry = registry["extensions"].pop(ext_key)
                break
    if entry is not None:
        write_registry(scripts_root, registry)
    return entry


def installed_at_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
