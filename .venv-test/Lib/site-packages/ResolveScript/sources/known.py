"""Known-extension table and standard naming conventions (Tauri-style)."""

from __future__ import annotations

# The canonical conventions (used to find a package from a bare name):
#   * dashes/underscores are treated alike when matching a bare name;
#   * a bare name resolves to github:owner/<resolvescript-<name>> first,
#     then github:owner/<name>;
#   * registered extensions live here with their canonical source.
CONVENTIONS = (
    # "resolvescript-<name>"
    "resolvescript",
)

_TABLE: dict[str, dict[str, str]] = {
    # name: canonical source + short description
    "hello": {"source": "github:OseMine/resolvescript-hello", "desc": "Hello-world demo extension"},
}


def known_names() -> list[str]:
    return sorted(_TABLE)


def lookup(name: str) -> dict | None:
    """Find a known extension by name (case/dash/underscore-insensitive)."""
    needle = name.lower().replace("-", "_").replace(" ", "_")
    for key, entry in _TABLE.items():
        if key.lower().replace("-", "_") == needle:
            return {"name": key, **entry}
    return None


def search(query: str) -> list[dict]:
    q = query.lower()
    return [
        {"name": name, **entry}
        for name, entry in _TABLE.items()
        if q in name.lower() or q in entry["desc"].lower() or q in entry["source"].lower()
    ]


def canonical_source(name: str) -> str | None:
    found = lookup(name)
    if found:
        return found["source"]
    return None
