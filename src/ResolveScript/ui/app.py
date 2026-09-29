"""Running a UI: mount, show, pump events, clean up.

The shortest complete script is one call::

    from ResolveScript.ui import Window, Column, Button, run

    run(Window("My Tool", children=[Column(Button("Go"), gap="md")]))

:class:`App` is the same thing with the event loop left to the caller, which is
what you want in a test, or when the UI is a panel inside a script that already
owns the loop::

    with App(Window("Panel", children=[...]), backend="mock") as app:
        app.backend.fire("go", "Clicked")

Backend selection
-----------------

``backend=`` accepts a name or an instance. The default, ``"auto"``, uses the
real Fusion UIManager when Resolve is reachable and falls back to the headless
mock otherwise — so the same script runs in Resolve's Workspace and in CI.

Closing
-------

A Fusion window's ``Close`` event does not stop ``RunLoop`` on its own, so
:class:`App` chains ``ExitLoop`` onto the window's close handler automatically.
An ``on_close`` on the window node still runs, and runs first.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .backends import get_backend
from .backends.base import Backend
from .components import Component, as_callable
from .errors import ElementError
from .events import Event, adapt
from .node import Node, NodeBase
from .render import AppRoot, Bound, Renderer
from .theme import Theme

__all__ = ["App", "run", "mount"]


class App:
    """A mounted window, with its backend and renderer attached.

    :param window: a :func:`~ResolveScript.ui.dsl.Window`/:func:`Dialog` node, a
        :class:`~ResolveScript.ui.components.Component`, or a zero-argument
        factory returning either (re-invoked by :meth:`refresh`).
    :param backend: ``"auto"`` (default), ``"fusion"``, ``"mock"``, or a
        :class:`~ResolveScript.ui.backends.base.Backend` instance.
    :param theme: overrides the active theme for this window and its subtree.
    :param on_close: called when the user closes the window, before the loop
        stops. Ignored when the window node already carries its own ``on_close``.
    """

    def __init__(
        self,
        window: Any,
        *,
        backend: Any = None,
        theme: Theme | None = None,
        on_close: Callable[..., Any] | None = None,
    ):
        self.backend: Backend = get_backend(backend)
        self.renderer = Renderer(self.backend, theme)
        self.source = window
        # Only a plain callable has to be re-invoked. A Node or Component is
        # resolved through ``as_callable`` each time, so a refreshed tree (or a
        # rebuilt component) is what gets mounted rather than the original.
        self._factory: Callable[[], Any] | None = (
            window if callable(window) and not isinstance(window, (Node, Component)) else None
        )
        self._on_close = adapt(on_close) if on_close is not None else None
        self._closed = False
        self.root: AppRoot = self.renderer.mount(self._build())

    # -- construction ----------------------------------------------------
    def _build(self) -> Node:
        factory = self._factory or as_callable(self.source)
        built = factory()
        if not isinstance(built, Node):
            raise ElementError(
                f"expected a window or dialog Node, got {type(built).__name__}"
            )
        if built.kind not in ("window", "dialog"):
            raise ElementError(
                f"the root node must be 'window' or 'dialog', got {built.kind!r}. "
                "Wrap your content in Window(...)."
            )
        return self._chain_close(built)

    def _chain_close(self, node: Node) -> Node:
        """Make closing the window stop the loop, keeping any existing handler.

        The dispatcher's ``On[id].Event`` table holds one handler per event, so
        chaining has to happen here rather than by connecting a second one.
        """
        existing = adapt(node.props["on_close"]) if node.props.get("on_close") else self._on_close

        def closed(event: Event | None = None) -> None:
            if existing is not None:
                existing(event.as_dict() if event is not None else {})
            self._request_exit()

        return node.with_props(on_close=closed)

    # -- access ----------------------------------------------------------
    @property
    def window(self) -> Bound:
        """The mounted root node — the entry point for :meth:`Bound.get`."""
        if self.root.bound is None:  # pragma: no cover - always set by mount
            raise ElementError("the window is not mounted")
        return self.root.bound

    @property
    def element(self) -> Any:
        """The native window element."""
        return self.root.element

    def find(self, key: str) -> Bound | None:
        """Find a mounted node by key — e.g. to read a native property."""
        return self.renderer.find(key)

    def require(self, key: str) -> Bound:
        """Like :meth:`find`, but raises when the node is not on screen."""
        found = self.find(key)
        if found is None:
            raise ElementError(f"no mounted node with key {key!r}")
        return found

    # -- lifecycle -------------------------------------------------------
    def show(self) -> App:
        """Display the window without entering the event loop."""
        self.root.show()
        return self

    def refresh(self) -> App:
        """Rebuild the tree and patch only what changed.

        Needed when the *structure* depends on something that is not a
        :class:`~ResolveScript.ui.state.Value` — a plain value changing will
        not re-run a component on its own. Every
        :class:`~ResolveScript.ui.components.Component` in the tree is rebuilt
        first, so a panel's markup can follow a change in its props.
        """
        self.source = _rebuild(self.source)
        self.renderer.update(self._build())
        return self

    def update(self) -> App:
        """Alias for :meth:`refresh`, reading better after a state change."""
        return self.refresh()

    def run(self) -> int:
        """Show the window and pump events until it closes. Returns the exit code."""
        if not self.root.shown:
            self.show()
        try:
            self.root.exit_code = int(self.backend.run_loop() or 0)
        finally:
            self.close()
        return self.root.exit_code

    def close(self, code: int = 0) -> None:
        """Close the window, release every subscription and drop the elements."""
        if self._closed:
            return
        self._closed = True
        self._request_exit(code)
        self.renderer.unmount()

    def _request_exit(self, code: int = 0) -> None:
        if self.root.closed:
            return
        self.root.closed = True
        self.root.exit_code = code
        self.backend.exit_loop(code)

    # -- niceties --------------------------------------------------------
    def __enter__(self) -> App:
        return self.show()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<App {self.root.kind} backend={self.backend.describe()}>"


def mount(window: Any, *, backend: Any = None, theme: Theme | None = None) -> App:
    """Build an :class:`App` without showing it."""
    return App(window, backend=backend, theme=theme)


def _carry_keys(old: NodeBase, new: NodeBase) -> NodeBase:
    """Reuse ``old``'s keys on the tree that replaces it.

    A component's :meth:`~ResolveScript.ui.components.Component.build` mints
    fresh auto-keys every time it runs, so without this a refresh would see
    every node as brand new and replace the whole subtree. Keys the author set
    explicitly (``key=`` or ``key_id=``) are left alone — they already say what
    they mean — and children are matched positionally, only while the shape
    still lines up. A genuine structural change (a child added or removed)
    rebuilds that subtree, which is the right outcome for a different tree.
    """
    if not isinstance(old, Node) or not isinstance(new, Node):
        return new
    if new.auto_key and new.kind == old.kind:
        new = replace(new, key=old.key)
    old_children, new_children = old.children, new.children
    if len(old_children) != len(new_children):
        return new
    carried = tuple(_carry_keys(o, n) for o, n in zip(old_children, new_children))
    if any(c is not n for c, n in zip(carried, new_children)):
        new = new.with_children(*carried)
    return new


def _rebuild(source: Any) -> Any:
    """Return ``source`` with every component in it freshly built.

    A component is expanded into a plain node when the tree is authored, so
    the node remembers where it came from (:attr:`Node.origin`) — that is what
    makes a nested panel rebuildable after its props change. Keys are carried
    across the rebuild by :func:`_carry_keys`, so the renderer patches the
    elements already on screen rather than replacing them.
    """
    if isinstance(source, Component):
        return source.refresh()
    if not isinstance(source, Node):
        return source

    if source.origin is not None:
        previous = source
        source.origin.refresh()
        source = _carry_keys(previous, source.origin.to_node())

    children = tuple(_rebuild(child) for child in source.children)
    if any(new is not old for new, old in zip(children, source.children)):
        source = source.with_children(*children)
    return source


def run(
    window: Any,
    *,
    backend: Any = None,
    theme: Theme | None = None,
    on_close: Callable[..., Any] | None = None,
) -> int:
    """Mount, show, run the event loop, clean up. Returns the exit code.

    >>> run(Window("Tool", children=[Button("Go", key_id="go")]), backend="mock")
    0
    """
    return App(window, backend=backend, theme=theme, on_close=on_close).run()
