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
class RequiresConfig:
    """Version gating for plugins."""

    resolvescript: str = ""
    python: str = ""

    def as_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.resolvescript:
            result["resolvescript"] = self.resolvescript
        if self.python:
            result["python"] = self.python
        return result

    def is_satisfied(self) -> bool:
        """Check if current environment satisfies requirements."""
        import sys

        from .. import __version__ as current_version
        from ..semver import Version, matches

        if self.resolvescript and not matches(Version.parse(current_version), self.resolvescript):
            return False
        if self.python:
            py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
            if not matches(Version.parse(py_version), self.python):
                return False
        return True


@dataclass
class ExtensionConfig:
    """Plugin-specific configuration (only used when kind == "extension")."""

    extension_kind: str = ""  # "commands", "sources", "hooks", "templates", "provides"
    provides: list[str] = field(default_factory=list)  # e.g. ["mocks:resolve19"]
    commands: list[str] = field(default_factory=list)  # new CLI commands
    sources: list[str] = field(default_factory=list)   # new specifier sources
    hooks: dict[str, str] = field(default_factory=dict)  # lifecycle hooks
    templates: list[str] = field(default_factory=list)  # new scaffold templates
    requires: RequiresConfig = field(default_factory=RequiresConfig)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.extension_kind:
            result["extension_kind"] = self.extension_kind
        if self.provides:
            result["provides"] = list(self.provides)
        if self.commands:
            result["commands"] = list(self.commands)
        if self.sources:
            result["sources"] = list(self.sources)
        if self.hooks:
            result["hooks"] = dict(self.hooks)
        if self.templates:
            result["templates"] = list(self.templates)
        if self.requires.as_dict():
            result["requires"] = self.requires.as_dict()
        return result


@dataclass
class WorkflowConfig:
    """Workflow Integration metadata (only used when kind == "workflow").

    These fields mirror :class:`ResolveScript.workflow.Integration`. They are
    duplicated here rather than imported because a manifest is read without
    the project being importable — the point of the block is to describe the
    integration to tooling that only has the manifest.
    """

    id: str = ""  # reverse-DNS plugin id, also the installed folder name
    name: str = ""  # the menu label under Workspace > Workflow Integrations
    version: str = ""
    description: str = ""
    entrypoint: str = ""  # "my_pkg.workflow:INTEGRATION"
    callbacks: list[str] = field(default_factory=list)  # e.g. ["RenderStart"]
    electron: bool = True  # also build the Electron plugin shell

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in ("id", "name", "version", "description", "entrypoint"):
            value = getattr(self, key)
            if value:
                result[key] = value
        if self.callbacks:
            result["callbacks"] = list(self.callbacks)
        if not self.electron:
            result["electron"] = False
        return result

    @property
    def is_empty(self) -> bool:
        return not self.as_dict()


@dataclass
class FusionConfig:
    """Fusion tool metadata (only used when kind == "fuse").

    A *fuse* is Fusion's scripted plugin: a single Lua file with a ``.fuse``
    extension that Fusion compiles on the fly, so there is nothing to compile
    here. These fields mirror :class:`ResolveScript.fuse.Fuse` and are
    duplicated for the same reason as :class:`WorkflowConfig` — a manifest is
    read without the project being importable.

    A *compiled* Fusion plugin (``.plugin``) is a native binary this tool
    cannot build, so ``binary`` records one being carried rather than made.
    """

    entrypoint: str = ""  # "my_pkg.fuse:FUSE" — where the Fuse is declared
    class_name: str = ""  # the FuRegisterClass name; also the .fuse file name
    display_name: str = ""  # REGS_Name
    category: str = ""  # REGS_Category, backslash-separated
    icon_string: str = ""  # REGS_OpIconString, the 3-letter search code
    description: str = ""  # REGS_OpDescription
    tool_type: str = "CT_Tool"  # CT_Tool | CT_SourceTool | CT_Operator
    binary: str = ""  # a prebuilt .plugin file to deploy, not to build

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in (
            "entrypoint",
            "class_name",
            "display_name",
            "category",
            "icon_string",
            "description",
            "tool_type",
            "binary",
        ):
            value = getattr(self, key)
            if value:
                result[key] = value
        return result

    @property
    def is_empty(self) -> bool:
        return not self.as_dict()


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
    kind: str = "script"  # "script" | "extension" (plugin) | "workflow" | "fuse"
    extension: ExtensionConfig = field(default_factory=ExtensionConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    fusion: FusionConfig = field(default_factory=FusionConfig)

    @property
    def is_plugin(self) -> bool:
        return self.kind == "extension"

    @property
    def is_fuse(self) -> bool:
        """Whether this manifest describes a Fusion fuse.

        Like a workflow, a fuse is installed into a Fusion directory rather
        than the Scripts root, so it has no meaningful ``targets`` either.
        """
        return self.kind == "fuse"

    @property
    def is_workflow(self) -> bool:
        """Whether this manifest describes a Workflow Integration.

        A workflow is *not* installed into the Scripts root — Resolve scans a
        separate plugins directory — so it also has no meaningful ``targets``.
        """
        return self.kind == "workflow"

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
        if self.is_plugin and self.extension.as_dict():
            result["extension"] = self.extension.as_dict()
        if self.is_workflow and self.workflow.as_dict():
            result["workflow"] = self.workflow.as_dict()
        if self.is_fuse and self.fusion.as_dict():
            result["fusion"] = self.fusion.as_dict()
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


def _as_str_dict(value: Any, key: str, source: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError(f"field '{key}' must be an object", path=source)
    result: dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(k, str):
            raise ManifestError(f"field '{key}' keys must be strings", path=source)
        if not isinstance(v, str):
            raise ManifestError(f"field '{key}.{k}' must be a string, got {type(v).__name__}", path=source)
        result[k] = v
    return result


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
    ext_raw = _as_dict(raw.get("extension"), "extension", source)
    wf_raw = _as_dict(raw.get("workflow"), "workflow", source)
    fu_raw = _as_dict(raw.get("fusion"), "fusion", source)

    install_to = _as_str(inst_raw.get("to"), "install.to", source) or "resolve"
    if install_to not in {"resolve", "framework"}:
        raise ManifestError(f"install.to must be 'resolve' or 'framework', got {install_to!r}", path=source)

    # Parse extension config (only used when kind == "extension")
    ext_raw_requires = _as_dict(ext_raw.get("requires"), "extension.requires", source)
    ext_requires = RequiresConfig(
        resolvescript=_as_str(ext_raw_requires.get("resolvescript"), "extension.requires.resolvescript", source) or "",
        python=_as_str(ext_raw_requires.get("python"), "extension.requires.python", source) or "",
    )
    extension = ExtensionConfig(
        extension_kind=_as_str(ext_raw.get("extension_kind"), "extension.extension_kind", source) or "",
        provides=_as_str_list(ext_raw.get("provides"), "extension.provides", source),
        commands=_as_str_list(ext_raw.get("commands"), "extension.commands", source),
        sources=_as_str_list(ext_raw.get("sources"), "extension.sources", source),
        hooks=_as_str_dict(ext_raw.get("hooks"), "extension.hooks", source),
        templates=_as_str_list(ext_raw.get("templates"), "extension.templates", source),
        requires=ext_requires,
    )

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
        extension=extension,
        workflow=WorkflowConfig(
            id=_as_str(wf_raw.get("id"), "workflow.id", source) or "",
            name=_as_str(wf_raw.get("name"), "workflow.name", source) or "",
            version=_as_str(wf_raw.get("version"), "workflow.version", source) or "",
            description=_as_str(wf_raw.get("description"), "workflow.description", source) or "",
            entrypoint=_as_str(wf_raw.get("entrypoint"), "workflow.entrypoint", source) or "",
            callbacks=_as_str_list(wf_raw.get("callbacks"), "workflow.callbacks", source),
            electron=_as_bool(wf_raw.get("electron"), "workflow.electron", source, True),
        ),
        fusion=FusionConfig(
            entrypoint=_as_str(fu_raw.get("entrypoint"), "fusion.entrypoint", source) or "",
            class_name=_as_str(fu_raw.get("class_name"), "fusion.class_name", source) or "",
            display_name=_as_str(fu_raw.get("display_name"), "fusion.display_name", source) or "",
            category=_as_str(fu_raw.get("category"), "fusion.category", source) or "",
            icon_string=_as_str(fu_raw.get("icon_string"), "fusion.icon_string", source) or "",
            description=_as_str(fu_raw.get("description"), "fusion.description", source) or "",
            tool_type=_as_str(fu_raw.get("tool_type"), "fusion.tool_type", source) or "CT_Tool",
            binary=_as_str(fu_raw.get("binary"), "fusion.binary", source) or "",
        ),
    )
