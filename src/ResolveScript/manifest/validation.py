"""Semantic validation of a parsed manifest.

The readers guarantee *shape* (correct types, required fields). This module
checks *meaning*: version format, target whitelist, install-path sanity, and
plugin gating. Returns a list of human-readable errors; an empty list means ok.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from .model import TARGET_SUGGESTIONS, Manifest, Target

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

_REQUIRED = ("name", "version")


def is_valid_semver(version: str) -> bool:
    return bool(_SEMVER.match(version.strip()))


def validate_target(target: str) -> str | None:
    """Return an error string for an unknown target name, or ``None`` if ok."""
    if target in Target.valid_names():
        return None
    suggestion = TARGET_SUGGESTIONS.get(target.lower())
    hint = f" (did you mean '{suggestion}'?)" if suggestion else ""
    return f"unknown target '{target}'{hint}; valid: {', '.join(sorted(Target.valid_names()))}"


def _path_is_sane(output: str | None, field_name: str) -> list[str]:
    if not output:
        return []
    path = PurePosixPath(output.replace("\\", "/"))
    if path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        return [f"{field_name} must be a relative path with no '.'/'..' segments (got '{output}')"]
    return []


def validate_manifest(manifest: Manifest) -> list[str]:
    """Return a list of validation errors for :class:`Manifest`."""
    errors: list[str] = []

    for field_name in _REQUIRED:
        if not getattr(manifest, field_name):
            errors.append(f"missing required field '{field_name}'")

    if manifest.version and not is_valid_semver(manifest.version):
        errors.append(f"invalid version '{manifest.version}' (expected strict semver, e.g. 1.2.3, 1.2.3-rc1)")

    if manifest.targets:
        for target in manifest.targets:
            error = validate_target(target)
            if error:
                errors.append(error)
    elif manifest.kind == "script":
        errors.append("no 'targets' declared (e.g. Comp/Utility) for a Resolve script")

    errors.extend(_path_is_sane(manifest.consolidate.output, "consolidate.output"))
    errors.extend(_path_is_sane(manifest.entrypoint, "entrypoint"))

    if manifest.consolidate.enabled and not manifest.consolidate.entry:
        errors.append("consolidate.enabled is true but 'consolidate.entry' is not set (package entry module)")

    if manifest.kind == "extension" and manifest.release.github_spec is None and not manifest.release.url:
        errors.append("plugin manifests need a source: set 'release.owner/repo' or 'release.url'")

    return errors


def validate_manifest_or_throw(manifest: Manifest) -> None:
    """Raise ``ValueError`` on the first validation error (for callers)."""
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError(errors[0])
