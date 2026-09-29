"""The renderer: node tree in, live native widget tree out.

Design notes
------------

*Retained mode, not re-rendering.* When state changes the framework writes the
one native property that changed. Nothing is torn down, so focus, caret
position, scroll offset and selection all survive — which is what you want in
a tool you keep open next to a timeline.

*Bindings, not polls.* Every prop holding a :class:`~ResolveScript.ui.state.Value`
or :class:`~ResolveScript.ui.state.Computed` is subscribed once at mount time.
Two-way inputs also listen to the native change event and push values back,
behind a re-entrancy guard so a write cannot loop.

*Keyed reconciliation.* Children are matched by key, so re-rendering a list
reuses existing elements and only adds, removes or reorders what changed.
Spacing uses Fusion's own ``VGap``/``HGap`` elements, inserted automatically
from a container's ``gap``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .errors import BindingError, ElementError
from .events import adapt
from .node import Node, NodeBase, Raw, TwoWay
from .spec import ROWS, UNSET, PropSpec, WidgetSpec, events_to_enable, get_spec
from .state import Computed, Subscription, changed, is_reactive

# ``active`` is a function, so it is imported rather than the ``theme`` value:
# resolving it on every access means :func:`ResolveScript.ui.theme.use_theme`
# takes effect on renderers that were built before it was entered.
from .theme import Theme
from .theme import active as active_theme

__all__ = ["Renderer", "Bound", "AppRoot", "RowItem", "normalise_rows"]

VERTICAL = "vertical"
HORIZONTAL = "horizontal"

#: Container kinds and the axis their children are stacked along.
_AXES = {"column": VERTICAL, "row": HORIZONTAL, "stack": VERTICAL}

#: Native spacing element per axis.
_GAP_ELEMENTS = {VERTICAL: "VGap", HORIZONTAL: "HGap"}

#: Row keys the renderer understands, so a row can be written several ways.
_ROW_FIELDS = ("id", "tooltip", "icon", "selected", "expanded")


@dataclass
class RowItem:
    """A live ``TreeItem`` plus the row model that last produced it.

    Rows are diffed against these rather than rebuilt, so a table that updates
    a progress figure keeps its scroll offset, expansion and selection.
    """

    element: Any
    cells: list[str] = field(default_factory=list)
    selected: bool = False
    children: list[RowItem] = field(default_factory=list)

    def walk(self):
        """Depth-first iteration over this item and its descendants."""
        yield self
        for child in self.children:
            yield from child.walk()


def normalise_rows(rows: Any) -> list[dict[str, Any]]:
    """Accept the several shapes a row is naturally written in.

    A row may be a plain string, a sequence of cells, or a mapping::

        {"cells": [...], "children": [...], "selected": True, "id": "clip-1"}

    ``text`` is accepted as a synonym for ``cells`` so a list row and a
    :func:`~ResolveScript.ui.dsl.Tree` row can share one vocabulary.
    """
    if rows is None:
        return []
    if isinstance(rows, (str, bytes, Mapping)):
        rows = [rows]
    return [_normalise_row(entry) for entry in rows]


def _normalise_row(entry: Any) -> dict[str, Any]:
    if isinstance(entry, str):
        return {"cells": [entry], "children": []}
    if isinstance(entry, Mapping):
        if "cells" in entry:
            raw_cells: Any = entry["cells"]
        else:
            raw_cells = entry.get("text", [])
        row: dict[str, Any] = {
            "cells": _as_cells(raw_cells),
            "children": normalise_rows(entry.get("children")),
        }
        for key in _ROW_FIELDS:
            if entry.get(key) is not None:
                row[key] = entry[key]
        return row
    if isinstance(entry, (list, tuple)):
        return {"cells": _as_cells(entry), "children": []}
    raise ElementError(
        f"cannot use {entry!r} as a row; expected a string, a sequence of cells, "
        "or a mapping with a 'cells' key"
    )


def _as_cells(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (str, bytes)):
        return [raw if isinstance(raw, str) else raw.decode()]
    if is_reactive(raw):
        raise ElementError("row cells must be plain values, not a reactive source")
    return [cell if isinstance(cell, str) else str(cell) for cell in raw]


def _shape(rows: Sequence[Mapping[str, Any]]) -> tuple:
    """A comparable summary of a row tree's *structure* (not its content)."""
    return tuple(_shape(row.get("children") or ()) for row in rows)


def _item_shape(items: Sequence[RowItem]) -> tuple:
    return tuple(_item_shape(item.children) for item in items)



def _is_bound(value: Any) -> bool:
    """Whether a prop is driven by the binding layer rather than set directly.

    A :class:`~ResolveScript.ui.node.TwoWay` wrapper is not itself reactive, but
    it must still be routed through the subscription machinery rather than
    coerced straight onto the element.
    """
    return is_reactive(value) or isinstance(value, TwoWay)


@dataclass
class Bound:
    """A mounted node: its native element plus everything keeping it in sync."""

    key: str
    node: NodeBase
    element: Any
    spec: WidgetSpec | None
    theme: Theme = field(default_factory=active_theme)
    root: AppRoot | None = None
    children: dict[str, Bound] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    subscriptions: list[Subscription] = field(default_factory=list)
    applied: dict[str, Any] = field(default_factory=dict)
    collections: dict[str, list[Any]] = field(default_factory=dict)
    row_items: list[RowItem] = field(default_factory=list)
    syncing: bool = False
    gap: int = 0
    padding: int = 0

    @property
    def id(self) -> str:
        return self.key

    @property
    def element_id(self) -> str:
        """The native ``ID``, which is what events are routed by.

        It defaults to the node key but is overridden by ``key_id=``, so event
        wiring must always go through here rather than through :attr:`key`.
        """
        return str(self.applied.get("ID") or self.key)

    def _require_root(self) -> AppRoot:
        if self.root is None:
            raise BindingError(f"node {self.key!r} is not attached to a window")
        return self.root

    def get(self, prop: str) -> Any:
        """Read a native property off this element."""
        return self._require_root().backend.get_prop(self.element, prop)

    def set(self, prop: str, value: Any) -> None:
        """Write a native property directly, bypassing the reactive layer."""
        self._require_root().backend.set_prop(self.element, prop, value)

    def call(self, method: str, *args: Any) -> Any:
        """Call a native method, e.g. ``Click()`` or ``SetFocus()``."""
        return self._require_root().backend.call(self.element, method, *args)

    def focus(self) -> None:
        """Move keyboard focus to this element."""
        self.call("SetFocus", "OtherFocusReason")

    def find(self, key: str) -> Bound | None:
        """Find a mounted node by its key, or by the ``key_id`` it is given."""
        if self.key == key or self.element_id == key:
            return self
        for child in self.children.values():
            found = child.find(key)
            if found is not None:
                return found
        return None

    def walk(self):
        """Depth-first iteration over this subtree."""
        yield self
        for child in self.children.values():
            yield from child.walk()

    def rows(self) -> list[list[str]]:
        """The cell contents currently shown by this tree or list."""
        backend = self._require_root().backend
        return [list(backend.get_prop(item.element, "Text")) for item in self.row_items]

    def row_item(self, index: int) -> RowItem | None:
        """The native item behind row ``index`` — pass it to ``on_select``."""
        if 0 <= index < len(self.row_items):
            return self.row_items[index]
        return None

    def __repr__(self) -> str:
        kind = self.spec.kind if self.spec else "raw"
        return f"<Bound {kind} {self.key!r}>"


@dataclass
class AppRoot:
    """A mounted window/dialog: the backend handle plus event routing."""

    kind: str
    renderer: Renderer
    element: Any = None
    bound: Bound | None = None
    shown: bool = False
    closed: bool = False
    exit_code: int = 0

    @property
    def backend(self) -> Any:
        return self.renderer.backend

    @property
    def id(self) -> str:
        return self.bound.element_id if self.bound else "window"

    def on_close(self, callback: Callable[..., Any]) -> AppRoot:
        """Run ``callback`` when the user closes the window."""
        self.renderer.connect(self, self.element, self.id, "Close", callback)
        return self

    def show(self) -> AppRoot:
        """Display the window."""
        self.backend.show(self.element)
        self.shown = True
        return self

    def close(self, code: int = 0) -> None:
        """Close the window and stop its event loop."""
        self.closed = True
        self.exit_code = code
        with contextlib.suppress(Exception):  # pragma: no cover - closing is best effort
            self.backend.call(self.element, "Close")
        self.backend.exit_loop(code)

    def find(self, key: str) -> Bound | None:
        """Find a mounted node by key."""
        return self.bound.find(key) if self.bound else None

    def __repr__(self) -> str:
        return f"<AppRoot {self.kind!r} id={self.id!r}>"


class Renderer:
    """Mounts and updates node trees against a backend.

    :param strict: reject props a widget does not declare (default). A typo like
        ``tooltipe="…"`` would otherwise be silently dropped at the boundary.
    """

    def __init__(self, backend: Any, theme: Theme | None = None, strict: bool = True):
        self.backend = backend
        self._theme = theme
        self.strict = strict
        self.root: AppRoot | None = None

    @property
    def theme(self) -> Theme:
        """The theme in force: the explicit one, or the active global."""
        if self._theme is not None:
            return self._theme
        return active_theme()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def mount(self, node: NodeBase) -> AppRoot:
        """Build a window/dialog from ``node``."""
        if isinstance(node, Raw):
            raise ElementError(
                "the root node must be a window or dialog Node, not a Raw escape hatch"
            )
        if node.kind not in ("window", "dialog"):
            raise ElementError(
                f"the root node must be 'window' or 'dialog', got {node.kind!r}. "
                "Wrap your content in Window(...) or Dialog(...)."
            )
        spec = get_spec(node.kind)
        self.root = AppRoot(kind=node.kind, renderer=self)
        bound = self._mount(node, spec, self.root, parent_axis=None)
        self.root.bound = bound
        self.root.element = bound.element
        return self.root

    def update(self, node: NodeBase) -> None:
        """Re-apply ``node``, patching only what changed."""
        if self.root is None or self.root.bound is None:
            raise BindingError("update() called before mount()")
        if not isinstance(node, Node):
            raise ElementError("update() expects a Node; Raw trees must be remounted")
        self._sync(self.root.bound, node)

    def unmount(self) -> None:
        """Tear down the tree and release every subscription."""
        if self.root is not None:
            if self.root.bound is not None:
                self._dispose(self.root.bound)
            if self.root.element is not None:
                self.backend.destroy(self.root.element)
        self.root = None

    def find(self, key: str) -> Bound | None:
        """Find a mounted node by key."""
        if self.root is None or self.root.bound is None:
            return None
        return self.root.bound.find(key)

    def connect(
        self,
        root: AppRoot,
        element: Any,
        element_id: str,
        event: str,
        handler: Any,
    ) -> None:
        """Route a native event on ``element_id`` to a user callback."""
        adapted = adapt(handler)
        self.backend.connect(
            root.element,
            element_id,
            event,
            lambda data, e=event, t=element: adapted(data, e, t),
        )

    # ------------------------------------------------------------------
    # Mounting
    # ------------------------------------------------------------------
    def _mount(
        self,
        node: NodeBase,
        spec: WidgetSpec | None,
        root: AppRoot,
        parent_axis: str | None,
        parent: Bound | None = None,
    ) -> Bound:
        if isinstance(node, Raw):
            return self._mount_raw(node, root, parent)

        assert spec is not None
        theme = self._theme_for(node.props, parent)
        self._validate(spec, node.props)
        bound = Bound(
            key=node.id,
            node=node,
            element=None,
            spec=spec,
            theme=theme,
            root=root,
        )

        native_props = self._native_props(node, spec, theme)
        if spec.root:
            bound.element = self.backend.create_root(spec.kind, native_props, [])
        else:
            native_type = self._native_type(spec, node.props, parent_axis)
            bound.element = self.backend.create_element(native_type, native_props, [])

        bound.applied = dict(native_props)
        bound.gap = self._gap_of(node.props, spec, theme)
        bound.padding = self._padding_of(node.props, theme)

        self._apply_collections(bound, spec, node.props)
        self._wire_handlers(bound, spec, node.props)
        self._wire_bindings(bound, spec, node.props)

        if node.children and not spec.container:
            raise ElementError(
                f"{spec.kind!r} does not accept children (got {len(node.children)}). "
                "Group them in a Column(...) or Row(...)."
            )
        if spec.container:
            self._reconcile(bound, node.children, _AXES.get(spec.kind))
        return bound

    def _mount_raw(self, node: Raw, root: AppRoot, parent: Bound | None = None) -> Bound:
        element = node.build(self.backend.ui)
        if element is None:
            raise ElementError(f"Raw node {node.id!r} built {None!r}, expected an element")
        # Events are routed by native ID, so an escape-hatch element that did
        # not name one adopts the node key and is addressable like any other.
        if not self._existing_id(element):
            self.backend.set_prop(element, "ID", node.id)
        bound = Bound(
            key=node.id,
            node=node,
            element=element,
            spec=None,
            theme=parent.theme if parent is not None else self.theme,
            root=root,
        )
        bound.applied["ID"] = self._existing_id(element) or node.id
        for child_node in node.children:
            child = self._mount(child_node, self._spec_of(child_node), root, None, bound)
            bound.children[child.key] = child
            bound.order.append(child.key)
            self.backend.add_child(bound.element, child.element)
        return bound

    def _existing_id(self, element: Any) -> str | None:
        """The ID a native element already carries, if any."""
        try:
            existing = self.backend.get_prop(element, "ID")
        except Exception:
            return None
        return str(existing) if existing else None

    # ------------------------------------------------------------------
    # Updating
    # ------------------------------------------------------------------
    def _sync(self, bound: Bound, node: Node, parent: Bound | None = None) -> None:
        spec = bound.spec
        if spec is None:
            raise BindingError(
                f"{bound.key!r} is a Raw node and cannot be patched; remount the window instead."
            )
        if node.kind != spec.kind:
            self._swap_kind(bound, node)
            return

        bound.node = node
        bound.theme = self._theme_for(node.props, parent)
        self._validate(spec, node.props)
        self._sync_props(bound, spec, node.props, bound.theme)
        self._apply_collections(bound, spec, node.props)
        self._wire_handlers(bound, spec, node.props)
        self._wire_bindings(bound, spec, node.props)
        if spec.container:
            self._reconcile(bound, node.children, _AXES.get(spec.kind))

    def _swap_kind(self, bound: Bound, node: Node) -> None:
        """A different widget type appeared under the same key: replace it."""
        parent = self._parent_of(bound)
        spec = get_spec(node.kind)
        axis = _AXES.get(parent.spec.kind) if parent is not None and parent.spec else None
        fresh = self._mount(node, spec, bound.root or AppRoot("window", self), axis, parent)
        if parent is None:
            return
        slot = parent.order.index(bound.key)
        parent.children.pop(bound.key, None)
        parent.order[slot] = fresh.key
        parent.children[fresh.key] = fresh
        self.backend.remove_child(parent.element, bound.element)
        self.backend.add_child(parent.element, fresh.element)
        self._dispose(bound)
        self._reorder(parent)

    # ------------------------------------------------------------------
    # Child reconciliation
    # ------------------------------------------------------------------
    def _reconcile(
        self, bound: Bound, wanted: Sequence[NodeBase], axis: str | None
    ) -> None:
        """Align native children with ``wanted``, inserting spacing elements."""
        if axis is None:
            axis = (
                VERTICAL
                if bound.spec and bound.spec.native_type == "VGroup"
                else HORIZONTAL
            )

        wanted_keys = [child.id for child in wanted]
        for key in list(bound.order):
            if key not in wanted_keys:
                self._retire(bound, key)

        for child_node in wanted:
            if child_node.id in bound.children:
                existing = bound.children[child_node.id]
                if isinstance(existing.node, Node) and isinstance(child_node, Node):
                    self._sync(existing, child_node, bound)
                continue
            child = self._mount(
                child_node, self._spec_of(child_node), bound.root or self._root(), axis, bound
            )
            bound.children[child.key] = child

        bound.order = [key for key in wanted_keys if key in bound.children]
        self._sync_gaps(bound, axis)
        if bound.spec and bound.spec.kind == "stack":
            self._apply_stack(bound)
        self._reorder(bound)

    def _root(self) -> AppRoot:
        if self.root is None:  # pragma: no cover - guarded by call sites
            raise BindingError("no mounted window")
        return self.root

    def _retire(self, bound: Bound, key: str) -> None:
        stale = bound.children.pop(key, None)
        if stale is None:
            return
        if key in bound.order:
            bound.order.remove(key)
        self.backend.remove_child(bound.element, stale.element)
        self._dispose(stale)

    def _sync_gaps(self, bound: Bound, axis: str) -> None:
        """Create or drop the ``VGap``/``HGap`` elements implied by ``gap``."""
        prefix = f"{bound.key}\x00gap"
        gap_type = _GAP_ELEMENTS.get(axis, "VGap")
        needed = max(0, len(bound.order) - 1) if bound.gap > 0 else 0

        for key in [k for k in bound.children if k.startswith(prefix)]:
            if int(key[len(prefix) :]) >= needed:
                gap = bound.children.pop(key)
                self.backend.remove_child(bound.element, gap.element)
                self._dispose(gap)

        for index in range(needed):
            key = f"{prefix}{index}"
            if key in bound.children:
                continue
            element = self.backend.create_element(gap_type, {"Size": bound.gap}, [])
            bound.children[key] = Bound(
                key=key, node=element, element=element, spec=None, root=bound.root
            )

    def _apply_stack(self, bound: Bound) -> None:
        """Show only the child at ``index``, hiding the rest."""
        active = self._resolve_number(bound, "index", 0)
        for index, key in enumerate(bound.order):
            child = bound.children[key]
            self.backend.set_prop(child.element, "Visible", index == active)

    def _reorder(self, bound: Bound) -> None:
        """Make the native child order match the logical order, gaps included."""
        axis = _AXES.get(bound.spec.kind) if bound.spec else None
        if axis is None:
            axis = (
                VERTICAL
                if bound.spec and bound.spec.native_type == "VGroup"
                else HORIZONTAL
            )
        prefix = f"{bound.key}\x00gap"

        real = [bound.children[key] for key in bound.order if key in bound.children]
        desired: list[Any] = []
        for index, child in enumerate(real):
            desired.append(child.element)
            if index < len(real) - 1:
                gap = bound.children.get(f"{prefix}{index}")
                if gap is not None:
                    desired.append(gap.element)

        current = self.backend.children_of(bound.element)
        if current == desired:
            return
        if len(current) < len(desired) and current == desired[: len(current)]:
            # Pure append — the common case, and cheap to do incrementally.
            for element in desired[len(current) :]:
                self.backend.add_child(bound.element, element)
            return
        for element in current:
            if element not in desired:
                self.backend.remove_child(bound.element, element)
        for element in desired:
            if element in current:
                self.backend.remove_child(bound.element, element)
            self.backend.add_child(bound.element, element)

    # ------------------------------------------------------------------
    # Props
    # ------------------------------------------------------------------
    def _validate(self, spec: WidgetSpec, props: Mapping[str, Any]) -> None:
        """Reject props the widget does not declare, rather than dropping them.

        A silently-ignored ``variantn="primary"`` is the sort of bug that
        survives to a demo, so the boundary is checked instead.
        """
        if not self.strict:
            return
        unknown = sorted(
            name
            for name in props
            if name not in spec.props
            and not (name.startswith("on_") and spec.native_event(name))
        )
        if unknown:
            events = sorted(spec.events)
            known = sorted(spec.props)
            extra = f" Events: {events}." if events else ""
            raise ElementError(
                f"{spec.kind!r} has no prop(s) {unknown}. Known props: {known}.{extra}"
            )

    def _native_props(
        self, node: Node, spec: WidgetSpec, theme: Theme
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        enabled = self._events_needed(node.props, spec)
        if enabled:
            out["Events"] = enabled

        for name, prop in spec.props.items():
            if prop.internal:
                continue
            value = node.props.get(name, prop.default)
            if value is UNSET or value is None or _is_bound(value):
                continue
            out[prop.native] = _coerce(prop, value)

        # An explicit ID always wins so scripts can address elements by name.
        out["ID"] = node.props.get("key_id") or node.id
        if spec.root:
            out.setdefault("WindowTitle", "ResolveScript")
        sheet = self._stylesheet_for(spec, node.props, theme)
        if sheet:
            out["StyleSheet"] = sheet
        return out

    def _sync_props(
        self, bound: Bound, spec: WidgetSpec, props: Mapping[str, Any], theme: Theme
    ) -> None:
        bound.gap = self._gap_of(props, spec, theme)
        bound.padding = self._padding_of(props, theme)

        # Checked before the generic loop, which would otherwise write the new
        # ID straight past the guard.
        element_id = props.get("key_id") or bound.key
        applied_id = bound.applied.get("ID")
        if applied_id != element_id:
            if applied_id is not None:
                raise ElementError(
                    f"{bound.key!r}: key_id cannot change after mount, because "
                    f"events are routed by id ({applied_id!r} -> {element_id!r})"
                )
            self.backend.set_prop(bound.element, "ID", element_id)
            bound.applied["ID"] = element_id

        for name, prop in spec.props.items():
            if prop.internal or prop.via or name == "key_id":
                continue
            if name not in props and prop.default is UNSET:
                continue
            value = props.get(name, prop.default)
            if value is UNSET or value is None or _is_bound(value):
                continue
            native_value = _coerce(prop, value)
            if bound.applied.get(prop.native) == native_value:
                continue
            self.backend.set_prop(bound.element, prop.native, native_value)
            bound.applied[prop.native] = native_value

        sheet = self._stylesheet_for(spec, props, theme)
        if sheet and bound.applied.get("StyleSheet") != sheet:
            self.backend.set_prop(bound.element, "StyleSheet", sheet)
            bound.applied["StyleSheet"] = sheet

    def _stylesheet_for(
        self, spec: WidgetSpec, props: Mapping[str, Any], theme: Theme
    ) -> str:
        if spec.root:
            sheet = theme.window_stylesheet()
        else:
            sheet = theme.stylesheet(spec.kind, spec.variant_of(props))
        padding = self._padding_of(props, theme)
        if padding and spec.container:
            sheet = f"{sheet} QWidget {{ padding: {padding}px; }}"
        return sheet

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _events_needed(self, props: Mapping[str, Any], spec: WidgetSpec) -> dict[str, bool]:
        names: list[str] = []
        for name in props:
            if name.startswith("on_"):
                mapped = spec.native_event(name)
                if mapped:
                    names.append(mapped)
        for prop in spec.two_way_props().values():
            value = props.get(prop.name)
            if (is_reactive(value) or isinstance(value, TwoWay)) and prop.event:
                names.append(prop.event)
        return events_to_enable(names)

    def _wire_handlers(
        self, bound: Bound, spec: WidgetSpec, props: Mapping[str, Any]
    ) -> None:
        if bound.root is None:  # pragma: no cover - always set during mount
            return
        for name, handler in props.items():
            if not name.startswith("on_"):
                continue
            event = spec.native_event(name)
            if not event or handler is None:
                continue
            self.connect(bound.root, bound.element, bound.element_id, event, handler)

    # ------------------------------------------------------------------
    # Bindings
    # ------------------------------------------------------------------
    def _wire_bindings(
        self, bound: Bound, spec: WidgetSpec, props: Mapping[str, Any]
    ) -> None:
        for name, prop in spec.props.items():
            if prop.via or name not in props:
                continue
            raw = props[name]
            explicit = raw if isinstance(raw, TwoWay) else None
            source = explicit.source if explicit is not None else raw
            if not is_reactive(source):
                continue

            if prop.internal:
                # An internal prop steers a structural decision rather than a
                # native property, so it needs its own subscriber.
                if name == "index" and spec.kind == "stack":
                    bound.subscriptions.append(
                        source.subscribe(lambda _v, b=bound: self._apply_stack(b))
                    )
                continue

            two_way = explicit is not None or prop.two_way
            read = explicit.read if explicit is not None else None
            write = (
                explicit.write
                if explicit is not None and explicit.write is not None
                else prop.from_native
            )
            event = (
                explicit.event
                if explicit is not None and explicit.event
                else (prop.event if two_way else None)
            )
            # A Computed has no storage of its own, so it can be displayed but
            # not written to. Two-way over one is a mistake rather than a
            # silently dead widget, so it is reported instead.
            if explicit is not None and isinstance(source, Computed) and explicit.write is None:
                raise BindingError(
                    f"{spec.kind!r}.{name}: TwoWay needs a write= to edit a Computed, "
                    "or a settable source — bind the value the Computed derives from"
                )

            def apply(current: Any, b=bound, p=prop, r=read) -> None:
                payload = r(current) if r is not None else current
                native_value = _coerce(p, payload)
                if b.applied.get(p.native) == native_value:
                    return
                b.syncing = True
                try:
                    self.backend.set_prop(b.element, p.native, native_value)
                    b.applied[p.native] = native_value
                finally:
                    b.syncing = False

            if event and two_way and not isinstance(source, Computed) and bound.root is not None:

                def push_back(
                    _data: Mapping[str, Any],
                    b=bound,
                    p=prop,
                    w=write,
                    s=source,
                ) -> None:
                    if b.syncing:
                        return
                    new_value = w(self.backend.get_prop(b.element, p.native))
                    if not changed(s.get(), new_value):
                        return
                    b.syncing = True
                    try:
                        s.set(new_value)
                    finally:
                        b.syncing = False

                self.backend.connect(bound.root.element, bound.element_id, event, push_back)

            bound.subscriptions.append(source.subscribe(apply, immediate=True))

    # ------------------------------------------------------------------
    # Collections applied through methods
    # ------------------------------------------------------------------
    def _apply_collections(
        self, bound: Bound, spec: WidgetSpec, props: Mapping[str, Any]
    ) -> None:
        for name, prop in spec.props.items():
            if not prop.via or name not in props:
                continue
            raw = props[name]
            source = raw.source if isinstance(raw, TwoWay) else raw
            if is_reactive(source):
                # Immediate: an empty combo box on first paint is never right.
                bound.subscriptions.append(
                    source.subscribe(
                        lambda v, b=bound, p=prop: self._fill(b, p, v), immediate=True
                    )
                )
                continue
            self._fill(bound, prop, raw)

    def _fill(self, bound: Bound, prop: PropSpec, raw: Any) -> None:
        if prop.strategy == ROWS:
            self._fill_rows(bound, raw)
            return
        items = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
        if bound.collections.get(prop.name) == items:
            return
        if prop.each:
            self._fill_each(bound, prop, items)
        else:
            self.backend.call(bound.element, prop.via, items)
        bound.collections[prop.name] = items

    def _fill_each(self, bound: Bound, prop: PropSpec, items: list[Any]) -> None:
        """Apply a one-native-call-per-item list as a minimal edit.

        The common prefix is left alone, so growing a tab bar appends only the
        new tabs and the tabs already on screen keep their identity (and their
        index). Anything past the prefix is removed and the remainder appended,
        which also covers the wholesale-replacement case: a tab bar has no
        ``clear``, so everything is removed and re-added instead.
        """
        previous: list[Any] = bound.collections.get(prop.name) or []
        keep = 0
        for old, new in zip(previous, items):
            if old != new:
                break
            keep += 1

        if keep < len(previous):
            if prop.remove is None:
                raise ElementError(
                    f"{prop.name!r} changed but {prop.via!r} has no paired removal "
                    "method; add one to the spec as remove=..."
                )
            for _ in range(len(previous) - keep):
                self.backend.call(bound.element, prop.remove, keep)
        for item in items[keep:]:
            self.backend.call(bound.element, prop.via, item)

    # ------------------------------------------------------------------
    # Tree rows
    # ------------------------------------------------------------------
    def _fill_rows(self, bound: Bound, raw: Any) -> None:
        """Sync a tree's rows, rebuilding only when the shape actually changes.

        Cells are written straight onto the existing ``TreeItem``s, so a live
        table keeps its scroll position, expanded branches and selection while
        its data changes underneath.
        """
        rows = normalise_rows(raw)
        first_fill = "rows" not in bound.collections
        if not first_fill and _item_shape(bound.row_items) == _shape(rows):
            self._update_rows(bound.row_items, rows)
        elif first_fill and not rows:
            bound.row_items = []
        else:
            self.backend.call(bound.element, "Clear")
            bound.row_items = []
            for row in rows:
                item = self._make_row(row)
                self.backend.call(bound.element, "AddTopLevelItem", item.element)
                bound.row_items.append(item)
        bound.collections["rows"] = rows

    def _make_row(self, row: Mapping[str, Any]) -> RowItem:
        properties: dict[str, Any] = {"Text": list(row["cells"])}
        if row.get("id") is not None:
            properties["ID"] = str(row["id"])
        if row.get("tooltip") is not None:
            properties["ToolTip"] = _as_cells(row["tooltip"])
        if row.get("icon") is not None:
            properties["Icon"] = _as_cells(row["icon"])
        element = self.backend.create_item("TreeItem", properties)
        item = RowItem(element=element, cells=list(row["cells"]))
        if row.get("selected"):
            self.backend.set_prop(element, "Selected", True)
            item.selected = True
        if row.get("expanded") and row.get("children"):
            self.backend.set_prop(element, "Expanded", True)
        for child_row in row.get("children") or ():
            child = self._make_row(child_row)
            self.backend.call(element, "AddChild", child.element)
            item.children.append(child)
        return item

    def _update_rows(self, items: Sequence[RowItem], rows: Sequence[Mapping[str, Any]]) -> None:
        for item, row in zip(items, rows):
            if item.cells != row["cells"]:
                self.backend.set_prop(item.element, "Text", list(row["cells"]))
                item.cells = list(row["cells"])
            wanted = bool(row.get("selected", False))
            if wanted != item.selected:
                self.backend.set_prop(item.element, "Selected", wanted)
                item.selected = wanted
            self._update_rows(item.children, row.get("children") or ())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _spec_of(self, node: NodeBase) -> WidgetSpec | None:
        return None if isinstance(node, Raw) else get_spec(node.kind)

    def _native_type(
        self, spec: WidgetSpec, props: Mapping[str, Any], axis: str | None
    ) -> str:
        if spec.kind == "spacer":
            horizontal = bool(props.get("horizontal", True))
            vertical = bool(props.get("vertical", False))
            if horizontal and not vertical:
                return "HGroup"
            if vertical and not horizontal:
                return "VGroup"
            # Both, or neither: follow the axis the parent stacks along.
            return "HGroup" if axis == HORIZONTAL else "VGroup"
        if spec.kind == "divider":
            return "VLine" if props.get("orientation") == "vertical" else "HLine"
        return spec.native_type

    def _theme_for(self, props: Mapping[str, Any], parent: Bound | None = None) -> Theme:
        """A node's theme: its own, else its nearest themed ancestor."""
        chosen = props.get("theme")
        if isinstance(chosen, Theme):
            return chosen
        return parent.theme if parent is not None else self.theme

    def _resolve_number(self, bound: Bound, name: str, default: int) -> int:
        if not isinstance(bound.node, Node):
            return default
        value = bound.node.props.get(name, default)
        if is_reactive(value):
            value = value.get()
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _gap_of(
        self, props: Mapping[str, Any], spec: WidgetSpec, theme: Theme
    ) -> int:
        prop = spec.props.get("gap")
        if prop is None:
            return 0
        return _as_int(props.get("gap", prop.default), theme.gap)

    def _padding_of(self, props: Mapping[str, Any], theme: Theme) -> int:
        return _as_int(props.get("padding", 0), theme.gap)

    # -- teardown --------------------------------------------------------
    def _parent_of(self, bound: Bound) -> Bound | None:
        if self.root is None or self.root.bound is None:
            return None
        for candidate in self.root.bound.walk():
            for child in candidate.children.values():
                if child is bound:
                    return candidate
        return None

    def _dispose(self, bound: Bound) -> None:
        for subscription in bound.subscriptions:
            subscription.unsubscribe()
        bound.subscriptions.clear()
        for child in list(bound.children.values()):
            self._dispose(child)
        bound.children.clear()
        bound.order.clear()
        bound.row_items.clear()


def _coerce(prop: PropSpec, value: Any) -> Any:
    """Apply a prop's transform, reporting failures in terms of the prop."""
    try:
        return prop.to_native(value)
    except ElementError:
        raise
    except Exception as exc:
        raise ElementError(
            f"invalid value for {prop.name!r}: {value!r} ({exc})"
        ) from exc


def _as_int(value: Any, resolve) -> int:
    if value is UNSET or value is None:
        return 0
    if is_reactive(value):
        value = value.get()
    if isinstance(value, str):
        try:
            return resolve(value)
        except KeyError:
            return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
