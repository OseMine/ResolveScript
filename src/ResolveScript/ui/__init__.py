"""ResolveScript UI — a declarative framework for DaVinci Resolve tools.

Three ways to author the same screen, all interchangeable because they produce
the same node tree:

**Functions** — the shortest path, and what most tools use::

    from ResolveScript.ui import Window, Column, Row, Button, TextField, run, Value

    name = Value("Sequence 01")

    run(Window("Render", children=[
        Column(
            Row(TextField(value=name), Button("Apply"), gap="sm"),
            gap="md", padding="md",
        )
    ]))

**Dictionaries / JSON** — a screen described as data, for templates and tools
that generate UIs::

    from ResolveScript.ui import from_json

    run(from_json(document))

**Classes** — for anything with real state::

    from ResolveScript.ui import Component, Card, Value, widget

    @widget("clip-panel")
    class ClipPanel(Component):
        def __init__(self, clip):
            super().__init__(clip=clip)
            self.locked = Value(False)

        def build(self):
            return Card(Heading(self.clip.get()), Check("Lock", self.locked))

**Native components** — anything the framework has not wrapped is still one
line away, and mixes freely with the above::

    from ResolveScript.ui import native, Row

    Row(native(lambda ui: ui.SpinBox({"ID": "custom", "Value": 3})))

How it works
------------

A UI is a tree of :class:`~ResolveScript.ui.node.Node` objects holding *logical*
props (``text``, ``checked``, ``variant``). A
:class:`~ResolveScript.ui.spec.WidgetSpec` maps those onto Fusion's real
properties, and a :class:`~ResolveScript.ui.render.Renderer` mounts the tree and
then patches *only* what changes — a bound
:class:`~ResolveScript.ui.state.Value` writes a single native property, so focus,
scroll position and selection all survive an update.

Because the target is specified rather than hard-coded, the same tree renders to
real Resolve (:class:`~ResolveScript.ui.backends.FusionBackend`), to a headless
mirror for tests (:class:`~ResolveScript.ui.backends.MockBackend`), and back out
as JSON.
"""

from __future__ import annotations

from . import backends
from .app import App, mount, run
from .backends import Backend, FusionBackend, MockBackend, get_backend
from .components import Component, Widget, all_components, get_component, register_component, widget
from .dsl import (
    Button,
    Card,
    Check,
    ColorPicker,
    Column,
    Combo,
    DangerButton,
    Dialog,
    Divider,
    Group,
    Heading,
    Icon,
    IconButton,
    Label,
    List,
    Muted,
    Number,
    PasswordField,
    PrimaryButton,
    Progress,
    Radio,
    Row,
    ScrollArea,
    Slider,
    Spacer,
    Stack,
    Switch,
    Tabs,
    TextArea,
    TextField,
    Title,
    Tree,
    Window,
    column,
    row,
)
from .errors import (
    BackendError,
    BackendUnavailable,
    BindingError,
    ElementError,
    SchemaError,
    UIError,
)
from .events import Event
from .jsonio import from_dict, from_json, to_dict, to_json
from .node import Node, Raw, TwoWay, native, node, raw_element, walk
from .render import AppRoot, Bound, Renderer
from .rows import Accessor, call, maybe, rows
from .spec import PropSpec, WidgetSpec, all_specs, get_spec, register_spec
from .state import (
    Computed,
    Subscription,
    Value,
    batch,
    batched,
    computed,
    is_reactive,
    value,
    watch,
)
from .theme import Color, Font, Theme, dark_theme, light_theme, theme, use_theme

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # -- roots ------------------------------------------------------------
    "Window",
    "Dialog",
    # -- layout -----------------------------------------------------------
    "Column",
    "Row",
    "Stack",
    "Card",
    "Group",
    "ScrollArea",
    "Spacer",
    "Divider",
    "column",
    "row",
    # -- text -------------------------------------------------------------
    "Label",
    "Heading",
    "Title",
    "Muted",
    # -- actions ----------------------------------------------------------
    "Button",
    "IconButton",
    "PrimaryButton",
    "DangerButton",
    # -- inputs -----------------------------------------------------------
    "TextField",
    "TextArea",
    "Number",
    "PasswordField",
    "Slider",
    "Check",
    "Switch",
    "Radio",
    "Combo",
    "ColorPicker",
    "Progress",
    # -- collections ------------------------------------------------------
    "Tabs",
    "Tree",
    # -- data -------------------------------------------------------------
    "Accessor",
    "rows",
    "call",
    "maybe",
    "List",
    "Icon",
    # -- composition ------------------------------------------------------
    "Component",
    "Widget",
    "widget",
    "register_component",
    "get_component",
    "all_components",
    "Node",
    "Raw",
    "TwoWay",
    "node",
    "native",
    "raw_element",
    "walk",
    # -- state ------------------------------------------------------------
    "Value",
    "Computed",
    "Subscription",
    "batch",
    "batched",
    "value",
    "computed",
    "watch",
    "is_reactive",
    # -- theming ----------------------------------------------------------
    "Theme",
    "Color",
    "Font",
    "theme",
    "dark_theme",
    "light_theme",
    "use_theme",
    # -- serialisation ----------------------------------------------------
    "to_dict",
    "from_dict",
    "to_json",
    "from_json",
    # -- runtime ----------------------------------------------------------
    "App",
    "run",
    "mount",
    "Renderer",
    "Bound",
    "AppRoot",
    "Event",
    "backends",
    "Backend",
    "FusionBackend",
    "MockBackend",
    "get_backend",
    # -- introspection ----------------------------------------------------
    "WidgetSpec",
    "PropSpec",
    "get_spec",
    "register_spec",
    "all_specs",
    # -- errors -----------------------------------------------------------
    "UIError",
    "ElementError",
    "BackendError",
    "BackendUnavailable",
    "BindingError",
    "SchemaError",
]
