"""Smoke tests that pass in the mock sandbox with zero setup."""

import @NAME@


def test_version_is_a_string() -> None:
    assert isinstance(@NAME@.__version__, str)


def test_main_module_has_main() -> None:
    assert hasattr(@NAME@.main, "main")
    assert callable(@NAME@.main.main)


def test_core_module_has_run_ui() -> None:
    assert hasattr(@NAME@.core, "run_ui")
    assert callable(@NAME@.core.run_ui)


def test_core_module_has_build_ui() -> None:
    assert hasattr(@NAME@.core, "build_ui")
    assert callable(@NAME@.core.build_ui)