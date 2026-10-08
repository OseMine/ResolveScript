"""``resolvescript doctor`` - environment and project self-diagnosis.

Answers the support questions that otherwise cost hours: is the Scripts root
where we think it is, does the project manifest parse, is the registry intact,
are network/env overrides in effect. Every check is defensive - a check that
itself raises is reported as a failure, never crashes the command.

Library use::

    from ResolveScript.doctor import run_checks

    for check in run_checks(cwd=Path.cwd()):
        print(check.status, check.name, check.detail)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ._version import __version__
from .config import (
    ENV_ALLOW_REMOTE,
    ENV_SCRIPTS_ROOT,
    allow_remote,
    is_editable_install,
    python_spec,
    resolve_env,
)

OK = "ok"
WARN = "warn"
FAIL = "fail"

#: Env vars worth surfacing: our own overrides first, then Resolve's own
#: scripting variables (informational - user scripts and launchers read them).
REPORTED_ENV = (
    ENV_SCRIPTS_ROOT,
    "RESOLVESCRIPT_WORKFLOWS_ROOT",
    "RESOLVESCRIPT_FUSES_ROOT",
    "RESOLVESCRIPT_FUSION_PLUGINS_ROOT",
    ENV_ALLOW_REMOTE,
    "RESOLVESCRIPT_ALLOW_NETWORK",
    "RESOLVE_SCRIPT_API",
    "RESOLVE_SCRIPT_LIB",
    "RESOLVE_SCRIPT_PATH",
)

CHECK_ORDER = (
    "interpreter",
    "templates",
    "scripts-root",
    "environment",
    "manifest",
    "workspace",
    "registry",
)


@dataclass(frozen=True)
class Check:
    """One diagnostic result: ``status`` is ``"ok"``, ``"warn"`` or ``"fail"``."""

    name: str
    status: str
    detail: str

    @property
    def failed(self) -> bool:
        return self.status == FAIL

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def run_checks(
    scripts_root: Path | None = None,
    cwd: Path | None = None,
) -> list[Check]:
    """Run every diagnostic and return the results in ``CHECK_ORDER``.

    ``scripts_root`` is an explicit override (the ``--scripts-root`` flag);
    when omitted the usual override > env > OS-default discovery applies.
    A check that raises is reported as ``fail`` - this never raises.
    """
    from .install.discovery import resolve_scripts_root
    from .scaffold import TEMPLATES_DIR

    cwd = cwd or Path.cwd()
    root = resolve_scripts_root(scripts_root)
    root_source = (
        "--scripts-root"
        if scripts_root is not None
        else "RESOLVESCRIPT_SCRIPTS_ROOT"
        if resolve_env(ENV_SCRIPTS_ROOT)
        else "OS default"
    )

    def guarded(name: str, func) -> Check:
        try:
            return func()
        except Exception as exc:  # diagnostics must not crash
            return Check(name, FAIL, f"{type(exc).__name__}: {exc}")

    return [
        guarded("interpreter", _check_interpreter),
        guarded("templates", lambda: _check_templates(TEMPLATES_DIR)),
        guarded("scripts-root", lambda: _check_scripts_root(root, root_source)),
        guarded("environment", _check_environment),
        guarded("manifest", lambda: _check_manifest(cwd)),
        guarded("workspace", lambda: _check_workspace(cwd)),
        guarded("registry", lambda: _check_registry(root)),
    ]


def issues_json(checks: list[Check]) -> str:
    payload = {
        "checks": [c.as_dict() for c in checks],
        "warnings": sum(1 for c in checks if c.status == WARN),
        "failures": sum(1 for c in checks if c.status == FAIL),
    }
    return json.dumps(payload, indent=2)


def _check_interpreter() -> Check:
    where = "source checkout" if is_editable_install() else "installed package"
    return Check("interpreter", OK, f"{python_spec()} (resolvescript {__version__}, {where})")


def _check_templates(templates_dir: Path) -> Check:
    if not templates_dir.is_dir():
        return Check(
            "templates",
            FAIL,
            f"{templates_dir} is missing - broken install (package-data not shipped?)",
        )
    count = sum(1 for entry in templates_dir.iterdir() if entry.is_dir())
    return Check("templates", OK, f"{count} template(s) in {templates_dir}")


def _check_scripts_root(root: Path, source: str) -> Check:
    if not root.exists():
        return Check(
            "scripts-root",
            WARN,
            f"{root} ({source}) - missing; launch DaVinci Resolve once or pass --scripts-root",
        )
    if not root.is_dir():
        return Check("scripts-root", FAIL, f"{root} ({source}) - exists but is not a directory")
    if not os.access(root, os.W_OK):
        return Check("scripts-root", FAIL, f"{root} ({source}) - not writable")
    targets = sorted(entry.name for entry in root.iterdir() if entry.is_dir())
    listed = ", ".join(targets) if targets else "no target folders yet"
    return Check("scripts-root", OK, f"{root} ({source}) - {listed}")


def _check_environment() -> Check:
    set_vars = [f"{name}={value}" for name in REPORTED_ENV if (value := resolve_env(name))]
    if not set_vars:
        return Check("environment", OK, "no RESOLVESCRIPT_*/RESOLVE_* overrides set")
    if not allow_remote():
        return Check("environment", WARN, "; ".join(set_vars) + " - remote installs are DISABLED")
    return Check("environment", OK, "; ".join(set_vars))


def _check_manifest(cwd: Path) -> Check:
    manifest_path = cwd / "manifest.json"
    if not manifest_path.is_file():
        manifest_path = cwd / "manifest.xml"
    if not manifest_path.is_file():
        return Check("manifest", OK, f"no manifest in {cwd} (not a script project)")
    from .manifest import load_manifest, validate_manifest_or_throw

    manifest = load_manifest(manifest_path)
    validate_manifest_or_throw(manifest)
    targets = ", ".join(manifest.targets) or "none"
    return Check("manifest", OK, f"{manifest.name} {manifest.version} - targets: {targets}")


def _check_workspace(cwd: Path) -> Check:
    from .workspace import WORKSPACE_FILE, read_workspace

    path = cwd / WORKSPACE_FILE
    if not path.is_file():
        return Check("workspace", OK, f"no {WORKSPACE_FILE} in {cwd}")
    data = read_workspace(cwd)
    deps = data.get("dependencies", {})
    return Check("workspace", OK, f"{WORKSPACE_FILE}: {len(deps)} recorded dependency(ies)")


def _check_registry(root: Path) -> Check:
    from .install.registry import read_registry, registry_path

    path = registry_path(root)
    if not path.is_file():
        return Check("registry", OK, f"no registry at {path} (nothing installed yet)")
    registry = read_registry(root)
    extensions = registry.get("extensions", {})
    names = ", ".join(sorted(extensions)) or "none"
    return Check("registry", OK, f"{len(extensions)} installed: {names}")


__all__ = ["Check", "FAIL", "OK", "WARN", "CHECK_ORDER", "issues_json", "run_checks"]
