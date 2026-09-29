"""Backend selection.

    from ResolveScript.ui import backends

    backends.get("fusion")    # real DaVinci Resolve
    backends.get("mock")      # headless, for tests
    backends.get()            # fusion when reachable, otherwise mock

Selecting the Fusion backend explicitly raises if Resolve is not running;
selecting ``auto`` falls back to the mock so a script can still be exercised
in a terminal or CI.
"""

from __future__ import annotations

from typing import Any, Callable

from ..errors import BackendUnavailable
from .base import Backend, ElementTypes
from .fusion import FusionBackend
from .mock import MockBackend, MockElement, MockUIDispatcher, MockUIManager

__all__ = [
    "Backend",
    "ElementTypes",
    "FusionBackend",
    "MockBackend",
    "MockElement",
    "MockUIManager",
    "MockUIDispatcher",
    "get_backend",
    "register_backend",
    "available",
]

_REGISTRY: dict[str, Callable[..., Backend]] = {
    "mock": MockBackend,
    "fusion": FusionBackend,
}

def register_backend(name: str, factory: Callable[..., Backend]) -> None:
    """Register an additional backend under ``name``."""
    _REGISTRY[name] = factory


def get_backend(target: Any = None) -> Backend:
    """Resolve ``target`` to a backend instance.

    ``target`` may be a backend instance (returned unchanged), a registered
    name, or ``None``/``"auto"`` to prefer Fusion and fall back to the mock.
    """
    if isinstance(target, Backend):
        return target
    if target is None or target == "auto":
        try:
            return FusionBackend()
        except BackendUnavailable:
            return MockBackend()
    try:
        factory = _REGISTRY[target]
    except KeyError:
        raise BackendUnavailable(
            f"unknown backend {target!r}; available: {sorted(_REGISTRY)}"
        ) from None
    return factory()


def available() -> list[str]:
    """Names of every registered backend."""
    return sorted(_REGISTRY)
