"""Library framework API (M18): rich top-level ``resolve_script`` surface.

A ResolveScript project is usable both as a CLI and as an ordinary Python
package. These tests pin the public API exported from the package root and
exercise a complete scripted pipeline — scaffold, analyze, consolidate,
package — using only top-level names, the way an app script would.
"""

from __future__ import annotations

import importlib

import pytest

import ResolveScript as rs

FUNCTION_EXPORTS = {
    # manifest
    "dumps", "is_valid_semver", "load_manifest", "loads",
    "manifest_from_dict", "validate_manifest", "validate_manifest_or_throw",
    "validate_target", "get_version",
    # sources
    "asset_download_url", "canonical_source", "codeload_url",
    "default_branch", "download_github", "is_archive_path", "known_names",
    "list_tags", "lookup", "make_archive", "resolve_tag", "search",
    "tags_have_version", "unpack_archive",
    # sandbox
    "build_default_env", "default_namespace", "discover_exports",
    "fake_resolve_module", "install_fake_resolve", "load_built_module",
    "load_source_module", "purge_module", "run_smoke", "start_repl",
    # config
    "allow_remote", "is_editable_install", "normalize_path", "plugins_dir",
    "python_spec", "scripts_root_override", "user_config_dir",
    # spec / resolver / workspace
    "lockfile_satisfies", "resolve_spec", "matches", "pick_best",
    "parse_specifier", "add_dependency", "has_workspace", "read_workspace",
    "remove_dependency", "save", "workspace_path", "write_workspace",
    # pipeline
    "analyze_project", "issues_to_json", "config_from_manifest", "consolidate",
    "summarize", "package_project",
    # scaffold
    "build_values", "normalize_name", "render", "scaffold_project",
    # fetch
    "fetch", "fetch_json", "sha256_file",
    # install
    "add_or_update_entry", "default_scripts_root", "discover_entrypoint",
    "get_extension", "install_package", "install_project", "read_registry",
    "registry_path", "remove_entry", "resolve_scripts_root", "select_files",
    "target_dir", "uninstall_package", "write_registry",
    # plugins
    "discover_plugins", "install_plugin", "list_plugins", "load_plugin_module",
    "register_plugin_commands", "uninstall_plugin",
}

CLASS_EXPORTS = {
    # errors
    "ResolveScriptError",
    # manifest
    "Compat", "ConsolidateConfig", "ExtensionConfig", "InstallConfig", "Manifest",
    "ManifestError", "Release", "Target",
    # sources
    "ArchiveError", "GitSourceError", "ReleaseError", "ReleaseSpec",
    # sandbox
    "FakeClip", "FakeComp", "FakeFolder", "FakeFusion", "FakeKey",
    "FakeMediaPool", "FakeMediaPoolItem", "FakeProject",
    "FakeProjectManager", "FakeResolve", "FakeSpline", "FakeStroke",
    "FakeTimeline", "FakeTool", "SmokeCheck", "SmokeResult",
    # spec / resolver / workspace / semver
    "ResolveError", "Resolved", "SemVerError", "Version", "Spec",
    "SpecError", "WorkspaceError",
    # pipeline
    "Analysis", "BuildConfig", "ConsolidateError", "ConsolidateResult",
    "Issue", "PackageError", "PackageResult",
    # scaffold
    "ScaffoldError",
    # fetch
    "Fetched", "FetchError",
    # install
    "InstallError", "InstallOptions", "InstallResult", "InstalledFile",
    "RegistryError",
    # plugins
    "PluginEntry", "PluginError", "PluginManifest", "PluginRegistry", "RequiresConfig",
}


def test_all_names_resolve() -> None:
    """Every name in ``__all__`` is an attribute of the package root."""
    missing = [name for name in rs.__all__ if not hasattr(rs, name)]
    assert missing == []


CONSTANT_EXPORTS = {
    "ARCHIVE_SUFFIXES", "CONVENTIONS", "DEFAULT_PROJECT", "DEFAULT_VERSION",
    "FUSION_SCRIPT_MODULE", "KNOWN_ROOTS", "REGISTRY_REL", "SCHEMA_VERSION",
    "TARGET_SUGGESTIONS", "TEMPLATES_DIR", "WORKSPACE_FILE",
    "ENV_ALLOW_REMOTE", "ENV_FUSES_ROOT", "ENV_FUSION_PLUGINS_ROOT",
    "ENV_SCRIPTS_ROOT", "ENV_WORKFLOWS_ROOT",
}


def test_all_classifies_exports() -> None:
    """Exported names are the union of the documented function and class sets."""
    all_names = set(rs.__all__) - {"__version__"}
    assert all_names == FUNCTION_EXPORTS | CLASS_EXPORTS | CONSTANT_EXPORTS


def test_exported_functions_are_functions() -> None:
    for name in sorted(FUNCTION_EXPORTS):
        assert callable(getattr(rs, name)), name


def test_exported_classes_are_classes() -> None:
    for name in sorted(CLASS_EXPORTS):
        assert isinstance(getattr(rs, name), type), name


def test_version() -> None:
    assert rs.__version__ == "1.0.2"
    assert rs.get_version() == rs.__version__


def test_submodule_imports_still_work() -> None:
    """Deep imports used by real scripts keep resolving after the re-exports."""
    for dotted in (
        "ResolveScript.consolidate",
        "ResolveScript.fetch",
        "ResolveScript.manifest",
        "ResolveScript.install",
        "ResolveScript.sandbox",
        "ResolveScript.sources",
    ):
        assert importlib.import_module(dotted) is not None
    with pytest.raises(ImportError):
        importlib.import_module("ResolveScript.definitely_not_a_module")


def test_scripted_pipeline(tmp_path) -> None:
    """scaffold -> analyze -> consolidate -> package via top-level API."""
    root, written = rs.scaffold_project("movie_tools", destination=tmp_path)
    assert root.is_dir()
    assert "manifest.json" in written

    analysis = rs.analyze_project(root)
    assert isinstance(analysis, rs.Analysis)
    assert isinstance(analysis.issues, list)
    for issue in analysis.issues:
        assert isinstance(issue, rs.Issue)

    manifest = rs.load_manifest(root / "manifest.json")
    assert isinstance(manifest, rs.Manifest)
    assert manifest.name == "movie_tools"
    assert rs.validate_manifest(manifest) == []

    cfg = rs.config_from_manifest(root, manifest)
    assert isinstance(cfg, rs.BuildConfig)
    result = rs.consolidate(cfg)
    assert isinstance(result, rs.ConsolidateResult)
    assert result.output.is_file()
    assert "Consolidated" in rs.summarize(result, cfg)

    pkg = rs.package_project(root)
    assert isinstance(pkg, rs.PackageResult)
    assert pkg.archive.is_file()


def test_scripted_pipeline_xml(tmp_path) -> None:
    root, _ = rs.scaffold_project("menu_ext", destination=tmp_path, fmt="xml")
    manifest = rs.load_manifest(root / "manifest.xml")
    assert manifest.name == "menu_ext"
    assert isinstance(manifest, rs.Manifest)


def test_fetch_helpers_exist() -> None:
    assert rs.FetchError
    assert rs.Fetched
    assert callable(rs.fetch)
    assert callable(rs.fetch_json)
    assert callable(rs.sha256_file)


def test_network_gate() -> None:
    assert rs.allow_remote() is True


def test_known_sources_table() -> None:
    names = rs.known_names()
    assert "hello" in names

    hit = rs.lookup("hello")
    assert isinstance(hit, dict)
    assert hit["source"].startswith("github:")

    result = rs.search("hello")
    assert isinstance(result, list)
    assert all(isinstance(item, dict) for item in result)


def test_build_values_direct() -> None:
    values = rs.build_values("my-tool", version="1.2.3")
    assert values["NAME"] == "my-tool"
    assert values["VERSION"] == "1.2.3"
    assert values["RESOLVESCRIPT_VERSION"] == rs.get_version()
