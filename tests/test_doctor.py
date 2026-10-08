"""doctor: environment and project self-diagnosis."""

from __future__ import annotations

import json

import ResolveScript as rs
from ResolveScript.cli import main
from ResolveScript.doctor import CHECK_ORDER, WARN, issues_json, run_checks


def _statuses(checks):
    return {check.name: check.status for check in checks}


def test_run_checks_covers_every_check_in_order(tmp_path):
    checks = run_checks(scripts_root=tmp_path, cwd=tmp_path)
    assert [check.name for check in checks] == list(CHECK_ORDER)
    assert all(check.status in {"ok", "warn", "fail"} for check in checks)


def test_interpreter_and_templates_are_ok(tmp_path):
    checks = _statuses(run_checks(scripts_root=tmp_path, cwd=tmp_path))
    assert checks["interpreter"] == "ok"
    assert checks["templates"] == "ok"


def test_missing_scripts_root_warns(tmp_path):
    checks = run_checks(scripts_root=tmp_path / "nope", cwd=tmp_path)
    entry = next(c for c in checks if c.name == "scripts-root")
    assert entry.status == WARN
    assert "missing" in entry.detail


def test_existing_scripts_root_is_ok_and_lists_targets(tmp_path):
    (tmp_path / "Comp").mkdir()
    (tmp_path / "Utility").mkdir()
    checks = run_checks(scripts_root=tmp_path, cwd=tmp_path)
    entry = next(c for c in checks if c.name == "scripts-root")
    assert entry.status == "ok"
    assert "Comp" in entry.detail and "Utility" in entry.detail


def test_manifest_check_in_a_scaffolded_project(tmp_path):
    root, _written = rs.scaffold_project("doc_tools", destination=tmp_path)
    checks = run_checks(scripts_root=tmp_path / "root", cwd=root)
    entry = next(c for c in checks if c.name == "manifest")
    assert entry.status == "ok"
    assert "doc_tools" in entry.detail


def test_manifest_check_without_a_project_is_ok(tmp_path):
    checks = run_checks(scripts_root=tmp_path, cwd=tmp_path)
    entry = next(c for c in checks if c.name == "manifest")
    assert entry.status == "ok"
    assert "not a script project" in entry.detail


def test_broken_manifest_fails(tmp_path):
    (tmp_path / "manifest.json").write_text("{ not json", encoding="utf-8")
    checks = run_checks(scripts_root=tmp_path, cwd=tmp_path)
    entry = next(c for c in checks if c.name == "manifest")
    assert entry.status == "fail"
    assert entry.detail


def test_broken_workspace_fails(tmp_path):
    (tmp_path / "resolvescript.json").write_text("[1, 2]", encoding="utf-8")
    checks = run_checks(scripts_root=tmp_path, cwd=tmp_path)
    entry = next(c for c in checks if c.name == "workspace")
    assert entry.status == "fail"


def test_broken_registry_fails(tmp_path):
    registry = tmp_path / ".resolvescript" / "install.json"
    registry.parent.mkdir(parents=True)
    registry.write_text("not json", encoding="utf-8")
    checks = run_checks(scripts_root=tmp_path, cwd=tmp_path)
    entry = next(c for c in checks if c.name == "registry")
    assert entry.status == "fail"


def test_issues_json_is_machine_readable(tmp_path):
    checks = run_checks(scripts_root=tmp_path, cwd=tmp_path)
    payload = json.loads(issues_json(checks))
    assert [c["name"] for c in payload["checks"]] == list(CHECK_ORDER)
    assert payload["warnings"] == sum(1 for c in checks if c.status == WARN)
    assert payload["failures"] == sum(1 for c in checks if c.status == "fail")


def test_cli_doctor_human_output(tmp_path, capsys):
    code = main(["doctor", "--scripts-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "[ ok ]" in out
    assert "all checks passed" in out


def test_cli_doctor_json_output(tmp_path, capsys):
    code = main(["doctor", "--json", "--scripts-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [c["name"] for c in payload["checks"]] == list(CHECK_ORDER)


def test_cli_doctor_exits_1_on_failure(tmp_path, monkeypatch, capsys):
    (tmp_path / "manifest.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    code = main(["doctor", "--json", "--scripts-root", str(tmp_path / "root")])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["failures"] >= 1
