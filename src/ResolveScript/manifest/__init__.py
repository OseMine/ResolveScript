"""Manifest model, readers (JSON/XML) and validation.

Load a manifest from a file with format auto-detection::

    from ResolveScript.manifest import load_manifest
    manifest = load_manifest("my-tool/manifest.json")
"""

from __future__ import annotations

from pathlib import Path

from .json_reader import dumps
from .json_reader import loads as loads_json
from .model import (
    TARGET_SUGGESTIONS,
    Compat,
    ConsolidateConfig,
    ExtensionConfig,
    FusionConfig,
    InstallConfig,
    Manifest,
    ManifestError,
    Release,
    RequiresConfig,
    Target,
    manifest_from_dict,
)
from .validation import (
    is_valid_semver,
    validate_manifest,
    validate_manifest_or_throw,
    validate_target,
)
from .xml_reader import loads as loads_xml

__all__ = [
    "Compat",
    "ConsolidateConfig",
    "ExtensionConfig",
    "FusionConfig",
    "InstallConfig",
    "Manifest",
    "ManifestError",
    "Release",
    "RequiresConfig",
    "TARGET_SUGGESTIONS",
    "Target",
    "dumps",
    "is_valid_semver",
    "load_manifest",
    "loads",
    "manifest_from_dict",
    "validate_manifest",
    "validate_manifest_or_throw",
    "validate_target",
]


def load_manifest(path: str | Path) -> Manifest:
    """Read a manifest, auto-detecting the format from the file suffix.

    - ``.json`` (incl. ``manifest.json``) -> JSON reader
    - ``.xml``  (incl. ``manifest.xml``)  -> XML reader
    """
    file_path = Path(path)
    if file_path.suffix.lower() == ".xml":
        return loads_xml(file_path.read_text(encoding="utf-8"), source=str(file_path))
    return loads_json(file_path.read_text(encoding="utf-8"), source=str(file_path))


def loads(text: str, *, fmt: str = "json", source: str = "<manifest>") -> Manifest:
    """Parse manifest text; ``fmt`` is ``"json"`` (default) or ``"xml"``."""
    if fmt.lower() == "xml":
        return loads_xml(text, source=source)
    return loads_json(text, source=source)
