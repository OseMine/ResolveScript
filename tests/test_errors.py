"""The error taxonomy contract: one base class for every library failure."""

from __future__ import annotations

import ResolveScript as rs
from ResolveScript.errors import ResolveScriptError


def test_base_is_exception():
    assert issubclass(ResolveScriptError, Exception)


def test_every_exported_error_is_catchable_via_base():
    """Any exception exported from the package root must derive from the base.

    This is a contract test: a new ``FooError(Exception)`` that forgets to
    subclass ``ResolveScriptError`` fails here the moment it is exported.
    """
    exported_errors = [
        name
        for name in rs.__all__
        if isinstance(getattr(rs, name), type) and issubclass(getattr(rs, name), Exception)
    ]
    assert exported_errors, "expected the package to export at least one error type"
    stray = [name for name in exported_errors if not issubclass(getattr(rs, name), ResolveScriptError)]
    assert not stray, f"exported errors missing ResolveScriptError base: {stray}"


def test_historic_bases_are_preserved():
    """Handlers written against the old types must keep working."""
    assert issubclass(rs.SpecError, ValueError)
    assert issubclass(rs.SemVerError, ValueError)
    assert issubclass(rs.FetchError, RuntimeError)
    assert issubclass(rs.WorkspaceError, RuntimeError)
    assert issubclass(rs.PackageError, RuntimeError)


def test_catchable_via_base_and_via_historic_type():
    try:
        raise rs.SpecError("bad spec")
    except ResolveScriptError as exc:
        assert str(exc) == "bad spec"
    try:
        raise rs.SpecError("bad spec")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("SpecError no longer satisfies ValueError")


def test_causes_chain_with_raise_from():
    try:
        try:
            raise ValueError("inner")
        except ValueError as exc:
            raise rs.FetchError("outer") from exc
    except ResolveScriptError as exc:
        assert isinstance(exc.__cause__, ValueError)
