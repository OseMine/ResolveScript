"""Event objects delivered to handlers.

Resolve invokes handlers with a plain dictionary, so that is what arrives here.
Rather than make every script index magic strings, the framework wraps it in
an :class:`Event` that offers typed accessors and still behaves like the
original mapping::

    def on_render(ev):
        print(ev.text, ev.key("Modifiers"))

Handlers that take no arguments work too, so a one-liner like
``Button("Go", on_click=lambda: run())`` is fine.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["Event", "adapt", "no_op"]

_SENTINEL = object()


@dataclass(frozen=True)
class Event:
    """A native event, with attribute *and* mapping access."""

    type: str
    target: Any = None
    native: Mapping[str, Any] = field(default_factory=dict)

    # -- typed accessors -------------------------------------------------
    @property
    def text(self) -> Any:
        """Text payload (``TextChanged``, ``ReturnPressed``, ...)."""
        return self.native.get("Text")

    @property
    def value(self) -> Any:
        """Numeric payload (``ValueChanged``)."""
        if "Value" in self.native:
            return self.native["Value"]
        return self.native.get("CurrentIndex")

    @property
    def checked(self) -> Any:
        """Boolean payload (``Toggled``)."""
        if "Checked" in self.native:
            return self.native["Checked"]
        return self.native.get("Down")

    @property
    def index(self) -> Any:
        """Selection index (``CurrentIndexChanged``, ``CurrentChanged``)."""
        if "CurrentIndex" in self.native:
            return self.native["CurrentIndex"]
        return self.native.get("Value")

    @property
    def item(self) -> Any:
        """Selected tree item (``CurrentItemChanged``)."""
        return self.native.get("CurrentItem") or self.native.get("Item")

    @property
    def color(self) -> Any:
        return self.native.get("Color")

    @property
    def position(self) -> Any:
        return self.native.get("Pos")

    @property
    def key_name(self) -> Any:
        return self.native.get("Key")

    @property
    def modifiers(self) -> list[str]:
        raw = self.native.get("Modifiers") or []
        if isinstance(raw, str):
            return [raw]
        return list(raw)

    @property
    def sender(self) -> Any:
        return self.native.get("sender", self.target)

    # -- mapping access --------------------------------------------------
    def key(self, name: str, default: Any = None) -> Any:
        return self.native.get(name, default)

    def __getitem__(self, name: str) -> Any:
        return self.native[name]

    def __contains__(self, name: object) -> bool:
        return name in self.native

    def get(self, name: str, default: Any = None) -> Any:
        return self.native.get(name, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.native)

    def __repr__(self) -> str:
        element_id = None
        if isinstance(self.native, Mapping):
            element_id = self.native.get("ID")
        suffix = f" id={element_id!r}" if element_id else ""
        return f"<Event {self.type}{suffix}>"


def no_op(event: Any = None) -> None:
    """A handler that does nothing — the default for optional callbacks."""
    return


def adapt(handler: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a user handler so it receives a single :class:`Event`.

    Handlers declaring zero parameters are called with no arguments; handlers
    declaring two or more receive the raw mapping, since they are almost
    certainly written against Resolve's own calling convention.
    """
    if not callable(handler):
        raise TypeError(f"handler must be callable, got {type(handler).__name__}")

    accepts = _arity(handler)

    if accepts == 0:

        def zero(event_data: Mapping[str, Any], type: str = "", target: Any = None) -> Any:
            return handler()

        return zero

    if accepts >= 2:

        def raw(event_data: Mapping[str, Any], type: str = "", target: Any = None) -> Any:
            return handler(event_data)

        return raw

    def one(event_data: Mapping[str, Any], type: str = "", target: Any = None) -> Any:
        return handler(Event(type=type, target=target, native=event_data))

    return one


def _arity(handler: Callable[..., Any]) -> int:
    """How many positional parameters a callable accepts, or 1 if unclear."""
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):  # builtins without introspectable signatures
        return 1
    count = 0
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            return 1
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            count += 1
    return count
