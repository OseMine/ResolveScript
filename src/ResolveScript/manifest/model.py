"""Manifest data model shared by the JSON and XML readers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ManifestError(Exception):
    """A manifest could not be parsed or normalized.

    Carries enough context to render ``path:line:column`` hints.
    """

    def __init__(
        self,
        message: str,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        line_text: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.path = path
        self.line = line
        self.column = column
        self.line_text = line_text

    def __str__(self) -> str:
        parts = []
        if self.path:
            loc = self.path
            if self.line is not None:
                loc += f":{self.line}"
                if self.column is not None:
                    loc += f":{self.column}"
            parts.append(loc)
        parts.append(self.message)
        rendered = ": ".join(parts)
        if self.line_text:
            rendered += f"\n    {self.line_text.strip()}"
        return rendered


class Target(str, Enum):
    """Valid Resolve Scripts subfolders under the per-OS scripts root."""

    COMP = "Comp"
    UTILITY = "Utility"
    TOOL = "Tool"
    RENDER = "Render"
    DELIVER = "Deliver"
    EDIT = "Edit"
    WORKFLOW_INTEGRATIONS = "WorkflowIntegrations"
    FUSION = "Fusion"
    ROOT = "root"

    @classmethod
    def valid_names(cls) -> set[str]:
        return {t.value for t in cls}


# Common misspellings / near-misses → recommended fix (M6 uses this too).
TARGET_SUGGESTIONS: dict[str, str] = {
    "comp": "Comp",
    "utility": "Utility",
    "tool": "Tool",
    "render": "Render",
    "deliver": "Deliver",
    "edit": "Edit",
    "scripts": "root",
    "fusion": "Fusion",
}


@dataclass
class Compat:
    """Expo-style compatibility axis (min Resolve / min Python versions)."""

    resolve: str | None = None
    python: str | None = None

    def as_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.resolve:
            result["resolve"] = self.resolve
        if self.python:
            result["python"] = self.python
        return result


@dataclass
class Release:
    """Published-artifact source for ``add`` / ``install <spec>``."""

    owner: str = ""
    repo: str = ""
    url: str = ""

    def as_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.owner:
            result["owner"] = self.owner
        if self.repo:
            result["repo"] = self.repo
        if self.url:
            result["url"] = self.url
        return result

    @property
    def github_spec(self) -> str | None:
        if self.owner and self.repo:
            return f"github:{self.owner}/{self.repo}"
        return None


@dataclass
class ConsolidateConfig:
    """Single-file build options (M3)."""

    enabled: bool = True
    output: str | None = None
    entry: str | None = None
    exclude: list[str] = field(default_factory=list)
    no_comment: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "output": self.output,
            "entry": self.entry,
            "exclude": list(self.exclude),
            "no_comment": list(self.no_comment),
        }


@dataclass
class InstallConfig:
    """Copy rules and install destination."""

    as_directory: bool = True
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    to: str = "resolve"  # "resolve" (Fusion Scripts) | "framework" (plugin dir)

    def as_dict(self) -> dict[str, Any]:
        return {
            "as_directory": self.as_directory,
            "include": list(self.include),
            "exclude": list(self.exclude),
            "to": self.to,
        }


@dataclass
class Manifest:
    """A Resolve script manifest (or, with ``kind="extension"``, a plugin)."""

    name: str
    version: str
    author: str = ""
    description: str = ""
    python: str = ""
    package_dir: str = ""
    entrypoint: str | None = None
    id: str | None = None
    compat: Compat = field(default_factory=Compat)
    release: Release = field(default_factory=Release)
    targets: list[str] = field(default_factory=list)
    scripts_root: str = ""
    consolidate: ConsolidateConfig = field(default_factory=ConsolidateConfig)
    dependencies: list[str] = field(default_factory=list)
    install: InstallConfig = field(default_factory=InstallConfig)
    kind: str = "script"  # "script" | "extension" (plugin)

    @property
    def is_plugin(self) -> bool:
        return self.kind == "extension"

    @property
    def default_package_dir(self) -> str:
        """Effective package directory (defaults to the extension root)."""
        return self.package_dir or self.name

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
        }
        for key in ("author", "description", "python", "package_dir", "entrypoint"):
            value = getattr(self, key)
            if value:
                result[key] = value
        if self.id:
            result["id"] = self.id
        if self.compat.as_dict():
            result["compat"] = self.compat.as_dict()
        if self.release.as_dict():
            result["release"] = self.release.as_dict()
        if self.targets:
            result["targets"] = list(self.targets)
        if self.scripts_root:
            result["scripts_root"] = self.scripts_root
        if self.consolidate.enabled or self.consolidate.output or self.consolidate.entry:
            result["consolidate"] = self.consolidate.as_dict()
        if self.dependencies:
            result["dependencies"] = list(self.dependencies)
        if self.install.as_directory or self.install.include or self.install.exclude or self.install.to != "resolve":
            result["install"] = self.install.as_dict()
        if self.kind != "script":
            result["kind"] = self.kind
        return result


def _as_str(value: Any, key: str, source: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestError(f"field '{key}' must be a string, got {type(value).__name__}", path=source)
    return value


def _as_str_list(value: Any, key: str, source: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise ManifestError(f"field '{key}' must be a list of strings", path=source)
    for item in value:
        if not isinstance(item, str):
            raise ManifestError(f"field '{key}' must contain only strings, got {type(item).__name__}", path=source)
    return list(value)


def _as_bool(value: Any, key: str, source: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ManifestError(f"field '{key}' must be a boolean, got {value!r}", path=source)


def _as_dict(value: Any, key: str, source: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError(f"field '{key}' must be an object", path=source)
    return value


def manifest_from_dict(raw: dict[str, Any], source: str = "<manifest>") -> Manifest:
    """Normalize a raw manifest dict (from JSON or XML) into a :class:`Manifest`."""
    if not isinstance(raw, dict):
        raise ManifestError(f"manifest must be a JSON object, got {type(raw).__name__}", path=source)

    name = _as_str(raw.get("name"), "name", source)
    version = _as_str(raw.get("version"), "version", source)
    if not name:
        raise ManifestError("missing required field 'name'", path=source)
    if not version:
        raise ManifestError("missing required field 'version'", path=source)

    compat_raw = _as_dict(raw.get("compat"), "compat", source)
    release_raw = _as_dict(raw.get("release"), "release", source)
    cons_raw = _as_dict(raw.get("consolidate"), "consolidate", source)
    inst_raw = _as_dict(raw.get("install"), "install", source)

    install_to = _as_str(inst_raw.get("to"), "install.to", source) or "resolve"
    if install_to not in {"resolve", "framework"}:
        raise ManifestError(f"install.to must be 'resolve' or 'framework', got {install_to!r}", path=source)

    return Manifest(
        name=name,
        version=version,
        kind=_as_str(raw.get("kind"), "kind", source) or "script",
        author=_as_str(raw.get("author"), "author", source) or "",
        description=_as_str(raw.get("description"), "description", source) or "",
        python=_as_str(raw.get("python"), "python", source) or "",
        package_dir=_as_str(raw.get("package_dir"), "package_dir", source) or "",
        entrypoint=_as_str(raw.get("entrypoint"), "entrypoint", source),
        id=_as_str(raw.get("id"), "id", source),
        compat=Compat(
            resolve=_as_str(compat_raw.get("resolve"), "compat.resolve", source),
            python=_as_str(compat_raw.get("python"), "compat.python", source),
        ),
        release=Release(
            owner=_as_str(release_raw.get("owner"), "release.owner", source) or "",
            repo=_as_str(release_raw.get("repo"), "release.repo", source) or "",
            url=_as_str(release_raw.get("url"), "release.url", source) or "",
        ),
        targets=_as_str_list(raw.get("targets"), "targets", source),
        scripts_root=_as_str(raw.get("scripts_root"), "scripts_root", source) or "",
        consolidate=ConsolidateConfig(
            enabled=_as_bool(cons_raw.get("enabled"), "consolidate.enabled", source, True),
            output=_as_str(cons_raw.get("output"), "consolidate.output", source),
            entry=_as_str(cons_raw.get("entry"), "consolidate.entry", source),
            exclude=_as_str_list(cons_raw.get("exclude"), "consolidate.exclude", source),
            no_comment=_as_str_list(cons_raw.get("no_comment"), "consolidate.no_comment", source),
        ),
        dependencies=_as_str_list(raw.get("dependencies"), "dependencies", source),
        install=InstallConfig(
            as_directory=_as_bool(inst_raw.get("as_directory"), "install.as_directory", source, True),
            include=_as_str_list(inst_raw.get("include"), "install.include", source),
            exclude=_as_str_list(inst_raw.get("exclude"), "install.exclude", source),
            to=install_to,
        ),
    )
