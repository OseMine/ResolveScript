"""Plugin manifest and entry dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..manifest.model import RequiresConfig


@dataclass
class PluginManifest:
    """Plugin metadata (loaded from plugin.json in the plugin package)."""

    name: str
    version: str
    kind: str = "extension"
    extension_kind: str = ""
    provides: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    hooks: dict[str, str] = field(default_factory=dict)
    templates: list[str] = field(default_factory=list)
    requires: RequiresConfig = field(default_factory=lambda: RequiresConfig())
    entry: str = ""

    def check_requires(self) -> None:
        """Verify environment satisfies requirements, raise PluginError if not."""
        if self.requires.resolvescript:
            from ResolveScript import __version__ as current_version
            from ResolveScript.semver import Version, matches
            if not matches(Version.parse(current_version), self.requires.resolvescript):
                from .errors import PluginError
                raise PluginError(
                    f"plugin requires resolvescript {self.requires.resolvescript}, "
                    f"have {current_version}"
                )
        if self.requires.python:
            import sys
            py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            from ResolveScript.semver import Version, matches
            if not matches(Version.parse(py_version), self.requires.python):
                from .errors import PluginError
                raise PluginError(
                    f"plugin requires python {self.requires.python}, have {py_version}"
                )


@dataclass
class PluginEntry:
    """Installed plugin metadata (stored in plugin registry)."""

    name: str
    version: str
    path: str
    manifest: PluginManifest
    installed_at: str
    source: str = ""
    integrity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "path": self.path,
            "source": self.source,
            "integrity": self.integrity,
            "manifest": {
                "name": self.manifest.name,
                "version": self.manifest.version,
                "kind": self.manifest.kind,
                "extension_kind": self.manifest.extension_kind,
                "provides": self.manifest.provides,
                "commands": self.manifest.commands,
                "sources": self.manifest.sources,
                "hooks": self.manifest.hooks,
                "templates": self.manifest.templates,
                "requires": self.manifest.requires.as_dict(),
                "entry": self.manifest.entry,
            },
            "installed_at": self.installed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginEntry:
        manifest = PluginManifest(
            name=data["manifest"]["name"],
            version=data["manifest"]["version"],
            kind=data["manifest"].get("kind", "extension"),
            extension_kind=data["manifest"].get("extension_kind", ""),
            provides=data["manifest"].get("provides", []),
            commands=data["manifest"].get("commands", []),
            sources=data["manifest"].get("sources", []),
            hooks=data["manifest"].get("hooks", {}),
            templates=data["manifest"].get("templates", []),
            requires=RequiresConfig(**data["manifest"].get("requires", {})),
            entry=data["manifest"].get("entry", ""),
        )
        return cls(
            name=data["name"],
            version=data["version"],
            path=data["path"],
            manifest=manifest,
            installed_at=data.get("installed_at", ""),
            source=data.get("source", ""),
            integrity=data.get("integrity", ""),
        )
