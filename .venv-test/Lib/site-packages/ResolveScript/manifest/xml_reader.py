"""XML manifest reader: ElementTree → same dict → same :class:`Manifest`.

The XML shape mirrors the JSON shape 1:1 so both readers normalize through the
same :func:`~ResolveScript.manifest.model.manifest_from_dict` and can never
drift (parity guaranteed by construction).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .model import Manifest, ManifestError, manifest_from_dict

# DTD / entity declarations are never needed by ResolveScript manifests and
# are the carrier for XXE and entity-expansion ("billion laughs") attacks.
_XML_HAZARD = re.compile(r"<!DOCTYPE|<!ENTITY", re.IGNORECASE)


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    stripped = el.text.strip()
    return stripped or None


def _attr(el: ET.Element | None, name: str) -> str | None:
    if el is None:
        return None
    value = el.get(name)
    return value.strip() if value is not None and value.strip() else None


def _child(root: ET.Element, tag: str) -> str | None:
    return _text(root.find(tag))


def _child_list(root: ET.Element, wrapper: str, item: str) -> list[str]:
    result: list[str] = []
    container = root.find(wrapper)
    if container is not None:
        for el in container.findall(item):
            value = _text(el)
            if value is not None:
                result.append(value)
    return result


def _to_plain(root: ET.Element, source: str) -> dict[str, Any]:
    """Convert an XML manifest tree into the JSON-equivalent dict shape."""
    raw: dict[str, Any] = {}
    for key in (
        "name",
        "version",
        "kind",
        "author",
        "description",
        "python",
        "package_dir",
        "entrypoint",
        "id",
        "scripts_root",
    ):
        value = _child(root, key)
        if value is not None:
            raw[key] = value

    targets = _child_list(root, "targets", "target")
    if targets:
        raw["targets"] = targets

    compat = root.find("compat")
    if compat is not None:
        raw["compat"] = {k: _text(compat.find(k)) for k in ("resolve", "python") if _text(compat.find(k)) is not None}

    release = root.find("release")
    if release is not None:
        raw["release"] = {
            k: v
            for k in ("owner", "repo", "url")
            if (v := _text(release.find(k))) is not None
        }

    consolidate = root.find("consolidate")
    if consolidate is not None:
        cons: dict[str, Any] = {}
        enabled = _attr(consolidate, "enabled")
        output = _attr(consolidate, "output")
        if enabled is not None:
            cons["enabled"] = enabled
        if output is not None:
            cons["output"] = output
        entry = _child(consolidate, "entry")
        if entry is not None:
            cons["entry"] = entry
        exclude = _text_list(consolidate, "exclude")
        no_comment = _text_list(consolidate, "no_comment")
        if exclude:
            cons["exclude"] = exclude
        if no_comment:
            cons["no_comment"] = no_comment
        raw["consolidate"] = cons

    deps = _child_list(root, "dependencies", "dependency")
    if deps:
        raw["dependencies"] = deps

    install = root.find("install")
    if install is not None:
        inst: dict[str, Any] = {}
        as_directory = _attr(install, "as_directory")
        to = _attr(install, "to")
        if as_directory is not None:
            inst["as_directory"] = as_directory
        if to is not None:
            inst["to"] = to
        include = _text_list(install, "include")
        exclude = _text_list(install, "exclude")
        if include:
            inst["include"] = include
        if exclude:
            inst["exclude"] = exclude
        raw["install"] = inst

    return raw


def _text_list(container: ET.Element, tag: str) -> list[str]:
    result: list[str] = []
    for el in container.findall(tag):
        value = _text(el)
        if value is not None:
            result.append(value)
    return result


def load_manifest(path: str | Path) -> Manifest:
    """Read and normalize a ``manifest.xml`` file."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read manifest: {exc}", path=str(file_path)) from exc
    return loads(text, source=str(file_path))


def _reject_unsafe_xml(text: str, source: str) -> None:
    """Reject DOCTYPE / entity declarations before parsing (XXE guard)."""
    match = _XML_HAZARD.search(text)
    if match:
        raise ManifestError(
            "manifest XML may not declare a DOCTYPE or entities "
            f"(found {match.group(0)!r}); refusing to parse",
            path=source,
        )


def loads(text: str, source: str = "<manifest.xml>") -> Manifest:
    """Parse manifest XML text into a :class:`Manifest` with error context."""
    _reject_unsafe_xml(text, source)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        line, column = getattr(exc, "position", (None, None))
        lines = text.splitlines()
        line_text = lines[line - 1] if line and 0 < line <= len(lines) else None
        raise ManifestError(
            f"invalid XML: {exc}",
            path=source,
            line=line,
            column=column,
            line_text=line_text,
        ) from exc
    if root.tag != "manifest":
        raise ManifestError(f"expected a <manifest> root element, got <{root.tag}>", path=source)
    raw = _to_plain(root, source)
    return manifest_from_dict(raw, source=source)
