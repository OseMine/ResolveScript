"""Widget specifications: the bridge between logical props and native ones.

Every framework widget is described by a :class:`WidgetSpec`. It records the
native element type, the logical-to-native prop mapping, the events the widget
raises, and which props are two-way bound inputs.

Keeping this in a table (rather than hand-written widget classes) is what makes
the framework mirror-friendly, JSON-serialisable and easy to extend: adding a
widget means adding one row of data, not a new renderer.

    spec = get_spec("text_field")
    spec.native_type          # 'LineEdit'
    spec.two_way_props()      # {'value': ('Text', 'TextChanged')}
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import ElementError
from .theme import Color, Font, Theme
from .theme import theme as _active_theme

__all__ = [
    "UNSET",
    "PropSpec",
    "WidgetSpec",
    "get_spec",
    "register_spec",
    "all_specs",
    "events_to_enable",
    "ALIGNMENTS",
    "ORIENTATIONS",
    "BULK",
    "EACH",
    "ROWS",
]

#: Sentinel for "this prop has no default", so ``None`` stays meaningful.
UNSET = object()


# Qt enum values, needed because Fusion's properties are genuine Qt properties.
ALIGNMENTS: dict[str, int] = {
    "left": 0x0001,
    "right": 0x0002,
    "center": 0x0084,
    "justify": 0x0003,
    "top": 0x0020,
    "bottom": 0x0040,
    "top_left": 0x0021,
    "top_right": 0x0022,
    "top_center": 0x0024,
    "bottom_left": 0x0041,
    "bottom_right": 0x0042,
    "bottom_center": 0x0084,
    "vcenter": 0x0080,
    "vcenter_left": 0x0081,
    "vcenter_right": 0x0082,
    "fill": 0x0000,
}

ORIENTATIONS: dict[str, int] = {"horizontal": 1, "vertical": 2}

SCROLL_POLICIES: dict[str, int] = {"as_needed": 0, "always_off": 1, "always_on": 2}

# Events that Qt only delivers when explicitly turned on via the ``Events``
# property. Without this a slider's value change can silently never fire.
_ENABLE_EVENTS = {
    "ValueChanged",
    "TextChanged",
    "TextEdited",
    "CurrentIndexChanged",
    "CurrentTextChanged",
    "StateChanged",
    "Toggled",
    "ItemClicked",
    "ItemActivated",
    "ItemDoubleClicked",
    "CurrentItemChanged",
    "CurrentChanged",
    "ColorChanged",
    "SliderReleased",
    "ReturnPressed",
    "EditingFinished",
}


# ---------------------------------------------------------------------------
# Transforms: logical value -> native property value
# ---------------------------------------------------------------------------


def _as_int(value: Any) -> int:
    return int(value)


def _as_float(value: Any) -> float:
    return float(value)


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_size(value: Any) -> list[int]:
    width, height = value
    return [int(width), int(height)]


def _as_geometry(value: Any) -> list[int]:
    x, y, width, height = value
    return [int(x), int(y), int(width), int(height)]


def _as_enum(table: Mapping[str, int]) -> Callable[[Any], int]:
    def transform(value: Any) -> int:
        if isinstance(value, int):
            return value
        try:
            return table[str(value).lower()]
        except KeyError:
            raise ElementError(
                f"expected one of {sorted(table)}, got {value!r}"
            ) from None

    return transform


def _as_color(value: Any) -> list[float]:
    if isinstance(value, Color):
        return value.to_fusion()
    if isinstance(value, (list, tuple)):
        channels = list(value) + [1.0] * (4 - len(value))
        return [float(c) for c in channels[:4]]
    return Color.from_hex(str(value)).to_fusion()


def _as_font(value: Any) -> dict[str, Any]:
    if isinstance(value, Font):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    raise ElementError(f"cannot use {value!r} as a font")


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, str):
        return [value]
    return list(value)


def _as_echo(value: Any) -> int:
    """LineEdit echo mode: mask the text when ``password`` is set.

    Fusion's reference does not list ``EchoMode``, but it is a standard
    QLineEdit property and the underlying widget is a QLineEdit.
    """
    if isinstance(value, str):
        return 2 if value.strip().lower() in ("1", "true", "yes", "password") else 0
    return 2 if value else 0


_TRANSFORMS: dict[str, Callable[[Any], Any]] = {
    "value": lambda v: v,
    "int": _as_int,
    "float": _as_float,
    "str": _as_str,
    "bool": _as_bool,
    "size": _as_size,
    "geometry": _as_geometry,
    "align": _as_enum(ALIGNMENTS),
    "orientation": _as_enum(ORIENTATIONS),
    "scroll": _as_enum(SCROLL_POLICIES),
    "color": _as_color,
    "font": _as_font,
    "list": _as_list,
    "echo": _as_echo,
}


#: How a ``via`` prop is delivered to its element.
BULK = "bulk"
#: One native call per item (``TabBar.AddTab``).
EACH = "each"
#: Tree rows, diffed item-by-item so the native items survive an update.
ROWS = "rows"


@dataclass(frozen=True)
class PropSpec:
    """One logical prop and how it reaches the native element.

    Props whose ``native`` name starts with ``__`` are renderer-internal (gap,
    padding, rows) and never reach the widget. Props with a ``via`` method are
    applied after construction, because some collections can only be filled
    through methods -- ``ComboBox.AddItems`` rather than a constructor property.
    """

    name: str
    native: str
    default: Any = UNSET
    kind: str = "value"
    two_way: bool = False
    event: str | None = None
    read: Callable[[Any], Any] | None = None
    via: str | None = None
    strategy: str = BULK
    remove: str | None = None

    @property
    def each(self) -> bool:
        """Whether the collection is applied one native call per item."""
        return self.strategy == EACH

    @property
    def internal(self) -> bool:
        """Whether this prop is handled by the renderer itself."""
        return self.native.startswith("__") or self.via is not None

    def to_native(self, value: Any) -> Any:
        try:
            transform = _TRANSFORMS[self.kind]
        except KeyError:  # pragma: no cover - guarded by construction
            raise ElementError(f"unknown prop kind {self.kind!r}") from None
        return transform(value)

    def from_native(self, value: Any) -> Any:
        """Read the native value back for a two-way binding."""
        if self.read is not None:
            return self.read(value)
        if self.kind == "int":
            return int(value)
        if self.kind == "float":
            return float(value)
        if self.kind == "bool":
            return bool(value)
        return value


@dataclass(frozen=True)
class WidgetSpec:
    """Everything the renderer needs to mount one widget kind."""

    kind: str
    native_type: str
    container: bool = False
    props: Mapping[str, PropSpec] = field(default_factory=dict)
    events: Mapping[str, str] = field(default_factory=dict)
    documented: bool = True
    #: Kinds rendered through the dispatcher rather than the element factory.
    root: bool = False
    #: Which prop supplies the stylesheet variant, if any.
    variant_prop: str | None = "variant"

    # -- lookups ---------------------------------------------------------
    def prop(self, name: str) -> PropSpec | None:
        return self.props.get(name)

    def two_way_props(self) -> dict[str, PropSpec]:
        return {n: p for n, p in self.props.items() if p.two_way}

    def two_way_for(self, name: str) -> PropSpec | None:
        found = self.props.get(name)
        return found if found is not None and found.two_way else None

    def events_to_enable(self, names: Iterable[str] = ()) -> dict[str, bool]:
        return {name: True for name in names if name in _ENABLE_EVENTS}

    def native_event(self, name: str) -> str | None:
        return self.events.get(name)

    def variant_of(self, props: Mapping[str, Any]) -> str | None:
        if not self.variant_prop:
            return None
        value = props.get(self.variant_prop)
        return str(value) if value is not None else None

    def stylesheet(self, props: Mapping[str, Any], active: Theme | None = None) -> str:
        chosen = active or _active_theme
        return chosen.stylesheet(self.kind, self.variant_of(props))

    def __repr__(self) -> str:
        return f"<WidgetSpec {self.kind!r} -> {self.native_type}>"


# ---------------------------------------------------------------------------
# Reusable prop groups
# ---------------------------------------------------------------------------

_COMMON: dict[str, PropSpec] = {
    "key_id": PropSpec("key_id", "ID", kind="str"),
    "visible": PropSpec("visible", "Visible", True, kind="bool"),
    "enabled": PropSpec("enabled", "Enabled", True, kind="bool"),
    "hidden": PropSpec("hidden", "Hidden", False, kind="bool"),
    "tooltip": PropSpec("tooltip", "ToolTip", kind="str"),
    "status_tip": PropSpec("status_tip", "StatusTip", kind="str"),
    "weight": PropSpec("weight", "Weight", kind="int"),
    "min_size": PropSpec("min_size", "MinimumSize", kind="size"),
    "max_size": PropSpec("max_size", "MaximumSize", kind="size"),
    "fixed_size": PropSpec("fixed_size", "FixedSize", kind="size"),
    "margin": PropSpec("margin", "Margin", kind="size"),
    "font": PropSpec("font", "Font", kind="font"),
    "background": PropSpec("background", "BackgroundColor", kind="color"),
    # Consumed by the renderer, never forwarded: ``theme`` cascades to the
    # whole subtree, ``variant`` selects a stylesheet preset.
    "theme": PropSpec("theme", "__theme", kind="value"),
    "variant": PropSpec("variant", "__variant", kind="str"),
}

_CONTAINER: dict[str, PropSpec] = {
    **_COMMON,
    "gap": PropSpec("gap", "__gap", 0, kind="int"),
    "padding": PropSpec("padding", "__padding", 0, kind="int"),
    "align": PropSpec("align", "Alignment", "fill", kind="align"),
}

_WINDOW_PROPS: dict[str, PropSpec] = {
    **_CONTAINER,
    "title": PropSpec("title", "WindowTitle", kind="str"),
    "geometry": PropSpec("geometry", "Geometry", kind="geometry"),
    "opacity": PropSpec("opacity", "WindowOpacity", kind="float"),
    "fixed_size": PropSpec("fixed_size", "FixedSize", kind="size"),
}


def _spec(kind: str, native_type: str, props: Mapping[str, PropSpec], **kwargs: Any) -> WidgetSpec:
    return WidgetSpec(kind=kind, native_type=native_type, props=dict(props), **kwargs)


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

_SPECS: dict[str, WidgetSpec] = {}


def register_spec(spec: WidgetSpec) -> WidgetSpec:
    """Register (or replace) a widget spec."""
    if not isinstance(spec, WidgetSpec):
        raise ElementError(f"expected a WidgetSpec, got {type(spec).__name__}")
    _SPECS[spec.kind] = spec
    return spec


def get_spec(kind: str) -> WidgetSpec:
    """Look up a spec, with a helpful error listing near-misses."""
    try:
        return _SPECS[kind]
    except KeyError:
        close = sorted(k for k in _SPECS if k.startswith(kind[:3]))
        hint = f"; did you mean {close}?" if close else ""
        raise ElementError(f"unknown widget kind {kind!r}{hint}") from None


def all_specs() -> Mapping[str, WidgetSpec]:
    """Every registered spec, keyed by kind."""
    return dict(_SPECS)


def events_to_enable(names: Iterable[str]) -> dict[str, bool]:
    """The ``Events`` table a set of event names requires.

    Qt only delivers value-change events (and several others) for elements that
    were created naming them, so the renderer passes this through to every
    widget that subscribes to one. ``Click`` and ``Close`` are on by default
    and are filtered out.
    """
    return {name: True for name in names if name in _ENABLE_EVENTS}


# -- roots -----------------------------------------------------------------

register_spec(
    _spec(
        "window",
        "Window",
        _WINDOW_PROPS,
        container=True,
        root=True,
        events={"on_close": "Close", "on_show": "Show", "on_hide": "Hide", "on_resize": "Resize"},
    )
)
register_spec(
    _spec(
        "dialog",
        "Dialog",
        _WINDOW_PROPS,
        container=True,
        root=True,
        events={"on_close": "Close"},
    )
)

# -- layout ----------------------------------------------------------------

register_spec(_spec("column", "VGroup", _CONTAINER, container=True))
register_spec(_spec("row", "HGroup", _CONTAINER, container=True))
register_spec(
    _spec(
        "stack",
        "VGroup",
        {**_CONTAINER, "index": PropSpec("index", "__index", 0, kind="int")},
        container=True,
    )
)
register_spec(_spec("card", "VGroup", _CONTAINER, container=True))
register_spec(
    _spec(
        "scroll_area",
        "ScrollArea",
        {
            **_CONTAINER,
            "horizontal": PropSpec("horizontal", "HorizontalScrollBarPolicy", False, kind="scroll"),
            "vertical": PropSpec("vertical", "VerticalScrollBarPolicy", True, kind="scroll"),
        },
        container=True,
        documented=False,
    )
)
register_spec(
    _spec(
        "spacer",
        "VGroup",
        {
            **_COMMON,
            "horizontal": PropSpec("horizontal", "__horizontal", True, kind="bool"),
            "vertical": PropSpec("vertical", "__vertical", False, kind="bool"),
        },
    )
)
register_spec(
    _spec(
        "divider",
        "HLine",
        {**_COMMON, "orientation": PropSpec("orientation", "__orientation", "horizontal",
                                            kind="orientation")},
        documented=False,
    )
)
register_spec(_spec("group", "GroupBox", {**_CONTAINER, "title": PropSpec("title", "Title", kind="str")}, container=True, documented=False))

# -- text ------------------------------------------------------------------

register_spec(
    _spec(
        "label",
        "Label",
        {
            **_COMMON,
            "text": PropSpec("text", "Text", "", kind="str"),
            "align": PropSpec("align", "Alignment", "left", kind="align"),
            "word_wrap": PropSpec("word_wrap", "WordWrap", False, kind="bool"),
            "indent": PropSpec("indent", "Indent", kind="int"),
        },
        events={"on_click": "MousePress", "on_double_click": "MouseDoubleClick"},
    )
)

register_spec(
    _spec(
        "text_field",
        "LineEdit",
        {
            **_COMMON,
            "value": PropSpec("value", "Text", "", kind="str", two_way=True, event="TextChanged"),
            "placeholder": PropSpec("placeholder", "PlaceholderText", "", kind="str"),
            "max_length": PropSpec("max_length", "MaxLength", kind="int"),
            "read_only": PropSpec("read_only", "ReadOnly", False, kind="bool"),
            "clear_button": PropSpec("clear_button", "ClearButtonEnabled", False, kind="bool"),
            "password": PropSpec("password", "EchoMode", False, kind="echo"),
        },
        events={
            "on_click": "Clicked",
            "on_change": "TextChanged",
            "on_submit": "ReturnPressed",
            "on_focus": "FocusIn",
            "on_blur": "FocusOut",
        },
    )
)

register_spec(
    _spec(
        "text_area",
        "TextEdit",
        {
            **_COMMON,
            "value": PropSpec("value", "Text", "", kind="str", two_way=True, event="TextChanged"),
            "placeholder": PropSpec("placeholder", "PlaceholderText", "", kind="str"),
            "read_only": PropSpec("read_only", "ReadOnly", False, kind="bool"),
        },
        events={"on_change": "TextChanged", "on_focus": "FocusIn", "on_blur": "FocusOut"},
    )
)

# -- input -----------------------------------------------------------------

register_spec(
    _spec(
        "button",
        "Button",
        {
            **_COMMON,
            "text": PropSpec("text", "Text", "", kind="str"),
            "icon": PropSpec("icon", "Icon", kind="str"),
            "icon_size": PropSpec("icon_size", "IconSize", kind="size"),
            "checkable": PropSpec("checkable", "Checkable", False, kind="bool"),
            "pressed": PropSpec(
                "pressed", "Checked", False, kind="bool", two_way=True, event="Toggled"
            ),
            "flat": PropSpec("flat", "Flat", False, kind="bool"),
        },
        events={"on_click": "Clicked", "on_toggle": "Toggled"},
    )
)

register_spec(
    _spec(
        "check",
        "CheckBox",
        {
            **_COMMON,
            "text": PropSpec("text", "Text", "", kind="str"),
            "checked": PropSpec(
                "checked", "Checked", False, kind="bool", two_way=True, event="Toggled"
            ),
            "tri_state": PropSpec("tri_state", "Tristate", False, kind="bool"),
        },
        events={"on_change": "Toggled", "on_click": "Clicked"},
    )
)

register_spec(
    _spec(
        "switch",
        "CheckBox",
        {
            **_COMMON,
            "checked": PropSpec(
                "checked", "Checked", False, kind="bool", two_way=True, event="Toggled"
            ),
        },
        events={"on_change": "Toggled", "on_click": "Clicked"},
    )
)

register_spec(
    _spec(
        "radio",
        "CheckBox",
        {
            **_COMMON,
            "text": PropSpec("text", "Text", "", kind="str"),
            "checked": PropSpec(
                "checked", "Checked", False, kind="bool", two_way=True, event="Toggled"
            ),
        },
        events={"on_change": "Toggled", "on_click": "Clicked"},
    )
)

register_spec(
    _spec(
        "combo",
        "ComboBox",
        {
            **_COMMON,
            "items": PropSpec("items", "ItemText", kind="list", via="AddItems"),
            "value": PropSpec(
                "value", "CurrentIndex", 0, kind="int", two_way=True,
                event="CurrentIndexChanged",
            ),
            "editable": PropSpec("editable", "Editable", False, kind="bool"),
        },
        events={"on_change": "CurrentIndexChanged", "on_submit": "EditingFinished"},
    )
)

register_spec(
    _spec(
        "number",
        "SpinBox",
        {
            **_COMMON,
            "value": PropSpec("value", "Value", 0, kind="int", two_way=True, event="ValueChanged"),
            "minimum": PropSpec("minimum", "Minimum", kind="int"),
            "maximum": PropSpec("maximum", "Maximum", kind="int"),
            "step": PropSpec("step", "SingleStep", 1, kind="int"),
            "suffix": PropSpec("suffix", "Suffix", kind="str"),
            "prefix": PropSpec("prefix", "Prefix", kind="str"),
        },
        events={"on_change": "ValueChanged", "on_submit": "EditingFinished"},
    )
)

register_spec(
    _spec(
        "slider",
        "Slider",
        {
            **_COMMON,
            "value": PropSpec("value", "Value", 0, kind="int", two_way=True, event="ValueChanged"),
            "minimum": PropSpec("minimum", "Minimum", 0, kind="int"),
            "maximum": PropSpec("maximum", "Maximum", 100, kind="int"),
            "step": PropSpec("step", "SingleStep", 1, kind="int"),
            "orientation": PropSpec("orientation", "Orientation", "horizontal", kind="orientation"),
        },
        events={"on_change": "ValueChanged", "on_release": "SliderReleased"},
    )
)

register_spec(
    _spec(
        "color",
        "ColorPicker",
        {
            **_COMMON,
            "value": PropSpec("value", "Color", kind="color", two_way=True, event="ColorChanged"),
            "alpha": PropSpec("alpha", "DoAlpha", True, kind="bool"),
        },
        events={"on_change": "ColorChanged"},
    )
)

register_spec(
    _spec(
        "progress",
        "ProgressBar",
        {
            **_COMMON,
            "value": PropSpec("value", "Value", 0, kind="int", two_way=True, event="ValueChanged"),
            "minimum": PropSpec("minimum", "Minimum", 0, kind="int"),
            "maximum": PropSpec("maximum", "Maximum", 100, kind="int"),
            "text": PropSpec("text", "Format", kind="str"),
        },
        events={"on_change": "ValueChanged"},
        documented=False,
    )
)

# -- collections -----------------------------------------------------------

register_spec(
    _spec(
        "tabs",
        "TabBar",
        {
            **_COMMON,
            "items": PropSpec(
                "items", "TabText", kind="list", via="AddTab", strategy=EACH, remove="RemoveTab"
            ),
            "tooltips": PropSpec("tooltips", "TabToolTip", kind="list"),
            "value": PropSpec(
                "value", "CurrentIndex", 0, kind="int", two_way=True, event="CurrentChanged"
            ),
            "closable": PropSpec("closable", "TabsClosable", False, kind="bool"),
            "expanding": PropSpec("expanding", "Expanding", True, kind="bool"),
        },
        events={"on_change": "CurrentChanged", "on_close": "CloseRequested"},
    )
)

register_spec(
    _spec(
        "tree",
        "Tree",
        {
            **_COMMON,
            "columns": PropSpec("columns", "HeaderLabels", kind="list", via="SetHeaderLabels"),
            "rows": PropSpec("rows", "__rows", kind="list", via="AddTopLevelItem", strategy=ROWS),
            "value": PropSpec("value", "CurrentItem", kind="value"),
            "header_hidden": PropSpec("header_hidden", "HeaderHidden", False, kind="bool"),
            "sorting": PropSpec("sorting", "SortingEnabled", True, kind="bool"),
            "alternating": PropSpec("alternating", "AlternatingRowColors", True, kind="bool"),
        },
        events={
            "on_select": "CurrentItemChanged",
            "on_click": "ItemClicked",
            "on_double_click": "ItemDoubleClicked",
            "on_activate": "ItemActivated",
        },
    )
)

register_spec(
    _spec(
        "list",
        "Tree",
        {
            **_COMMON,
            "columns": PropSpec("columns", "HeaderLabels", kind="list", via="SetHeaderLabels"),
            "rows": PropSpec("rows", "__rows", kind="list", via="AddTopLevelItem", strategy=ROWS),
            "value": PropSpec("value", "CurrentItem", kind="value"),
            "header_hidden": PropSpec("header_hidden", "HeaderHidden", True, kind="bool"),
            "sorting": PropSpec("sorting", "SortingEnabled", True, kind="bool"),
        },
        events={
            "on_select": "CurrentItemChanged",
            "on_click": "ItemClicked",
            "on_double_click": "ItemDoubleClicked",
            "on_activate": "ItemActivated",
        },
    )
)

register_spec(
    _spec("icon", "Icon", {**_COMMON, "file": PropSpec("file", "File", kind="str")})
)
