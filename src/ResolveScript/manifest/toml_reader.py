"""TOML manifest reader: load, normalize and report errors with line hints.

This is an optional format for projects that prefer TOML over JSON/XML.
Uses the standard library ``tomllib`` (Python 3.11+) or ``tomli`` backport.
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib as _tomllib  # type: ignore[no-redef]
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore[assignment]

from .model import Manifest, ManifestError, manifest_from_dict


def load_manifest(path: str | Path) -> Manifest:
    """Read and normalize a ``manifest.toml`` file."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read manifest: {exc}", path=str(file_path)) from exc
    return loads(text, source=str(file_path))


def loads(text: str, source: str = "<manifest.toml>") -> Manifest:
    """Parse manifest text into a :class:`Manifest` with error context."""
    if tomllib is None:
        raise ManifestError(
            "TOML support requires Python 3.11+ or the 'tomli' package (pip install tomli)",
            path=source,
        )
    try:
        raw = _tomllib.loads(text)
    except Exception as exc:
        raise ManifestError(f"invalid TOML: {exc}", path=source) from exc
    return manifest_from_dict(raw, source=source)


def dumps(manifest: Manifest) -> str:
    """Serialize a manifest back to TOML text.

    Note: This requires the 'tomli_w' package for Python <3.11,
    or Python 3.11+ with tomllib/tomli_w.
    """
    try:
        import tomli_w
    except ImportError as exc:
        pass  # tomli_w import is only needed for serialization
        raise ManifestError(
            "TOML serialization requires 'tomli_w' package (pip install tomli_w)"
        ) from exc
    return tomli_w.dumps(manifest.to_dict())
