"""ResolveScript — script framework for DaVinci Resolve.

ResolveScript is both a CLI and a normal Python package, so you can drive
every feature directly from a script or an interactive session.

Quick start — create and inspect a new script project::

    import resolve_script as rs

    root, written = rs.scaffold_project(
        "my-tool", destination=".", fmt="json", template="default"
    )
    print(root, written)

    issues = rs.analyze_project(root)
    for issue in issues:
        print(issue)

    cfg = rs.config_from_manifest(root / "resolve-script.manifest.json")
    result = rs.consolidate(cfg)
    print(result.target)      # single-file build
    print(result.sources)     # files folded into the build

Borrow a ``Source`` spec from a known GitHub project::

    import resolve_script as rs

    print(rs.lookup("hello"))          # canonical source for a known name
    values = rs.build_values("my-tool")  # template substition values

Sit scripts in the Resolve environment::

    from resolve_script.sandbox import build_default_env, fake_resolve_module
    from resolve_script.install import install_project

    env = build_default_env()
    fake_resolve_module(env)           # injects a fake ``resolve`` module
    install_project(env, run_smoke=True, root=".")

Every public name is available both at the package root and from its owning
module, e.g. ``resolve_script.consolidate`` is also the top-level
``consolidate`` function.

Subpackages ship their own convenience imports:

* ``resolve_script.manifest``  — manifest model, loaders, validators
* ``resolve_script.sandbox``   — mock Resolve API, smoke runs, REPL
* ``resolve_script.sources``   — archive/git/known-source helpers
* ``resolve_script.install``   — install, registry and target resolution
"""

from __future__ import annotations

from ._version import __version__, get_version

# --- pipeline ----------------------------------------------------------
from .analyze import KNOWN_ROOTS, Analysis, Issue, analyze_project, issues_to_json

# --- config ------------------------------------------------------------
from .config import (
    allow_remote,
    is_editable_install,
    normalize_path,
    plugins_dir,
    python_spec,
    scripts_root_override,
    user_config_dir,
)
from .consolidate import (
    BuildConfig,
    ConsolidateError,
    ConsolidateResult,
    config_from_manifest,
    consolidate,
    summarize,
)

# --- fetch / CLI -------------------------------------------------------
from .fetch import Fetched, FetchError, fetch, fetch_json, sha256_file

# --- install -----------------------------------------------------------
from .install import (
    REGISTRY_REL,
    SCHEMA_VERSION,
    InstalledFile,
    InstallError,
    InstallOptions,
    InstallResult,
    RegistryError,
    add_or_update_entry,
    default_scripts_root,
    discover_entrypoint,
    get_extension,
    install_package,
    install_project,
    read_registry,
    registry_path,
    remove_entry,
    resolve_scripts_root,
    select_files,
    target_dir,
    uninstall_package,
    write_registry,
)

# --- manifest ----------------------------------------------------------
from .manifest import (
    TARGET_SUGGESTIONS,
    Compat,
    ConsolidateConfig,
    InstallConfig,
    Manifest,
    ManifestError,
    Release,
    Target,
    dumps,
    is_valid_semver,
    load_manifest,
    loads,
    manifest_from_dict,
    validate_manifest,
    validate_manifest_or_throw,
    validate_target,
)
from .package import PackageError, PackageResult, package_project

# --- spec / resolver ---------------------------------------------------
from .resolver import (
    Resolved,
    ResolveError,
    lockfile_satisfies,
    resolve_spec,
)

# --- sandbox -----------------------------------------------------------
from .sandbox import (
    DEFAULT_PROJECT,
    FUSION_SCRIPT_MODULE,
    FakeClip,
    FakeComp,
    FakeFolder,
    FakeFusion,
    FakeKey,
    FakeMediaPool,
    FakeMediaPoolItem,
    FakeProject,
    FakeProjectManager,
    FakeResolve,
    FakeSpline,
    FakeStroke,
    FakeTimeline,
    FakeTool,
    SmokeCheck,
    SmokeResult,
    build_default_env,
    default_namespace,
    discover_exports,
    fake_resolve_module,
    install_fake_resolve,
    load_built_module,
    load_source_module,
    purge_module,
    run_smoke,
    start_repl,
)

# --- scaffold ----------------------------------------------------------
from .scaffold import (
    DEFAULT_VERSION,
    TEMPLATES_DIR,
    ScaffoldError,
    build_values,
    normalize_name,
    render,
    scaffold_project,
)
from .semver import SemVerError, Version, matches, pick_best

# --- sources -----------------------------------------------------------
from .sources import (
    ARCHIVE_SUFFIXES,
    CONVENTIONS,
    ArchiveError,
    GitSourceError,
    ReleaseError,
    ReleaseSpec,
    asset_download_url,
    canonical_source,
    codeload_url,
    default_branch,
    download_github,
    is_archive_path,
    known_names,
    list_tags,
    lookup,
    make_archive,
    resolve_tag,
    search,
    tags_have_version,
    unpack_archive,
)
from .spec import Spec, SpecError, parse_specifier
from .workspace import (
    WORKSPACE_FILE,
    WorkspaceError,
    add_dependency,
    has_workspace,
    read_workspace,
    remove_dependency,
    save,
    workspace_path,
    write_workspace,
)

__all__ = [
    # version
    "__version__",
    "get_version",
    # manifest
    "Compat",
    "ConsolidateConfig",
    "InstallConfig",
    "Manifest",
    "ManifestError",
    "Release",
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
    # sources
    "ARCHIVE_SUFFIXES",
    "CONVENTIONS",
    "ArchiveError",
    "GitSourceError",
    "ReleaseError",
    "ReleaseSpec",
    "asset_download_url",
    "canonical_source",
    "codeload_url",
    "default_branch",
    "download_github",
    "is_archive_path",
    "known_names",
    "list_tags",
    "lookup",
    "make_archive",
    "resolve_tag",
    "search",
    "tags_have_version",
    "unpack_archive",
    # install
    "REGISTRY_REL",
    "SCHEMA_VERSION",
    "InstallError",
    "InstallOptions",
    "InstallResult",
    "InstalledFile",
    "RegistryError",
    "add_or_update_entry",
    "default_scripts_root",
    "discover_entrypoint",
    "get_extension",
    "install_package",
    "install_project",
    "read_registry",
    "registry_path",
    "remove_entry",
    "resolve_scripts_root",
    "select_files",
    "target_dir",
    "uninstall_package",
    "write_registry",
    # sandbox
    "DEFAULT_PROJECT",
    "FUSION_SCRIPT_MODULE",
    "FakeClip",
    "FakeComp",
    "FakeFolder",
    "FakeFusion",
    "FakeKey",
    "FakeMediaPool",
    "FakeMediaPoolItem",
    "FakeProject",
    "FakeProjectManager",
    "FakeResolve",
    "FakeSpline",
    "FakeStroke",
    "FakeTimeline",
    "FakeTool",
    "SmokeCheck",
    "SmokeResult",
    "build_default_env",
    "default_namespace",
    "discover_exports",
    "fake_resolve_module",
    "install_fake_resolve",
    "load_built_module",
    "load_source_module",
    "purge_module",
    "run_smoke",
    "start_repl",
    # config
    "allow_remote",
    "is_editable_install",
    "normalize_path",
    "plugins_dir",
    "python_spec",
    "scripts_root_override",
    "user_config_dir",
    # spec / resolver
    "ResolveError",
    "Resolved",
    "lockfile_satisfies",
    "resolve_spec",
    "SemVerError",
    "Version",
    "matches",
    "pick_best",
    "Spec",
    "SpecError",
    "parse_specifier",
    "WORKSPACE_FILE",
    "WorkspaceError",
    "add_dependency",
    "has_workspace",
    "read_workspace",
    "remove_dependency",
    "save",
    "workspace_path",
    "write_workspace",
    # pipeline
    "KNOWN_ROOTS",
    "Analysis",
    "Issue",
    "analyze_project",
    "issues_to_json",
    "BuildConfig",
    "ConsolidateError",
    "ConsolidateResult",
    "config_from_manifest",
    "consolidate",
    "summarize",
    "PackageError",
    "PackageResult",
    "package_project",
    # scaffold
    "DEFAULT_VERSION",
    "TEMPLATES_DIR",
    "ScaffoldError",
    "build_values",
    "normalize_name",
    "render",
    "scaffold_project",
    # fetch
    "Fetched",
    "FetchError",
    "fetch",
    "fetch_json",
    "sha256_file",
]
