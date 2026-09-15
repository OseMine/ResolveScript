"""Pytest fixtures for developing Resolve scripts against the mock API.

The ``sandbox`` fixture installs the fake ``DaVinciResolveScript`` module and
yields the mock Resolve object. ``load_source_module`` and ``load_built_module``
import the extension under test either as a source package or as a consolidated
single-file build.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from ..sandbox.env import install_fake_resolve
from ..sandbox.loader import load_built_module as _load_built_module
from ..sandbox.loader import load_source_module as _load_source_module


@pytest.fixture(scope="session", autouse=True)
def _sandbox_installed() -> None:
    """Install the mock Resolve API once per test session."""
    install_fake_resolve()


@pytest.fixture
def sandbox() -> ModuleType:
    """Install (idempotently) and return the fake DaVinciResolveScript module."""
    return install_fake_resolve()


@pytest.fixture
def load_source_module() -> Callable[[str, Path | str], ModuleType]:
    def _load(module_name: str, package_dir: Path | str = ".") -> ModuleType:
        return _load_source_module(module_name, Path(package_dir))

    return _load


@pytest.fixture
def load_built_module() -> Callable[[str, Path | str], ModuleType]:
    def _load(module_name: str, built_file: Path | str) -> ModuleType:
        return _load_built_module(module_name, Path(built_file))

    return _load
