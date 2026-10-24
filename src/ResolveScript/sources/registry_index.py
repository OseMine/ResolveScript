"""Static registry index for extension discovery.

This module provides access to a static JSON index (registry.resolvescript.dev/extensions.json)
with dist-tags, per-version compat, and archive URL patterns — upgrading search/update
beyond the hardcoded known table.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from .known import _TABLE, canonical_source, lookup, search

# Default registry URL (can be overridden via env)
DEFAULT_REGISTRY_URL = "https://registry.resolvescript.dev/extensions.json"
ENV_REGISTRY_URL = "RESOLVESCRIPT_REGISTRY_URL"


class RegistryIndex:
    """Static registry index with version metadata."""

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.extensions = data.get("extensions", {})
        self.version = data.get("version", 1)

    @classmethod
    def load(cls, source: str | None = None) -> RegistryIndex:
        """Load registry from URL, local file, or fallback to built-in table."""
        source = source or os.environ.get(ENV_REGISTRY_URL) or DEFAULT_REGISTRY_URL

        if source.startswith(("http://", "https://")):
            try:
                with urllib.request.urlopen(source, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return cls(data)
            except Exception:
                pass  # Fall through to local/built-in

        if Path(source).is_file():
            try:
                data = json.loads(Path(source).read_text(encoding="utf-8"))
                return cls(data)
            except Exception:
                pass

        # Fallback: built-in known table as minimal index
        extensions = {}
        for name, entry in _TABLE.items():
            extensions[name] = {
                "description": entry.get("desc", ""),
                "source": entry.get("source", ""),
                "versions": {
                    "latest": {
                        "version": "0.0.0",
                        "source": entry.get("source", ""),
                        "compat": {"resolve": ">=18.5", "python": ">=3.9"},
                    }
                },
                "dist-tags": {"latest": "0.0.0"},
            }
        return cls({"version": 1, "extensions": extensions})

    def get_extension(self, name: str) -> dict[str, Any] | None:
        """Get full extension metadata by name."""
        return self.extensions.get(name)

    def get_versions(self, name: str) -> dict[str, Any]:
        """Get all version metadata for an extension."""
        ext = self.extensions.get(name)
        if not ext:
            return {}
        return ext.get("versions", {})

    def get_latest_version(self, name: str) -> str | None:
        """Get the 'latest' dist-tag version for an extension."""
        ext = self.extensions.get(name)
        if not ext:
            return None
        dist_tags = ext.get("dist-tags", {})
        latest_tag = dist_tags.get("latest")
        if latest_tag and latest_tag in ext.get("versions", {}):
            return latest_tag
        # Fallback: highest semver
        versions = list(ext.get("versions", {}).keys())
        if versions:
            return sorted(versions, key=lambda v: [int(x) for x in v.split(".")])[-1]
        return None

    def search(self, query: str) -> list[dict]:
        """Search extensions with full metadata."""
        q = query.lower()
        results = []
        for name, ext in self.extensions.items():
            if q in name.lower() or q in ext.get("description", "").lower():
                latest = self.get_latest_version(name)
                results.append({
                    "name": name,
                    "description": ext.get("description", ""),
                    "source": ext.get("source", ""),
                    "latest_version": latest,
                    "versions": ext.get("versions", {}),
                })
        return results


# Backward compatibility with known_names, lookup, search, canonical_source
# These now delegate to the registry index when available, else built-in table

_GLOBAL_REGISTRY: RegistryIndex | None = None


def get_registry() -> RegistryIndex:
    """Get the global registry instance (lazy-loaded)."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = RegistryIndex.load()
    return _GLOBAL_REGISTRY


def refresh_registry(source: str | None = None) -> RegistryIndex:
    """Force refresh the global registry."""
    global _GLOBAL_REGISTRY
    _GLOBAL_REGISTRY = RegistryIndex.load(source)
    return _GLOBAL_REGISTRY


# Enhanced search that uses registry
def search_enhanced(query: str) -> list[dict]:
    """Search using registry index if available, else fallback to known table."""
    try:
        return get_registry().search(query)
    except Exception:
        return search(query)


def lookup_enhanced(name: str) -> dict | None:
    """Lookup using registry index if available, else fallback to known table."""
    try:
        ext = get_registry().get_extension(name)
        if ext:
            latest = get_registry().get_latest_version(name)
            return {"name": name, "source": ext.get("source", ""), "latest_version": latest}
    except Exception:
        pass
    return lookup(name)


def canonical_source_enhanced(name: str) -> str | None:
    """Get canonical source using registry if available."""
    try:
        ext = get_registry().get_extension(name)
        if ext:
            return ext.get("source", "")
    except Exception:
        pass
    return canonical_source(name)
