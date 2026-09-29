"""The DaVinci Resolve backend.

Talks to the real Fusion UIManager, which is Qt-based::

    ui = resolve.Fusion().UIManager
    dispatcher = bmd.UIDispatcher(ui)
    win = dispatcher.AddWindow({"ID": "main"}, [ui.Label({"Text": "Hi"})])
    win.On.main.Close = lambda ev: dispatcher.ExitLoop()
    win.Show()
    dispatcher.RunLoop()

Two details matter and are easy to get wrong, so they are handled here rather
than in every caller:

* **Elements need an ``ID`` to receive events.** The dispatcher routes events
  through ``win.On[ID].Event``, so every element that has a handler is given
  a unique id derived from its node key.
* **Value-change events are opt-in.** Qt only delivers, say,
  ``ValueChanged`` or ``TextChanged`` when the element is created with an
  ``Events`` table naming them. The renderer builds that table; this backend
  just passes the props through.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from ..errors import BackendUnavailable
from .base import Backend

__all__ = ["FusionBackend", "connect"]


def _acquire_resolve(resolve: Any = None) -> Any:
    """Find the live Resolve object, trying the usual entry points."""
    if resolve is not None:
        return resolve
    try:
        import DaVinciResolveScript as dvr_script  # type: ignore[import-not-found]

        found = dvr_script.scriptapp("Resolve")
        if found is not None:
            return found
    except Exception:
        pass
    try:
        import builtins

        found = getattr(builtins, "resolve", None)
        if found is not None:
            return found
    except Exception:  # pragma: no cover - builtins always exists
        pass
    raise BackendUnavailable(
        "DaVinci Resolve is not reachable. Run this script from inside Resolve "
        "(Workspace > Scripts), or pass resolve=FusionBackend(resolve=...) "
        "explicitly when driving it externally."
    )


def _acquire_ui_manager(resolve: Any) -> Any:
    """Return the Fusion UIManager, tolerating both the property and call forms."""
    fusion_of = getattr(resolve, "Fusion", None)
    if not callable(fusion_of):
        raise BackendUnavailable(
            f"{type(resolve).__name__} has no Fusion(). The UI framework needs a "
            "live DaVinci Resolve, not a stub — run the script from Resolve's "
            "Workspace, or use backend='mock' outside it."
        )
    try:
        fusion = fusion_of()
    except Exception as exc:
        raise BackendUnavailable(f"{type(resolve).__name__}.Fusion() failed: {exc}") from exc
    if fusion is None:
        raise BackendUnavailable("resolve.Fusion() returned nothing.")
    manager = getattr(fusion, "UIManager", None)
    if manager is None:
        raise BackendUnavailable("resolve.Fusion() has no UIManager attribute.")
    # The documented examples use both ``fusion.UIManager`` and
    # ``fusion.UIManager()``; support either.
    if callable(manager):
        manager = manager()
    if manager is None:
        raise BackendUnavailable("resolve.Fusion().UIManager() returned nothing.")
    return manager


def _acquire_dispatcher(ui: Any) -> Any:
    """Build a ``bmd.UIDispatcher`` around the given UIManager."""
    try:
        import bmd  # type: ignore[import-not-found]
    except ImportError:
        import sys

        bmd = sys.modules.get("bmd")
    if bmd is None:
        raise BackendUnavailable(
            "The 'bmd' module is unavailable, so no UIDispatcher can be created. "
            "It ships with Resolve and is importable only from Resolve's own "
            "Python environment. Pass dispatcher=... to inject your own."
        )
    return bmd.UIDispatcher(ui)


class FusionBackend(Backend):
    """Renders to the real DaVinci Resolve / Fusion UI.

    :param resolve: the Resolve object; discovered automatically when omitted.
    :param ui: the element factory; taken from ``resolve.Fusion().UIManager``.
    :param dispatcher: an existing UIDispatcher, or a callable that builds one
        from ``ui`` (the default).
    """

    name = "fusion"

    def __init__(
        self,
        resolve: Any = None,
        ui: Any = None,
        dispatcher: Any = None,
    ):
        self._resolve = _acquire_resolve(resolve)
        self.ui = ui if ui is not None else _acquire_ui_manager(self._resolve)
        if dispatcher is None:
            self.dispatcher = _acquire_dispatcher(self.ui)
        elif callable(dispatcher) and not hasattr(dispatcher, "AddWindow"):
            self.dispatcher = dispatcher(self.ui)
        else:
            self.dispatcher = dispatcher
        self._roots: dict[int, Any] = {}

    # -- construction ----------------------------------------------------
    def create_root(
        self, kind: str, props: Mapping[str, Any], children: Sequence[Any]
    ) -> Any:
        payload = list(children)
        if kind == "dialog":
            element = self.dispatcher.AddDialog(dict(props), payload)
        else:
            element = self.dispatcher.AddWindow(dict(props), payload)
        self._roots[id(element)] = element
        return element

    def create_element(
        self, native_type: str, props: Mapping[str, Any], children: Sequence[Any]
    ) -> Any:
        factory = getattr(self.ui, native_type, None)
        if factory is None:
            raise BackendUnavailable(
                f"this Resolve build has no {native_type!r} element. "
                "Check the element name against the UIManager reference."
            )
        attributes = dict(props)
        payload = list(children)
        if payload:
            return factory(attributes, payload) if attributes else factory(payload)
        return factory(attributes) if attributes else factory()

    def connect(
        self, root: Any, element_id: str, event: str, handler: Callable[..., Any]
    ) -> None:
        # ``win.On["myId"]["Clicked"] = fn`` and ``win.On.myId.Clicked = fn``
        # are equivalent; the bracketed form is used because element ids
        # frequently contain characters that are not valid identifiers.
        root.On[element_id][event] = handler

    # -- mutation --------------------------------------------------------
    def set_prop(self, element: Any, name: str, value: Any) -> None:
        setattr(element, name, value)

    def get_prop(self, element: Any, name: str) -> Any:
        return getattr(element, name)

    def add_child(self, parent: Any, child: Any) -> None:
        parent.AddChild(child)

    def remove_child(self, parent: Any, child: Any) -> None:
        with contextlib.suppress(Exception):
            parent.RemoveChild(child)

    def children_of(self, element: Any) -> list[Any]:
        return list(element.GetChildren())

    def call(self, element: Any, method: str, *args: Any) -> Any:
        handler = getattr(element, method, None)
        if not callable(handler):
            raise BackendUnavailable(f"{method!r} is not available on this element.")
        return handler(*args)

    # -- lifecycle -------------------------------------------------------
    def show(self, root: Any) -> None:
        root.Show()

    def run_loop(self) -> int:
        return int(self.dispatcher.RunLoop() or 0)

    def exit_loop(self, code: int = 0) -> None:
        self.dispatcher.ExitLoop(code)

    def destroy(self, element: Any) -> None:
        self._roots.pop(id(element), None)
        with contextlib.suppress(Exception):
            element.Close()

    def create_item(self, kind: str, props: Mapping[str, Any]) -> Any:
        factory = getattr(self.ui, kind, None)
        if factory is None:
            raise BackendUnavailable(f"this Resolve build has no {kind!r} element.")
        return factory(dict(props))

    def describe(self) -> str:
        return "fusion (live DaVinci Resolve)"


def connect(
    resolve: Any = None, ui: Any = None, dispatcher: Any = None
) -> FusionBackend:
    """Convenience factory: build a :class:`FusionBackend`.

    Kept separate from the constructor so it reads well at a call site and can
    gain defaulting logic later without touching the class.
    """
    return FusionBackend(resolve=resolve, ui=ui, dispatcher=dispatcher)
