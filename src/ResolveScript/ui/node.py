"""The declarative node tree.

A UI is described as an immutable tree of :class:`Node` objects. Nodes carry
*logical* props (``text``, ``checked``, ``variant``) rather than Fusion
property names, and a :class:`~ResolveScript.ui.spec.WidgetSpec` translates
them per widget kind. That indirection is what lets one description render to
the real Fusion UIManager, to the headless mock, and back out as JSON.

Reactive props
--------------

A prop may be a plain value, a reactive source, or a :class:`TwoWay` wrapper::

    name = Value("Untitled")

    TextField(value=name)            # inferred two-way for known inputs
    Label(text=name)                 # one-way
    Slider(value=TwoWay(amount))     # explicit, for custom widgets

Classes
-------

:class:`Raw` is the escape hatch. It hands you the live ``ui`` manager and
returns whatever native element you like, so anything Resolve exposes — even
elements the framework has never heard of — can be dropped into a tree built
from framework widgets::

    Raw(lambda ui: ui.SpinBox({"ID": "native", "Value": 3}))

:class:`ResolveScript.ui.components.Component` instances are accepted as
children too; they are expanded through their ``to_node()``.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .errors import ElementError
from .spec import get_spec

__all__ = [
    "Node",
    "Raw",
    "TwoWay",
    "node",
    "native",
    "raw_element",
    "walk",
    "iter_nodes",
]

_KEY_COUNTER = itertools.count(1)


def _coerce_children(children: Sequence[Any]) -> tuple[NodeBase, ...]:
    """Normalise children into a flat tuple, rejecting anything unrenderable.

    Anything exposing ``to_node()`` — every :class:`Component` — is expanded
    into the node it builds, so components and functions compose freely. The
    component is remembered on the node it produced (see
    :attr:`Node.origin`) so a later :meth:`ResolveScript.ui.app.App.refresh`
    can rebuild it.
    """
    flat: list[NodeBase] = []
    stack = list(children)
    while stack:
        item = stack.pop(0)
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            stack = list(item) + stack
            continue
        origin: Any = None
        if not isinstance(item, (Node, Raw)):
            expand = getattr(item, "to_node", None)
            if callable(expand):
                origin = item
                item = expand()
            elif isinstance(item, type) and hasattr(item, "build"):
                origin = item
                item = item().to_node()
            else:
                raise ElementError(
                    f"expected a Node, Raw or Component child, got "
                    f"{type(item).__name__}: {item!r}"
                )
        if origin is not None and isinstance(item, Node) and item.origin is None:
            item = replace(item, origin=origin)
        flat.append(item)
    return tuple(flat)


class NodeBase:
    """Shared surface of :class:`Node` and :class:`Raw`."""

    key: str | None
    children: tuple[NodeBase, ...]

    def __iter__(self) -> Iterator[NodeBase]:
        return iter(self.children)


@dataclass(frozen=True)
class Node(NodeBase):
    """A framework widget description.

    ``kind`` selects a registered :class:`WidgetSpec`; ``props`` are logical
    prop names. Keys are assigned automatically when not given, which is what
    lets the renderer reconcile lists across updates.
    """

    kind: str
    props: Mapping[str, Any] = field(default_factory=dict)
    children: tuple[NodeBase, ...] = ()
    key: str | None = None
    #: The :class:`~ResolveScript.ui.components.Component` this node was built
    #: from, if any. Not serialised and not part of equality; it exists so
    #: :meth:`ResolveScript.ui.app.App.refresh` can rebuild the component.
    origin: Any = field(default=None, compare=False, repr=False)
    #: ``True`` when :attr:`key` came from the counter rather than the author.
    #: Rebuilt components mint fresh counters every time, so a refresh carries
    #: these keys across — see :func:`ResolveScript.ui.app._carry_keys`.
    auto_key: bool = field(default=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "children", _coerce_children(self.children))
        if not isinstance(self.props, Mapping):
            raise ElementError(f"props must be a mapping, got {type(self.props).__name__}")
        # Fail at the point of authorship, not three frames into a mount.
        get_spec(self.kind)
        props = dict(self.props)
        # DSL helpers forward **props, so ``key=`` can arrive either way: as the
        # node's key or as a prop. Always drop it from the props - an explicit
        # key= on the Node wins, and anything left behind would be rejected by
        # the renderer's prop validation.
        forwarded = props.pop("key", None)
        key = self.key if self.key is not None else forwarded
        object.__setattr__(self, "props", props)
        if key is not None:
            object.__setattr__(self, "key", str(key))
            return
        # ``key_id`` names the native element, and events are routed by that
        # id, so adopting it as the key means re-authoring a tree patches the
        # elements already on screen instead of replacing them.
        named = props.get("key_id")
        if isinstance(named, str):
            object.__setattr__(self, "key", named)
            return
        object.__setattr__(self, "key", f"{self.kind}-{next(_KEY_COUNTER)}")
        object.__setattr__(self, "auto_key", True)

    # -- builders --------------------------------------------------------
    def _copy(self, **changes: Any) -> Node:
        """A copy of this node, keeping its key provenance.

        Reconstructing through the constructor would mark the copy's key as
        explicit, which would stop a refresh from carrying it across.
        """
        clone = replace(self, **changes)
        object.__setattr__(clone, "auto_key", self.auto_key)
        return clone

    def with_props(self, **props: Any) -> Node:
        """Return a copy with extra props merged in."""
        return self._copy(props={**self.props, **props})

    def with_children(self, *children: Any) -> Node:
        """Return a copy with different children."""
        return self._copy(children=_coerce_children(children))

    def keyed(self, key: str) -> Node:
        """Return a copy with an explicit key (useful inside generated lists)."""
        return Node(self.kind, self.props, self.children, key, self.origin)

    @property
    def id(self) -> str:
        return self.key or self.kind

    def __repr__(self) -> str:
        label = self.props.get("text") or self.props.get("label") or ""
        return f"<{self.kind}{' ' + str(label) if label else ''}>"


@dataclass(frozen=True)
class Raw(NodeBase):
    """An escape hatch for arbitrary native elements.

    ``build`` receives the backend's element factory (``ui``) and returns a
    native element. Any children attached to the node are added to the
    resulting element via the framework's container logic.
    """

    build: Callable[[Any], Any]
    children: tuple[NodeBase, ...] = ()
    key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "children", _coerce_children(self.children))
        if self.key is None:
            object.__setattr__(self, "key", f"raw-{next(_KEY_COUNTER)}")
        if not callable(self.build):
            raise ElementError("Raw.build must be callable")

    @property
    def id(self) -> str:
        return self.key or "raw"

    def __repr__(self) -> str:
        return f"<Raw {self.id}>"


@dataclass(frozen=True)
class TwoWay:
    """Marks a prop as bidirectionally bound, optionally with transforms.

    :param source: the :class:`~ResolveScript.ui.state.Value` holding the state.
    :param read: stored value -> the value the widget should show.
    :param write: the widget's new value -> the value to store.
    :param event: override the native event the write-back listens for.

    Without ``read``/``write`` the value round-trips unchanged, which is what
    most widgets want. Pair them to display a derived value and still edit the
    state behind it::

        amount = Value(50)
        Slider(value=TwoWay(amount, read=lambda a: a * 2, write=lambda v: v // 2))

    ``source`` must be settable, so binding a :class:`~ResolveScript.ui.state.Computed`
    raises — bind the value it derives from instead.
    """

    source: Any
    read: Callable[[Any], Any] | None = None
    write: Callable[[Any], Any] | None = None
    event: str | None = None

    def __post_init__(self) -> None:
        if self.source is None:
            raise ElementError("TwoWay requires a source value")


def node(
    kind: str,
    *children: Any,
    key: str | None = None,
    **props: Any,
) -> Node:
    """Build a :class:`Node` from a kind, keyword props and children.

    >>> node("button", key="go", text="Go", variant="primary")
    <button Go>
    """
    return Node(kind, props, _coerce_children(children), key)


def native(build: Callable[[Any], Any], *children: Any, key: str | None = None) -> Raw:
    """Wrap a native-element factory as a node (the escape hatch).

    >>> node("row", native(lambda ui: ui.SpinBox({"Value": 3})))
    """
    return Raw(build, _coerce_children(children), key)


def raw_element(
    type_name: str,
    props: Mapping[str, Any] | None = None,
    *children: Any,
    key: str | None = None,
) -> Raw:
    """Create a native element of ``type_name`` by name, e.g. ``"TextEdit"``.

    Equivalent to ``native(lambda ui: getattr(ui, type_name)(props, children))``
    but without the closure.
    """
    attributes = dict(props or {})

    def build(ui: Any) -> Any:
        factory = getattr(ui, type_name, None)
        if factory is None:
            raise ElementError(f"UIManager has no element type {type_name!r}")
        payload = list(_coerce_children(children))
        if not payload:
            return factory(attributes) if attributes else factory()
        return factory(attributes, payload) if attributes else factory(payload)

    return Raw(build, (), key)


def iter_nodes(root: NodeBase) -> Iterator[NodeBase]:
    """Depth-first iteration over a node tree."""
    stack: list[NodeBase] = [root]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def walk(root: NodeBase) -> Iterator[NodeBase]:
    """Alias for :func:`iter_nodes`, reading better in ``for x in walk(...)``."""
    return iter_nodes(root)
