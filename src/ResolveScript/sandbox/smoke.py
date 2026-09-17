"""Generic smoke checks for any Resolve script package.

``run_smoke`` walks the package's public API (or an explicit list of export
names) and calls every zero-arg callable against the injected mock Resolve
environment. Any callable that raises is reported as a failure; functions that
require arguments are skipped by design.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Callable

_REQUIRED = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)


@dataclass
class SmokeCheck:
    name: str
    ok: bool
    detail: str = "ok"


@dataclass
class SmokeResult:
    checks: list[SmokeCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failed(self) -> int:
        return sum(0 if check.ok else 1 for check in self.checks)

    def __len__(self) -> int:
        return len(self.checks)


def callable_without_args(obj: Any) -> bool:
    """True if ``obj`` is a plain callable that takes no required arguments."""
    if inspect.isclass(obj):
        return False
    if not callable(obj):
        return False
    try:
        signature = inspect.signature(obj)
    except (TypeError, ValueError):
        return False
    for param in signature.parameters.values():
        if param.kind in _REQUIRED and param.default is inspect.Parameter.empty:
            return False
    return True


def discover_exports(module: ModuleType) -> dict[str, Callable[..., Any]]:
    """Public zero-arg callables of a module (in ``dir()`` order)."""
    exports: dict[str, Callable[..., Any]] = {}
    for name in dir(module):
        if name.startswith("_"):
            continue
        obj = getattr(module, name)
        if isinstance(obj, ModuleType):
            continue
        if callable_without_args(obj):
            exports[name] = obj
    return exports


def run_smoke(module: ModuleType, exports: list[str] | None = None, verbose: bool = False) -> SmokeResult:
    """Exercise ``module``'s public API against the mock environment.

    When ``exports`` is given it selects named attributes; otherwise the
    module's public zero-arg callables are discovered automatically.
    """
    names = exports if exports is not None else sorted(discover_exports(module))
    result = SmokeResult()

    def _check(name: str, fn: Any) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a smoke run must not abort
            result.checks.append(SmokeCheck(name, False, f"{type(exc).__name__}: {exc}"))
        else:
            result.checks.append(SmokeCheck(name, True, "ok"))

    for name in names:
        attr = getattr(module, name, None)
        if attr is None or not callable(attr):
            result.checks.append(SmokeCheck(name, False, f"missing export '{name}'"))
            continue
        if not callable_without_args(attr):
            result.checks.append(SmokeCheck(name, True, "skipped (requires arguments)"))
            continue
        _check(name, attr)

    if verbose:
        for check in result.checks:
            tag = "PASS" if check.ok else "FAIL"
            print(f"  [{tag}] {check.name}  ({check.detail})")
        print(f"\n{len(result) - result.failed}/{len(result)} checks passed")
    return result
