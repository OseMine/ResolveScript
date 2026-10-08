"""Shared test-suite fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_plugin_config(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the plugin registry off the host machine.

    Every CLI invocation now discovers installed plugins at startup (M5c), so
    without this the suite's output would depend on whatever plugins the
    developer or CI runner happens to have installed. Individual tests that
    need a config directory (e.g. test_plugins.py) override the variable
    again with their own fixture.
    """
    monkeypatch.setenv("RESOLVESCRIPT_CONFIG_DIR", str(tmp_path_factory.mktemp("rs-config")))
