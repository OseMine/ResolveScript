"""Tests for the analyzer (M6) and the test command."""

from __future__ import annotations

import json

from resolve_script.analyze import analyze_project
from resolve_script.cli import main
from resolve_script.scaffold import scaffold_project


def test_analyze_scaffolded_project(tmp_path) -> None:
    scaffold_project("hello", destination=tmp_path)
    manifest_path = tmp_path / "hello" / "manifest.json"
    from resolve_script.manifest.json_reader import load_manifest

    manifest = load_manifest(manifest_path)
    analysis = analyze_project(tmp_path / "hello", manifest)
    assert not [i for i in analysis.issues if i.severity == "error"]
    assert analysis.api_mocked
    assert any(line.startswith("API coverage:") for line in analysis.api_report())


def test_analyze_syntax_error(tmp_path) -> None:
    (tmp_path / "broken.py").write_text("def (\n", encoding="utf-8")
    analysis = analyze_project(tmp_path)
    assert any(i.code == "SYNTAX" for i in analysis.issues)


def test_analyze_unused_import(tmp_path) -> None:
    (tmp_path / "mod.py").write_text(
        "import os\nimport sys\nprint(sys.argv)\n", encoding="utf-8"
    )
    analysis = analyze_project(tmp_path)
    warnings = [i for i in analysis.issues if i.code == "UNUSED_IMPORT"]
    assert warnings
    assert any("os" in w.message for w in warnings)


def test_analyze_api_unmocked(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        'resolve = object()\nresolve.FooBarCustomMethod()\n', encoding="utf-8"
    )
    analysis = analyze_project(tmp_path)
    used = {i.message for i in analysis.issues if i.code == "API_UNMOCKED"}
    assert any("FooBarCustomMethod" in m for m in used)

    (tmp_path / "app.py").write_text(
        'resolve = object()\nresolve.GetProjectManager()\n', encoding="utf-8"
    )
    analysis = analyze_project(tmp_path)
    used = {i.message for i in analysis.issues if i.code == "API_UNMOCKED"}
    assert not any("GetProjectManager" in m for m in used)


def test_cli_analyze_json(tmp_path, monkeypatch, capsys) -> None:
    scaffold_project("hello", destination=tmp_path)
    monkeypatch.chdir(tmp_path / "hello")
    assert main(["analyze", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)


def test_cli_analyze_error(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "manifest.json").write_text(
        '{"name":"bad","version":"not-semver"}', encoding="utf-8"
    )
    assert main(["analyze"]) == 1
    assert "[ERROR]" in capsys.readouterr().out


def test_cli_test_scaffolded(tmp_path, monkeypatch, capsys) -> None:
    scaffold_project("hello", destination=tmp_path)
    monkeypatch.chdir(tmp_path / "hello")
    assert main(["test"]) == 0


def test_cli_test_built_not_found(tmp_path, monkeypatch, capsys) -> None:
    scaffold_project("hello", destination=tmp_path)
    monkeypatch.chdir(tmp_path / "hello")
    assert main(["test", "--built"]) == 1
    assert "built package not found" in capsys.readouterr().err


def test_cli_test_built(tmp_path, monkeypatch, capsys) -> None:
    scaffold_project("hello", destination=tmp_path)
    monkeypatch.chdir(tmp_path / "hello")
    assert main(["build"]) == 0
    assert main(["test", "--built"]) == 0


def test_cli_test_api_coverage(tmp_path, monkeypatch, capsys) -> None:
    scaffold_project("hello", destination=tmp_path)
    monkeypatch.chdir(tmp_path / "hello")
    assert main(["test", "--api-coverage"]) == 0
    out = capsys.readouterr().out
    assert "API coverage:" in out
    assert "of" in out
