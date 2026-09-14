"""CLI wiring tests (M0)."""

from __future__ import annotations

import pytest

from resolve_script import __version__
from resolve_script.cli import main


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


def test_skeleton_command_reports_not_implemented(capsys) -> None:
    assert main(["dev"]) == 1
    err = capsys.readouterr().err
    assert "not implemented" in err


@pytest.mark.parametrize(
    "argv",
    [
        ["dev", "--repl"],
        ["test", "--built"],
        ["analyze", "--json"],
        ["package", "--dist", "out"],
        ["add", "owner/repo"],
        ["install"],
        ["update", "--fix"],
        ["remove", "foo"],
        ["search", "roto"],
        ["manage", "list"],
        ["manage", "remove", "foo"],
        ["extensions", "add", "foo"],
        ["extensions", "list"],
    ],
)
def test_command_wiring(argv: list[str]) -> None:
    assert main(argv) == 1  # skeleton: command resolves, returns error exit
