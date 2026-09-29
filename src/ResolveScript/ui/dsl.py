"""The authoring API: composition functions that return nodes.

This is the primary way to describe a UI::

    from ResolveScript.ui import Column, Row, Button, TextField, Window, run

    name = Value("Sequence 01")

    Window(
        title="Render",
        children=(
            Column(
                Row(TextField(value=name), Button("Apply", on_click=save)),
                Separator(),
                Row(Button("Render", variant="primary")),
                align="right",
                gap="sm",
            ),
            gap="md",
            padding="md",
        ),
    )

Every function is a thin wrapper over :class:`~ResolveScript.ui.node.Node`, so
anything the DSL cannot express is still reachable — see
:func:`~ResolveScript.ui.node.node` and
:func:`~ResolveScript.ui.node.native`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .errors import ElementError
from .node import Node
from .state import Value, is_reactive
from .theme import Theme

__all__ = [
    # roots
    "Window",
    "Dialog",
    # layout
    "Column",
    "Row",
    "Stack",
    "Card",
    "Group",
    "ScrollArea",
    "Spacer",
    "Divider",
    # text
    "Label",
    "Heading",
    "Title",
    "Muted",
    # actions
    "Button",
    "IconButton",
    "PrimaryButton",
    "DangerButton",
    # inputs
    "TextField",
    "PasswordField",
    "TextArea",
    "Number",
    "Slider",
    "Check",
    "Switch",
    "Radio",
    "Combo",
    "ColorPicker",
    "Progress",
    # collections
    "Tabs",
    "Tree",
    "List",
    "Icon",
    # helpers
    "row",
    "column",
]


def _flatten(children: Sequence[Any]) -> tuple[Any, ...]:
    out: list[Any] = []
    for child in children:
        if child is None:
            continue
        if isinstance(child, (list, tuple)):
            out.extend(_flatten(child))
        else:
            out.append(child)
    return tuple(out)


def _with_children(
    props: dict[str, Any], children: Sequence[Any]
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    """Split a ``children=[...]`` keyword out of ``**props``.

    Both spellings read well, and silently treating ``children=`` as a prop is
    exactly the sort of mistake the renderer's validation would then reject.
    """
    extra = props.pop("children", None)
    merged = tuple(children)
    if extra:
        merged = (*_flatten(extra), *merged)
    return props, _flatten(merged)


def _items(value: Any) -> Any:
    """Materialise a sequence prop, leaving a reactive source untouched.

    ``rows=Value(rows)`` has to stay a subscription, not become a snapshot.
    """
    if is_reactive(value):
        return value
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    return list(value)


def _static_items(value: Any, what: str) -> list[Any]:
    if is_reactive(value):
        raise ElementError(
            f"{what} must be a static list; a tree/list of rows already updates "
            "itself, but tab labels are fixed at build time"
        )
    return _items(value)


# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------


def Window(
    title: str = "ResolveScript",
    *children: Any,
    geometry: Sequence[int] | None = None,
    min_size: Sequence[int] | None = None,
    theme: Theme | None = None,
    on_close: Callable[..., Any] | None = None,
    **props: Any,
) -> Node:
    """A top-level window.

    :param title: text in the title bar.
    :param geometry: ``(x, y, width, height)``.
    :param min_size: ``(width, height)`` the user cannot shrink below.
    :param on_close: called when the user closes the window.

    Children may be passed positionally or as ``children=[...]``; a ``theme=``
    here applies to the window and everything inside it.
    """
    payload, children = _with_children(props, children)
    payload["title"] = title
    if geometry is not None:
        payload["geometry"] = geometry
    if min_size is not None:
        payload["min_size"] = min_size
    if on_close is not None:
        payload["on_close"] = on_close
    if theme is not None:
        payload["theme"] = theme
    return Node("window", payload, children)


def Dialog(
    title: str = "Dialog",
    *children: Any,
    on_close: Callable[..., Any] | None = None,
    **props: Any,
) -> Node:
    """A modal dialog window."""
    payload, children = _with_children(props, children)
    payload["title"] = title
    if on_close is not None:
        payload["on_close"] = on_close
    return Node("dialog", payload, children)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def Column(*children: Any, gap: Any = "sm", **props: Any) -> Node:
    """Stack children vertically. ``gap`` takes a token or pixels."""
    payload, children = _with_children(props, children)
    payload["gap"] = gap
    return Node("column", payload, children)


def Row(*children: Any, gap: Any = "sm", **props: Any) -> Node:
    """Lay children out horizontally."""
    payload, children = _with_children(props, children)
    payload["gap"] = gap
    return Node("row", payload, children)


def Stack(*children: Any, index: Any = 0, **props: Any) -> Node:
    """Mount every child but show only the one at ``index``.

    ``index`` may be a :class:`~ResolveScript.ui.state.Value`, which lets a
    tab bar and its content share a single source of truth.
    """
    payload, children = _with_children(props, children)
    payload["index"] = index
    return Node("stack", payload, children)


def Card(*children: Any, gap: Any = "md", **props: Any) -> Node:
    """A rounded, bordered surface — the standard grouping container."""
    payload, children = _with_children(props, children)
    payload["gap"] = gap
    return Node("card", payload, children)


def Group(title: str, *children: Any, gap: Any = "sm", **props: Any) -> Node:
    """A titled group box."""
    payload, children = _with_children(props, children)
    payload.update({"title": title, "gap": gap})
    return Node("group", payload, children)


def ScrollArea(*children: Any, **props: Any) -> Node:
    """A scrollable region; set ``weight=1`` to let it fill the window."""
    payload, children = _with_children(props, children)
    return Node("scroll_area", payload, children)


def Spacer(horizontal: bool = True, vertical: bool = False, size: int | None = None) -> Node:
    """Flexible empty space.

    Inside a :func:`Row` this pushes siblings apart; inside a :func:`Column`
    it absorbs leftover height. Pass ``size`` for a fixed gap instead, or
    ``vertical=True`` to stretch downwards.
    """
    props: dict[str, Any] = {"horizontal": horizontal, "vertical": vertical}
    if size is not None:
        props["fixed_size"] = (size, size) if horizontal != vertical else (size, 0)
    return Node("spacer", props)


def Divider(orientation: str = "horizontal", **props: Any) -> Node:
    """A separator line."""
    return Node("divider", {"orientation": orientation, **props})


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


def Label(
    text: Any = "",
    *,
    variant: str | None = None,
    align: str = "left",
    word_wrap: bool = False,
    on_click: Callable[..., Any] | None = None,
    **props: Any,
) -> Node:
    """Static or bound text.

    ``variant`` picks a colour/weight preset: ``default``, ``muted``,
    ``subtle``, ``accent``, ``heading``, ``title``, ``danger``, ``success``.
    """
    payload: dict[str, Any] = {"text": text, "align": align, "word_wrap": word_wrap, **props}
    if variant is not None:
        payload["variant"] = variant
    if on_click is not None:
        payload["on_click"] = on_click
    return Node("label", payload)


def Heading(text: Any, **props: Any) -> Node:
    """Bold, slightly larger text — a section heading."""
    return Label(text, variant="heading", **props)


def Title(text: Any, **props: Any) -> Node:
    """Large bold text for a window or card title."""
    return Label(text, variant="title", **props)


def Muted(text: Any, **props: Any) -> Node:
    """De-emphasised supporting text."""
    return Label(text, variant="muted", **props)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def Button(
    text: str = "",
    on_click: Callable[..., Any] | None = None,
    *,
    variant: str = "default",
    tooltip: str | None = None,
    icon: str | None = None,
    enabled: Any = True,
    checkable: bool = False,
    **props: Any,
) -> Node:
    """A push button.

    ``variant`` is one of ``default``, ``primary``, ``ghost``, ``danger`` or
    ``success``. ``on_click`` may take zero arguments or a single
    :class:`~ResolveScript.ui.events.Event`.
    """
    payload: dict[str, Any] = {
        "text": text,
        "variant": variant,
        "enabled": enabled,
        "checkable": checkable,
        **props,
    }
    if tooltip is not None:
        payload["tooltip"] = tooltip
    if icon is not None:
        payload["icon"] = icon
    if on_click is not None:
        payload["on_click"] = on_click
    return Node("button", payload)


def PrimaryButton(text: str, on_click: Callable[..., Any] | None = None, **props: Any) -> Node:
    """Shorthand for ``Button(text, variant="primary")``."""
    return Button(text, on_click, variant="primary", **props)


def DangerButton(text: str, on_click: Callable[..., Any] | None = None, **props: Any) -> Node:
    """Shorthand for the destructive-action style."""
    return Button(text, on_click, variant="danger", **props)


def IconButton(icon: str, on_click: Callable[..., Any] | None = None, **props: Any) -> Node:
    """An icon-only button, usually given a ``tooltip`` for accessibility."""
    payload = {"icon": icon, "variant": "ghost", **props}
    if on_click is not None:
        payload["on_click"] = on_click
    return Node("button", payload)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def TextField(
    value: Any = "",
    *,
    placeholder: str = "",
    on_change: Callable[..., Any] | None = None,
    on_submit: Callable[..., Any] | None = None,
    read_only: bool = False,
    tooltip: str | None = None,
    max_length: int | None = None,
    clear_button: bool = False,
    **props: Any,
) -> Node:
    """A single-line text input.

    Pass a :class:`~ResolveScript.ui.state.Value` as ``value`` for two-way
    binding: the field writes every keystroke back to it.
    """
    payload: dict[str, Any] = {
        "value": value,
        "placeholder": placeholder,
        "read_only": read_only,
        **props,
    }
    if max_length is not None:
        payload["max_length"] = max_length
    if clear_button:
        payload["clear_button"] = True
    if tooltip is not None:
        payload["tooltip"] = tooltip
    if on_change is not None:
        payload["on_change"] = on_change
    if on_submit is not None:
        payload["on_submit"] = on_submit
    return Node("text_field", payload)


def PasswordField(**props: Any) -> Node:
    """A masked text input."""
    return Node("text_field", {"password": True, **props})


def TextArea(
    value: Any = "",
    *,
    placeholder: str = "",
    on_change: Callable[..., Any] | None = None,
    read_only: bool = False,
    **props: Any,
) -> Node:
    """A multi-line text input."""
    payload: dict[str, Any] = {"value": value, "placeholder": placeholder, **props}
    if read_only:
        payload["read_only"] = True
    if on_change is not None:
        payload["on_change"] = on_change
    return Node("text_area", payload)


def Number(
    value: Any = 0,
    *,
    minimum: float = 0,
    maximum: float = 100,
    step: int = 1,
    on_change: Callable[..., Any] | None = None,
    suffix: str | None = None,
    **props: Any,
) -> Node:
    """A numeric stepper. Bind ``value`` to a ``Value`` for two-way updates."""
    payload: dict[str, Any] = {
        "value": value,
        "minimum": minimum,
        "maximum": maximum,
        "step": step,
        **props,
    }
    if suffix is not None:
        payload["suffix"] = suffix
    if on_change is not None:
        payload["on_change"] = on_change
    return Node("number", payload)


def Slider(
    value: Any = 0,
    *,
    minimum: float = 0,
    maximum: float = 100,
    step: float = 1,
    orientation: str = "horizontal",
    on_change: Callable[..., Any] | None = None,
    **props: Any,
) -> Node:
    """A draggable slider."""
    payload: dict[str, Any] = {
        "value": value,
        "minimum": minimum,
        "maximum": maximum,
        "step": step,
        "orientation": orientation,
        **props,
    }
    if on_change is not None:
        payload["on_change"] = on_change
    return Node("slider", payload)


def Check(
    text: str = "",
    checked: Any = False,
    *,
    on_change: Callable[..., Any] | None = None,
    **props: Any,
) -> Node:
    """A checkbox. Bind ``checked`` to a ``Value`` for two-way updates."""
    payload: dict[str, Any] = {"text": text, "checked": checked, **props}
    if on_change is not None:
        payload["on_change"] = on_change
    return Node("check", payload)


def Switch(checked: Any = False, *, on_change: Callable[..., Any] | None = None, **props: Any) -> Node:
    """A checkbox styled as a switch (no label)."""
    payload: dict[str, Any] = {"checked": checked, **props}
    if on_change is not None:
        payload["on_change"] = on_change
    return Node("switch", payload)


def Radio(
    text: str = "",
    checked: Any = False,
    *,
    on_change: Callable[..., Any] | None = None,
    **props: Any,
) -> Node:
    """A radio-style option. Pair with a shared ``Value`` via RadioGroup."""
    payload: dict[str, Any] = {"text": text, "checked": checked, **props}
    if on_change is not None:
        payload["on_change"] = on_change
    return Node("radio", payload)


def Combo(
    items: Sequence[str],
    value: Any = 0,
    *,
    on_change: Callable[..., Any] | None = None,
    **props: Any,
) -> Node:
    """A dropdown of ``items``; ``value`` is the selected index.

    Bind ``value`` to a ``Value`` to keep a selection in sync across rebuilds.
    """
    payload: dict[str, Any] = {"items": _items(items), "value": value, **props}
    if on_change is not None:
        payload["on_change"] = on_change
    return Node("combo", payload)


def ColorPicker(
    value: Any = None,
    *,
    alpha: bool = True,
    on_change: Callable[..., Any] | None = None,
    **props: Any,
) -> Node:
    """A colour chooser. ``value`` is an RGBA sequence or a hex string."""
    from .theme import Color

    if value is None:
        payload_value: Any = Color(255, 255, 255, 255 if alpha else 255)
    elif isinstance(value, str) and not is_reactive(value):
        payload_value = Color.from_hex(value)
    else:
        payload_value = value
    payload: dict[str, Any] = {"value": payload_value, "alpha": alpha, **props}
    if on_change is not None:
        payload["on_change"] = on_change
    return Node("color", payload)


def Progress(
    value: Any = 0,
    *,
    minimum: float = 0,
    maximum: float = 100,
    text: str | None = None,
    **props: Any,
) -> Node:
    """A progress bar. Bind ``value`` to a ``Value`` to animate it."""
    payload: dict[str, Any] = {"value": value, "minimum": minimum, "maximum": maximum, **props}
    if text is not None:
        payload["text"] = text
    return Node("progress", payload)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def Tabs(
    items: Sequence[str],
    *pages: Any,
    value: Any = 0,
    on_change: Callable[..., Any] | None = None,
    key_prefix: str = "tab",
    **props: Any,
) -> Node:
    """A tab bar with a content stack.

    Renders one tab button per entry in ``items`` and shows the matching page.
    ``items`` may be plain strings or ``(label, tooltip)`` pairs.

    Pass a :class:`~ResolveScript.ui.state.Value` as ``value`` when the active
    tab needs to survive a rebuild; otherwise an internal value is created and
    ``on_change`` still fires.
    """
    entries = _static_items(items, "Tabs(items=)")
    labels = [entry[0] if isinstance(entry, (tuple, list)) else entry for entry in entries]
    tooltips = [
        entry[1] for entry in entries if isinstance(entry, (tuple, list)) and len(entry) > 1
    ]

    internal = is_reactive(value)
    index: Any = value if internal else Value(value)

    def tab_changed(event: Any) -> None:
        new_index = event.index if event.index is not None else index.get()
        if not internal:
            index.set(new_index)
        if on_change is not None:
            on_change(event)

    bar_props: dict[str, Any] = {
        "items": labels,
        "value": index,
        "on_change": tab_changed,
        **props,
    }
    if tooltips:
        bar_props["tooltips"] = tooltips

    bar = Node("tabs", bar_props, key=f"{key_prefix}-bar")
    body = Stack(
        *pages,
        index=index,
        gap=0,
        key=f"{key_prefix}-body",
    )
    return Column(bar, body, gap="xs", key=key_prefix, weight=1)


def Tree(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]] = (),
    *,
    on_select: Callable[..., Any] | None = None,
    on_double_click: Callable[..., Any] | None = None,
    header: bool = True,
    sorting: bool = True,
    **props: Any,
) -> Node:
    """A hierarchical table.

    ``rows`` entries are dicts::

        {"cells": ["A001", "24 fps"],
         "children": [...],
         "selected": True}

    Cells and structure are diffed, so in-place updates (a renamed clip, a
    progress figure) do not reset the tree's expansion state.
    """
    payload: dict[str, Any] = {
        "columns": list(columns),
        "rows": _items(rows),
        "header_hidden": not header,
        "sorting": sorting,
        **props,
    }
    if on_select is not None:
        payload["on_select"] = on_select
    if on_double_click is not None:
        payload["on_double_click"] = on_double_click
    return Node("tree", payload)


def List(
    rows: Sequence[Any] = (),
    *,
    on_select: Callable[..., Any] | None = None,
    on_double_click: Callable[..., Any] | None = None,
    **props: Any,
) -> Node:
    """A single-column list.

    Accepts plain strings, sequences of cells, or the same row mappings as
    :func:`Tree` when a row needs to carry more than its text.
    """
    payload: dict[str, Any] = {
        "columns": [],
        "rows": _items(rows),
        "header_hidden": True,
        **props,
    }
    if on_select is not None:
        payload["on_select"] = on_select
    if on_double_click is not None:
        payload["on_double_click"] = on_double_click
    return Node("list", payload)


def Icon(file: str, **props: Any) -> Node:
    """An icon loaded from a file path."""
    return Node("icon", {"file": file, **props})


# ---------------------------------------------------------------------------
# Lower-case aliases, for codebases that prefer function-style naming
# ---------------------------------------------------------------------------


def row(*children: Any, **props: Any) -> Node:
    """Alias for :func:`Row`."""
    return Row(*children, **props)


def column(*children: Any, **props: Any) -> Node:
    """Alias for :func:`Column`."""
    return Column(*children, **props)
