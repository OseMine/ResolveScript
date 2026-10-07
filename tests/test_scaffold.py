"""Scaffolder tests (M2)."""

from __future__ import annotations

import importlib
import sys

import pytest

from ResolveScript.cli import main
from ResolveScript.manifest.json_reader import load_manifest
from ResolveScript.manifest.validation import validate_manifest
from ResolveScript.scaffold import (
    ScaffoldError,
    _walk_templates,
    normalize_name,
    render,
    scaffold_project,
)


def test_normalize_name() -> None:
    assert normalize_name("my_roto_tools") == "my_roto_tools"
    assert normalize_name("My Roto Tools!") == "My_Roto_Tools"
    with pytest.raises(ScaffoldError):
        normalize_name("123")


def test_render_substitutes_and_preserves() -> None:
    out = render("@NAME@ hello @NAME@ @UNKNOWN@", {"NAME": "x"})
    assert out == "x hello x @UNKNOWN@"


def test_scaffold_json_project(tmp_path) -> None:
    root, written = scaffold_project("my_tool", destination=tmp_path)
    assert (root / "manifest.json").exists()
    assert (root / "my_tool" / "__init__.py").is_file()
    assert (root / "my_tool_main.py").is_file()
    assert (root / "tests" / "test_smoke.py").is_file()
    assert not (root / "manifest.xml").exists()
    assert "manifest.json" in {str(p) for p in written}


def test_scaffold_xml_project(tmp_path) -> None:
    root, written = scaffold_project("my_tool", destination=tmp_path, fmt="xml")
    assert (root / "manifest.xml").exists()
    assert not (root / "manifest.json").exists()
    labels = {str(p) for p in written}
    assert "manifest.xml" in labels


def test_scaffolded_manifest_is_valid(tmp_path) -> None:
    root, _ = scaffold_project("my_tool", destination=tmp_path)
    manifest = load_manifest(root / "manifest.json")
    assert manifest.name == "my_tool"
    assert manifest.version == "0.1.0"
    assert manifest.consolidate.entry == "my_tool/__init__.py"
    assert manifest.consolidate.output == "my_tool.py"
    assert validate_manifest(manifest) == []


def test_scaffolded_project_imports_and_runs(tmp_path) -> None:
    root, _ = scaffold_project("my_tool", destination=tmp_path)
    sys.path.insert(0, str(root))
    try:
        pkg = importlib.import_module("my_tool")
        assert pkg.hello() == "Hello from my_tool!"
    finally:
        sys.path.pop(0)


def test_scaffold_refuses_nonempty_dir(tmp_path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ScaffoldError, match="not empty"):
        scaffold_project("occupied", destination=tmp_path)


def test_scaffold_unknown_template(tmp_path) -> None:
    with pytest.raises(ScaffoldError, match="unknown template"):
        scaffold_project("t", destination=tmp_path, template="toolkit")


def test_scaffold_workflow_template(tmp_path) -> None:
    """Test workflow template creates proper workflow integration project."""
    root, written = scaffold_project("my_workflow", destination=tmp_path, template="workflow")

    assert (root / "manifest.json").exists()
    assert (root / "my_workflow" / "__init__.py").is_file()
    assert (root / "my_workflow" / "workflow.py").is_file()
    assert (root / "my_workflow_workflow.py").is_file()
    assert (root / "tests" / "test_smoke.py").is_file()
    assert not (root / "manifest.xml").exists()

    manifest = load_manifest(root / "manifest.json")
    assert manifest.name == "my_workflow"
    assert manifest.kind == "workflow"
    assert manifest.is_workflow is True
    # A workflow integration is loaded from Resolve's Workflow Integration
    # Plugins directory, not the Scripts root, so it declares no `targets` —
    # there is no WorkflowIntegrations folder under Fusion/Scripts.
    assert manifest.targets == []
    assert manifest.workflow.id == "com.resolvescript.myworkflow"
    assert manifest.workflow.name == "My Workflow"
    assert manifest.workflow.entrypoint == "my_workflow.workflow:INTEGRATION"


def test_scaffold_pydavinci_template(tmp_path) -> None:
    """Test pydavinci template creates project with pydavinci dependency."""
    root, written = scaffold_project("my_tool", destination=tmp_path, template="pydavinci")

    assert (root / "manifest.json").exists()
    manifest = load_manifest(root / "manifest.json")
    assert "pydavinci>=0.2.3" in manifest.dependencies


def test_scaffold_davinci_rest_template(tmp_path) -> None:
    """Test davinci-rest template creates project with davinci-rest dependency."""
    root, written = scaffold_project("my_tool", destination=tmp_path, template="davinci-rest")

    assert (root / "manifest.json").exists()
    manifest = load_manifest(root / "manifest.json")
    assert "davinci-rest>=0.2.5" in manifest.dependencies


def test_scaffold_lua_template(tmp_path) -> None:
    """Test lua template creates Lua script project."""
    root, written = scaffold_project("my_lua", destination=tmp_path, template="lua")

    assert (root / "manifest.json").exists()
    assert (root / "my_lua_main.lua").is_file()
    assert not (root / "my_lua.py").is_file()  # No Python entry

    manifest = load_manifest(root / "manifest.json")
    assert manifest.consolidate.enabled is False
    assert manifest.python == ""  # No Python package


def test_cli_create_end_to_end(tmp_path, capsys) -> None:
    assert main(["create", "cli_ext", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    project = tmp_path / "cli_ext"
    assert "Next steps" in out
    assert (project / "manifest.json").is_file()
    assert (project / "cli_ext" / "__init__.py").is_file()


def test_walk_templates_skips_pycache(tmp_path) -> None:
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "menu.cpython-312.pyc").write_bytes(b"\xcb\r\r\n")
    (tmp_path / "manifest.json.j2").write_text("{}", encoding="utf-8")
    found = [p.name for p in _walk_templates(tmp_path)]
    assert found == ["manifest.json.j2"]


def test_scaffold_survives_pycache_in_templates(tmp_path, monkeypatch) -> None:
    from ResolveScript import scaffold as scaffold_mod

    fake = tmp_path / "extension"
    (fake / "@NAME@").mkdir(parents=True)
    (fake / "manifest.json.j2").write_text('{"name": "@NAME@"}', encoding="utf-8")
    (fake / "README.md").write_text("# @NAME@", encoding="utf-8")
    (fake / "@NAME@" / "__init__.py").write_text("", encoding="utf-8")
    (fake / "@NAME@" / "__pycache__").mkdir()
    (fake / "@NAME@" / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\xcb\r\r\n")
    monkeypatch.setattr(scaffold_mod, "TEMPLATES_DIR", tmp_path)
    root, written = scaffold_project("py_cache_ok", destination=tmp_path)
    assert (root / "py_cache_ok").is_dir()
    assert (root / "py_cache_ok" / "__init__.py").is_file()
    assert not any(".pyc" in str(p) for p in written)
