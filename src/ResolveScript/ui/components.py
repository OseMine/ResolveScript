"""Class-based components: the other way to author a UI.

The function DSL in :mod:`ResolveScript.ui.dsl` is the shortest path from an
idea to a screen, but a 200-line ``build_tool_panel()`` starts to hurt. When it
does, move the state and the markup into a class::

    @widget("clip-panel")
    class ClipPanel(Component):
        def __init__(self, clip):
            super().__init__(clip=clip)
            self.enabled = Value(True)

        def build(self) -> Node:
            return Card(
                Heading(self.clip.get()),
                TextField(value=self.clip, enabled=self.enabled),
                Row(Button("Apply", on_click=self.apply), Spacer(), Switch(self.enabled)),
                gap="sm",
            )

        def apply(self) -> None:
            print("applying", self.clip.get())

A component instance can be used anywhere a node can::

    Window(title="Editor", children=[ClipPanel(clip)])

It is also registered by name, so the same component can be requested from a
dict or JSON document — see :mod:`ResolveScript.ui.jsonio`.

Reactivity is unchanged: a component is a *factory*, and the node it returns is
an ordinary node. Bind a :class:`~ResolveScript.ui.state.Value` to a prop and
the renderer keeps it in sync; no component re-render is involved. Call
:meth:`Component.build` again (or :meth:`ResolveScript.ui.app.App.refresh`) when
the *structure* depends on something that is not a ``Value``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, ClassVar

from .errors import ElementError
from .node import Node

__all__ = [
    "Component",
    "Widget",
    "widget",
    "register_component",
    "get_component",
    "all_components",
]


class Component:
    """Base class for a reusable piece of UI.

    Subclasses implement :meth:`build`. The constructor should call
    ``super().__init__(**kwargs)`` so declared props are available on
    ``self.props``.
    """

    #: Registry name, filled in by the :func:`widget` decorator.
    name: ClassVar[str | None] = None

    def __init__(self, **props: Any):
        self.props: dict[str, Any] = dict(props)
        self._node: Node | None = None
        #: Components this one expanded, so a refresh can invalidate them too.
        self._nested: list[Component] = []

    # -- authoring -------------------------------------------------------
    def build(self) -> Node:
        """Return the node tree for this component."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement build() returning a Node"
        )

    def to_node(self) -> Node:
        """The component as a node, building it once and caching the result."""
        if self._node is None:
            built = self.build()
            # A component may return another component — a panel is very often
            # just a composition of smaller ones — so expand it here rather
            # than making every intermediate wrapper remember to call to_node().
            if isinstance(built, Component):
                inner = built
                built = inner.to_node()
                self._nested.append(inner)
                if built.origin is None:
                    built = replace(built, origin=inner)
            if not isinstance(built, Node):
                raise ElementError(
                    f"{type(self).__name__}.build() returned {type(built).__name__}, "
                    "expected a Node or Component"
                )
            self._node = built
        return self._node

    def refresh(self) -> Node:
        """Discard the cached node — and that of any nested component — and build again.

        A component that keeps a child as an instance attribute would otherwise
        hand back the child's stale cache forever.
        """
        self._node = None
        nested, self._nested = self._nested, []
        for child in nested:
            child.refresh()
        return self.to_node()

    def with_props(self, **overrides: Any) -> Component:
        """A sibling of this component with different props.

        Instance attributes are carried over, so derived state survives; the
        node cache is not, so the clone builds its own tree.
        """
        clone = type(self)(**{**self.props, **overrides})
        for key, value in self.__dict__.items():
            if key not in ("props", "_node", "_nested"):
                clone.__dict__[key] = value
        return clone

    # -- convenience -----------------------------------------------------
    def __call__(self) -> Node:
        return self.to_node()

    def __repr__(self) -> str:
        label = self.name or type(self).__name__
        return f"<{label} {self.props!r}>" if self.props else f"<{label}>"


#: Readable alias, since these are the framework's user-defined widgets.
Widget = Component


_COMPONENTS: dict[str, type[Component]] = {}


def register_component(name: str, cls: type[Component]) -> type[Component]:
    """Register a component class under ``name``."""
    if not isinstance(name, str) or not name:
        raise ElementError("component name must be a non-empty string")
    if not (isinstance(cls, type) and issubclass(cls, Component)):
        raise ElementError(f"expected a Component subclass, got {cls!r}")
    _COMPONENTS[name] = cls
    cls.name = name
    return cls


def get_component(name: str) -> type[Component]:
    """Look up a registered component class."""
    try:
        return _COMPONENTS[name]
    except KeyError:
        close = sorted(key for key in _COMPONENTS if name.lower() in key.lower())
        hint = f"; did you mean {close}?" if close else ""
        raise ElementError(f"unknown component {name!r}{hint}") from None


def all_components() -> dict[str, type[Component]]:
    """Every registered component, keyed by name."""
    return dict(_COMPONENTS)


def widget(
    target: str | type[Component] | None = None, **defaults: Any
) -> Any:
    """Register a component so dict/JSON documents can name it.

    Usable bare or with a name, and with optional prop defaults::

        @widget
        class Header(Component): ...

        @widget("clip-panel", clip="A001")
        class ClipPanel(Component): ...
    """
    if isinstance(target, str):
        name: str = target
    else:
        name = ""

    def decorate(cls: type[Component]) -> type[Component]:
        label = name or cls.__name__
        register_component(label, cls)
        if defaults:
            original_init = cls.__init__

            def __init__(self: Any, **props: Any) -> None:
                original_init(self, **{**defaults, **props})

            cls.__init__ = __init__  # type: ignore[method-assign]
        return cls

    if target is None or isinstance(target, str):
        return decorate
    return decorate(target)


def as_callable(builder: Any) -> Callable[[], Any]:
    """Normalise ``Node``/``Component``/callable into a zero-arg factory.

    Used by :class:`ResolveScript.ui.app.App`, which accepts any of the three
    so a window can be described once and rebuilt on refresh.
    """
    if isinstance(builder, Component):
        return builder.to_node
    if isinstance(builder, Node):
        return lambda: builder
    if callable(builder):
        return builder
    raise ElementError(f"expected a Node, Component or factory, got {builder!r}")
