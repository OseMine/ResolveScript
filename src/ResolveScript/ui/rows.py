"""Deriving table rows from ordinary objects.

A Resolve tool usually exists to show a list of things Resolve handed it —
media pool items, timeline clips, render jobs — and asking the author to write
a dict comprehension for every column is a tax paid on every screen. This
module removes it::

    Tree(
        ["Clip", "Type"],
        rows(items, "GetName", call("GetClipProperty", "Type")),
    )

:func:`~ResolveScript.ui.dsl.Tree` and :func:`~ResolveScript.ui.dsl.List` still
accept hand-written row dicts; this is the shorthand for the common case, and
it produces exactly the same dictionaries, so nothing else in the framework
changes behaviour.

Naming a column
---------------

Each column is either:

a callable
    Called with the item. Use this for anything computed.

a string
    Read as an attribute, **and called if it turns out to be a method**. Every
    Resolve API object exposes ``GetSomething()`` and nothing else, so
    ``"GetName"`` is the natural spelling; a plain dataclass attribute works
    the same way. This rule is the whole ergonomic trick — it means the common
    case needs no ceremony.

``call("GetClipProperty", "Type")``
    For a method that needs arguments. :func:`call` is the explicit spelling
    of the same thing, and raises a clear error when the method is absent
    rather than an ``AttributeError`` from inside a comprehension.

``maybe("GetClipProperty", "Type", default="folder")``
    For when it may legitimately be missing. A media pool folder and a clip
    are *different types* — the folder has ``GetClipList``, the clip has
    ``GetClipProperty`` — so any column or ``children`` accessor that spans
    both levels has to tolerate absence. :func:`maybe` is how you say that
    without a ``getattr`` dance in every accessor.

A missing attribute is reported against the item's type and the name asked
for, because "AttributeError: 'FakeMediaPoolItem' object has no attribute
'GetNmae'" at row 400 is the kind of message that costs an hour.

Hierarchies
-----------

Media pool folders contain clips, which contain sub-folders, to any depth.
``children`` takes an accessor returning that item's **child items** — not
rows — and the same columns are applied all the way down, so a real media pool
tree is one call::

    Tree(["Name"], rows([root], "GetName", children=lambda f: f.GetClipList()))

Depth follows your data: if the accessor returns ``None`` or an empty
sequence, that row is a leaf. A caller that needs *different* columns on
children (a media pool bin with a clip-count column only on folders) can
still return built rows instead of items, and they are used verbatim.

Since folders and clips are different types, both the shared columns and the
``children`` accessor need :func:`maybe` to cross that boundary::

    def members(folder):
        return list(folder.GetClipList()) + list(folder.GetSubFolderList())

    Tree(
        ["Name", "Type"],
        rows(
            [root],
            "GetName",
            maybe("GetClipProperty", "Type", default="folder"),
            children=maybe("GetClipList", default=()),
        ),
    )

Which is the whole media pool browser, for every depth, in one call.

Missing values
--------------

Resolve says "no such property" with ``None``, and a cell showing the literal
text ``None`` reads as a bug in the tool rather than as absent data. ``None``
becomes ``""`` here; pass ``placeholder="-"`` if that is your house style.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, NamedTuple, Union

from .errors import ElementError

__all__ = ["Accessor", "call", "maybe", "rows"]

#: How a column, id or icon name is turned into a value.
#:
#: ``Union`` rather than ``str | Callable``: this is a value, not an
#: annotation, so ``from __future__ import annotations`` does not defer it and
#: 3.9 would raise on evaluation.
Accessor = Union[str, Callable[[Any], Any]]


def call(name: str, *args: Any, **kwargs: Any) -> Callable[[Any], Any]:
    """An accessor for a method that needs arguments.

    ``call("GetClipProperty", "Type")`` reads ``item.GetClipProperty("Type")``.

    Strict: a missing method is an error, because on one type of item it being
    missing is a typo. Reach for :func:`maybe` when absence is legitimate.
    """

    def accessor(item: Any) -> Any:
        return _invoke(item, name, args, kwargs)

    accessor.__name__ = f"call({name})"
    return accessor


def maybe(
    name: str,
    *args: Any,
    default: Any = None,
    **kwargs: Any,
) -> Callable[[Any], Any]:
    """An accessor for a method that may legitimately not exist.

    ``maybe("GetClipProperty", "Type", default="folder")`` reads
    ``item.GetClipProperty("Type")`` when the item has that method, and yields
    ``"folder"`` when it does not. With no ``args``/``kwargs`` the attribute is
    read instead of called, so ``maybe("GetClipList", default=())`` works for
    both a plain attribute and a no-argument method.
    """

    def accessor(item: Any) -> Any:
        found = getattr(item, name, None)
        if not callable(found):
            return default if found is None else found
        return found(*args, **kwargs)

    accessor.__name__ = f"maybe({name})"
    return accessor


def rows(
    items: Iterable[Any],
    *columns: Accessor,
    id: Accessor | None = None,
    tooltip: Accessor | None = None,
    icon: Accessor | None = None,
    selected: Accessor | None = None,
    children: Accessor | None = None,
    placeholder: str = "",
) -> list[dict[str, Any]]:
    """Build the row dictionaries :func:`Tree` and :func:`List` take.

    :param items: the objects to show, in display order.
    :param columns: one accessor per column; see the module docstring.
    :param id: a stable per-row identifier. Worth setting — it is what lets
        the renderer tell a renamed row from a replaced one.
    :param tooltip: text for the row's tooltip cells.
    :param icon: icon path per cell.
    :param selected: truthy marks the row selected.
    :param children: an accessor returning that item's child **items**; the
        same columns are applied recursively, to any depth. Return already
        built row dicts instead to vary the columns per level.
    :param placeholder: shown where an accessor returned ``None``. Resolve
        signals "no such property" with ``None`` rather than an empty string
        (``GetClipProperty`` on a still image, ``GetStartFrame`` on a compound
        clip), and ``str(None)`` in a table cell reads as a bug in your tool
        rather than as missing data. Pass ``"-"`` if that is your house style.
    """
    if not columns:
        raise ElementError("rows() needs at least one column accessor")
    return _build(items, _Options(columns, id, tooltip, icon, selected, children, placeholder))


class _Options(NamedTuple):
    """The accessors and settings shared by every row at every depth."""

    columns: tuple[Accessor, ...]
    id: Accessor | None
    tooltip: Accessor | None
    icon: Accessor | None
    selected: Accessor | None
    children: Accessor | None
    placeholder: str


def _build(items: Iterable[Any], options: _Options) -> list[dict[str, Any]]:
    return [_row(item, options) for item in items]


def _row(item: Any, options: _Options) -> dict[str, Any]:
    row: dict[str, Any] = {
        "cells": [_cell(item, column, options.placeholder) for column in options.columns],
        "children": [],
    }
    if options.id is not None:
        row["id"] = str(_read(item, options.id))
    if options.tooltip is not None:
        row["tooltip"] = _read(item, options.tooltip)
    if options.icon is not None:
        row["icon"] = _read(item, options.icon)
    if options.selected is not None and _read(item, options.selected):
        row["selected"] = True
    if options.children is not None:
        row["children"] = _children(item, options)
    return row


def _children(item: Any, options: _Options) -> list[dict[str, Any]]:
    """Recurse with the same columns, unless the caller handed back ready rows.

    Both are supported because a media pool bin wants the same column on its
    clips and sub-bins, while a mixed tree sometimes wants a count column on
    the folder level only. Detecting a mapping is enough to tell them apart —
    an item that happens to *be* a mapping is a rare enough shape, and the
    caller can always disambiguate by building the rows explicitly.
    """
    kids = _read(item, options.children)
    if not kids:
        return []
    if all(isinstance(kid, Mapping) for kid in kids):
        return list(kids)
    return _build(kids, options)


def _cell(item: Any, accessor: Accessor, placeholder: str) -> Any:
    """Read one cell, substituting ``placeholder`` for a missing value."""
    value = _read(item, accessor)
    return placeholder if value is None else value


def _read(item: Any, accessor: Accessor) -> Any:
    """Resolve one accessor against one item."""
    if callable(accessor):
        return accessor(item)
    if not isinstance(accessor, str):
        raise ElementError(
            f"column accessor must be a string or a callable, got {accessor!r}"
        )
    return _attribute(item, accessor)


def _attribute(item: Any, name: str) -> Any:
    """An attribute, called if it is a method. The rule that makes this readable."""
    try:
        value = getattr(item, name)
    except AttributeError as exc:
        raise ElementError(
            f"cannot read {name!r} from {_typename(item)}"
        ) from exc
    if callable(value):
        try:
            return value()
        except TypeError as exc:
            raise ElementError(
                f"{_typename(item)}.{name} needs arguments — "
                f"use call({name!r}, ...), or give it a lambda"
            ) from exc
    return value


def _invoke(item: Any, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    method = getattr(item, name, None)
    if not callable(method):
        raise ElementError(f"{_typename(item)} has no callable {name!r}")
    return method(*args, **kwargs)


def _typename(item: Any) -> str:
    return type(item).__name__
