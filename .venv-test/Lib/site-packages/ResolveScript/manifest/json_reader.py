"""JSON manifest reader: load, normalize and report errors with line hints."""

from __future__ import annotations

import json
from pathlib import Path

from .model import Manifest, ManifestError, manifest_from_dict


def load_manifest(path: str | Path) -> Manifest:
    """Read and normalize a ``manifest.json`` file."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read manifest: {exc}", path=str(file_path)) from exc
    return loads(text, source=str(file_path))


def loads(text: str, source: str = "<manifest.json>") -> Manifest:
    """Parse manifest text into a :class:`Manifest` with error context."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        lines = text.splitlines()
        line_text = lines[exc.lineno - 1] if 0 < exc.lineno <= len(lines) else None
        raise ManifestError(
            f"invalid JSON: {exc.msg}",
            path=source,
            line=exc.lineno,
            column=exc.colno,
            line_text=line_text,
        ) from exc
    return manifest_from_dict(raw, source=source)


def dumps(manifest: Manifest, indent: int = 2) -> str:
    """Serialize a manifest back to JSON text (round-trip helper)."""
    return json.dumps(manifest.to_dict(), ensure_ascii=False, indent=indent) + "\n"
