"""Scaffolder tests (M2)."""

from __future__ import annotations

import importlib
import sys

import pytest

from resolve_script.cli import main
from resolve_script.manifest.json_reader import load_manifest
from resolve_script.manifest.validation import validate_manifest
from resolve_script.scaffold import ScaffoldError, normalize_name, render, scaffold_project


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
    assert (root / "my_tool.py").is_file()
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


def test_cli_create_end_to_end(tmp_path, capsys) -> None:
    assert main(["create", "cli_ext", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    project = tmp_path / "cli_ext"
    assert "Next steps" in out
    assert (project / "manifest.json").is_file()
    assert (project / "cli_ext" / "__init__.py").is_file()
