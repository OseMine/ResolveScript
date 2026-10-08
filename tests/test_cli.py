"""CLI wiring tests (M0)."""

from __future__ import annotations

import pytest

from ResolveScript import __version__
from ResolveScript.cli import main


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert f"resolvescript {__version__}" in out


def test_no_command_prints_help_and_exits_usage(capsys) -> None:
    assert main([]) == 2
    out = capsys.readouterr().out
    assert "usage:" in out


def test_extensions_list_is_wired(capsys, tmp_path, monkeypatch) -> None:
    """`extensions list` is a real command now (M5c), not an M0 skeleton."""
    monkeypatch.setenv("RESOLVESCRIPT_CONFIG_DIR", str(tmp_path))
    assert main(["extensions", "list"]) == 0
    assert "no framework extensions installed" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["test", "--built"],
        ["analyze", "--json"],
        ["package", "--dist", "out"],
        ["manage", "remove", "foo"],
        ["extensions", "add", "foo"],
    ],
)
def test_command_wiring(argv: list[str]) -> None:
    assert main(argv) == 1  # command resolves, reports a failure exit


def test_remove_uninstalled_reports_error(capsys) -> None:
    assert main(["remove", "foo"]) == 1
    assert "is not installed" in capsys.readouterr().err


def test_author_flow_e2e(tmp_path, monkeypatch, capsys) -> None:
    """create -> dev -> build -> test --built -> package -> install -> list -> remove."""
    from ResolveScript.scaffold import scaffold_project

    scaffold_project("demo", destination=tmp_path)
    project = tmp_path / "demo"
    scripts = tmp_path / "Scripts"
    monkeypatch.chdir(project)

    assert main(["dev"]) == 0
    capsys.readouterr()
    assert main(["build"]) == 0
    assert main(["test", "--built"]) == 0
    capsys.readouterr()
    assert main(["package"]) == 0
    capsys.readouterr()
    assert main(["install", "--scripts-root", str(scripts)]) == 0
    capsys.readouterr()
    assert main(["manage", "list", "--scripts-root", str(scripts)]) == 0
    out = capsys.readouterr().out
    assert "demo" in out
    assert main(["remove", "demo", "--scripts-root", str(scripts)]) == 0
    assert not (scripts / "Comp" / "demo").exists()
