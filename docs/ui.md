# ResolveScript UI

A declarative UI framework for DaVinci Resolve tools, shipped as
`ResolveScript.ui`.

It gives you two things at once:

- **Native access.** Every widget is a thin, typed wrapper over a real Resolve
  `UIManager` element. Nothing is emulated or reimplemented — when the framework
  sets `Button.Text`, Qt sets `Button.Text`.
- **Composability.** Screens are described as plain Python functions returning
  nodes, and are *retained*: updating state patches individual native properties
  instead of rebuilding the tree, so focus, scroll position, text selection and
  tree expansion all survive a change.

Because the backend is chosen at mount time, the exact same tree renders to real
Resolve, to a headless in-memory mirror for tests, or back out as JSON.

---

## Contents

- [Install and import](#install-and-import)
- [60-second example](#60-second-example)
- [The three authoring modes](#the-three-authoring-modes)
- [Widgets](#widgets)
- [Layout](#layout)
- [State and reactivity](#state-and-reactivity)
- [Building tables from data](#building-tables-from-data)
- [Two-way binding and `TwoWay`](#two-way-binding-and-twoway)
- [Events](#events)
- [Keys, identity and reconciliation](#keys-identity-and-reconciliation)
- [Components](#components)
- [Native escape hatches](#native-escape-hatches)
- [Theming](#theming)
- [Dicts and JSON](#dicts-and-json)
- [Testing headlessly](#testing-headlessly)
- [Runtime control](#runtime-control)
- [Errors](#errors)
- [Extending: custom widget specs](#extending-custom-widget-specs)
- [How it fits together](#how-it-fits-together)

---

## Install and import

The UI framework ships inside the main package, so nothing extra to install:

```python
from ResolveScript.ui import (
    Window, Column, Row, Button, TextField, Tree, Tabs,
    Value, run, mount, MockBackend,
)
```

`ResolveScript.ui` runs on Resolve's bundled Python (3.12) and on any CPython
3.9+ for the headless/testing paths.

---

## 60-second example

```python
from ResolveScript.ui import (
    Window, Column, Row, Divider, Button, TextField, Check, Tree, run, Value,
)

sequence = Value("Sequence 01")
enabled  = Value(True)

run(Window("Batch Renderer", children=[
    Column(
        Row(TextField(value=sequence, placeholder="Sequence name"),
            Button("Render", variant="primary", on_click=start), gap="sm"),
        Check("Include adjustments", enabled),
        Divider(),
        Tree(["Clip", "Duration"],
             [{"cells": ["A001", "00:00:10:00"]},
              {"cells": ["B002", "00:00:04:12"]}]),
        gap="md",
        padding="md",
    )
]))
```

Inside Resolve this opens a real window. Swap `run` for `mount` with a
`MockBackend()` and the same tree runs in a test with no Resolve installed.

---

## The three authoring modes

All three produce the same node tree, so they mix freely inside one screen.

### 1. Functions (primary)

```python
from ResolveScript.ui import Card, Heading, Muted, TextField, Value

name = Value("A001")

screen = Card(
    Heading("Clip"),
    Muted("Source media"),
    TextField(value=name),
    gap="md",
)
```

### 2. Dicts and JSON

A screen described as data, for tools that generate UIs or ship layouts as
templates:

```python
from ResolveScript.ui import from_dict, run

run(from_dict({
    "kind": "window",
    "props": {"title": "Settings"},
    "children": [
        {"kind": "column", "props": {"gap": "md", "padding": "md"}, "children": [
            {"kind": "label", "props": {"text": "Output", "variant": "heading"}},
            {"kind": "combo", "props": {"items": ["ProRes", "DNxHR"], "value": 0}},
        ]},
    ],
}))
```

### 3. Classes

For anything with real state. A `Component` implements `build()`; props passed to
the constructor land on `self.props`.

```python
from ResolveScript.ui import Component, Card, Heading, Check, Value, widget

@widget("clip-panel", clip="A001")
class ClipPanel(Component):
    def __init__(self, **props):
        super().__init__(**props)
        self.locked = Value(False)

    def build(self):
        return Card(Heading(self.props["clip"]), Check("Lock", self.locked))
```

`@widget` registers the class under a name so dict/JSON documents can refer to
it. `App.refresh()` rebuilds registered components, so a component whose `build()`
reads `self.locked.get()` re-renders in place when that value changes.

---

## Widgets

Every widget takes logical props (`text`, `checked`, `variant`) that a spec maps
onto real Fusion properties. The table lists the DSL function, the widget kind
(what goes in a dict/JSON document), and the native element it creates.

| Function | Kind | Native | Notes |
| --- | --- | --- | --- |
| `Window(title, ...)` | `window` | `Window` | root; `geometry=`, `min_size=` |
| `Dialog(title, ...)` | `dialog` | `Dialog` | root |
| `Label(text)` | `label` | `Label` | `variant=`, `align=`, `word_wrap=` |
| `Heading` / `Title` / `Muted` | `label` | `Label` | preset variants |
| `Button(text)` | `button` | `Button` | `variant=` `default\|primary\|danger\|success\|ghost` |
| `IconButton(icon)` | `button` | `Button` | icon-only |
| `PrimaryButton` / `DangerButton` | `button` | `Button` | variant shorthands |
| `TextField(value)` | `text_field` | `LineEdit` | `placeholder=`, `read_only=`, `max_length=`, `clear_button=` |
| `PasswordField(value)` | `text_field` | `LineEdit` | a `TextField` with `password=True` |
| `TextArea(value)` | `text_area` | `TextEdit` | |
| `Number(value)` | `number` | `SpinBox` | `minimum=`, `maximum=`, `step=`, `prefix=`, `suffix=` |
| `Slider(value)` | `slider` | `Slider` | `orientation=` |
| `Check(text, checked)` | `check` | `CheckBox` | |
| `Switch(checked)` | `switch` | `CheckBox` | |
| `Radio(text, checked)` | `radio` | `CheckBox` | |
| `Combo(items, value)` | `combo` | `ComboBox` | |
| `ColorPicker(value)` | `color` | `ColorPicker` | `alpha=` |
| `Progress(value)` | `progress` | `ProgressBar` | |
| `Tabs(items, *pages)` | `tabs` | `TabBar` | tab bar + content stack |
| `Tree(columns, rows)` | `tree` | `Tree` | |
| `List(rows)` | `list` | `Tree` | single column |
| `Icon(file)` | `icon` | `Icon` | |

`PasswordField` is a `TextField` with `password=True`, for tools that need a
masked line edit (API keys, connection strings).

### Props common to every widget

| Prop | Native | Meaning |
| --- | --- | --- |
| `key_id` | `ID` | names the native element, making it event-addressable |
| `visible` / `hidden` | `Visible` / `Hidden` | |
| `enabled` | `Enabled` | |
| `tooltip` / `status_tip` | `ToolTip` / `StatusTip` | |
| `weight` | `Weight` | stretch factor in a container |
| `min_size` / `max_size` / `fixed_size` | `MinimumSize` / … | |
| `margin` | `Margin` | |
| `font` | `Font` | a `Font`, or a token like `"lg"` |
| `background` | `BackgroundColor` | a `Color`, or a token like `"surface_alt"` |
| `theme` | — | overrides the theme for this subtree |

Unknown props are rejected at mount time with a message listing what the widget
does accept, so typos surface immediately rather than silently doing nothing.

---

## Layout

`Column` and `Row` are `VGroup`/`HGroup`. Their `gap=` takes a spacing token or
raw pixels, and is realised as real `VGap`/`HGap` elements:

```python
Column(Label("A"), Label("B"), gap="md")     # 12px
Row(Button("Go"), Button("Stop"), gap="xs")  # 4px
```

Tokens: `xs=4`, `sm=8`, `md=12`, `lg=16`, `xl=24`, `xxl=32`, `none=0`. A raw
`int` passes straight through.

Other containers:

- **`Card(*children, gap="md")`** — a bordered surface.
- **`Group(title, ...)`** — a `GroupBox`.
- **`ScrollArea(*children)`** — with `horizontal=` / `vertical=`.
- **`Stack(*children, index=0)`** — mounts every child, shows one. `index` may
  be a `Value`; this is what makes a tab bar and its content share a single
  source of truth.
- **`Spacer()`**, **`Divider()`** — separators.

---

## State and reactivity

`Value` is an observable cell. Pass one anywhere a prop is expected and the
renderer subscribes to it:

```python
from ResolveScript.ui import Value, Check, Label, Column, Window, mount, MockBackend

name = Value("A001")
locked = Value(False)

mount(Window("t", Column(
    Check("Lock", locked),
    Label(name),          # text re-reads whenever name changes
)))
```

Setting a value notifies only its subscribers, so only the affected native
properties are written:

```python
name.set("A002")   # writes Text on that one Label
name.update(lambda cur: cur + "_v2")
```

`Computed` derives from other sources and recomputes only when a dependency
actually changed:

```python
from ResolveScript.ui import Computed

upper = Computed(lambda: name.get().upper(), name="upper")
```

Other pieces:

- **`watch(source, fn, immediate=False)`** — run arbitrary code on change. Returns
  a `Subscription` that is also a context manager.
- **`batch()`** (alias `batched()`) — collapse many writes into one notification
  pass, so ten `set()` calls notify subscribers once.
- **`Value.get()` / `.set()` / `.update()` / `.version()`** — read, write, and a
  change counter useful for skipping redundant work.

---

## Building tables from data

`Tree` and `List` take rows. `rows()` derives them from ordinary objects, which is
what you want for the usual Resolve screen — a list of things Resolve gave you.

A column is a **string** naming an attribute (called for you if it turns out to be
a method, so `"GetName"` is the natural spelling) or a **callable**:

```python
from ResolveScript.ui import Tree, List, rows, call, maybe

clips = list(media_pool.GetRootFolder().GetClipList())

Tree(["Clip", "Type"], rows(clips, "GetName", call("GetClipProperty", "Type")))
List(rows(clips, "GetName"))
```

`call("GetClipProperty", "Type")` is for a method that needs arguments. It is
strict: a missing method raises, because on one kind of item that means you
misspelled it.

Options, all accessors, applied per row:

| Option | Effect |
| --- | --- |
| `id` | stable identifier — lets the renderer tell a renamed row from a replaced one |
| `selected` | truthy marks the row selected |
| `tooltip` / `icon` | row-level tooltip and icon |
| `placeholder` | shown where an accessor returned `None` (default `""`) |
| `children` | that item's child **items**; the same columns recurse |

Resolve says "no such property" with `None`, and a cell showing the literal text
`None` reads as a bug in your tool rather than as absent data, so `None` becomes
`placeholder` instead.

### Hierarchies

`children` recurses with the same columns, so a media pool browser is one call:

```python
screen = Tree(
    ["Name", "Type"],
    rows(
        [root],
        "GetName",
        maybe("GetClipProperty", "Type", default="folder"),
        children=maybe("GetClipList", default=()),
    ),
)
```

`maybe("name", ..., default=...)` is the forgiving counterpart of `call`: it reads
the attribute, calls it if it is a method, and yields `default` when it is absent.
It exists because a `MediaPoolFolder` and a `MediaPoolItem` are unrelated types —
the folder has `GetClipList`, the clip has `GetClipProperty` — so any column or
`children` accessor spanning both levels has to tolerate absence. It forgives a
missing *method* only; a method that ran and returned `None` is a different thing,
and `placeholder` applies.

Return already-built row dicts from `children` instead of items when a level needs
different columns. They are used verbatim.

Errors name the item's type and the attribute asked for
(`cannot read 'GetNmae' from Clip`) rather than surfacing an `AttributeError` from
inside a comprehension at row 400.

---

## Two-way binding and `TwoWay`

If a spec marks a prop `two_way`, a plain `Value` bound to it is read *and*
written: type into the field and the value updates, no handler required.

```python
count = Value(0)
mount(Window("t", Number(value=count, minimum=0, maximum=100)))
```

`TwoWay` gives you that behaviour with a transform, which is what you need when
the stored representation differs from the native one. `read` goes
stored → native, `write` goes native → stored:

```python
from ResolveScript.ui import TwoWay, Value

# A checkbox whose Value stores "yes"/"no" but a native Checked bool.
flag = Value("no")
Check("Enable", TwoWay(flag, read=lambda s: s == "yes", write=lambda b: "yes" if b else "no"))
```

```python
# A text field that stores a trimmed string.
raw = Value("  padded  ")
TextField(value=TwoWay(raw, read=lambda s: s, write=lambda t: t.strip()))
```

`TwoWay` needs a settable source. Wrapping a read-only `Computed` without a
`write=` raises `BindingError` when the node is built, rather than failing
silently at click time.

---

## Events

Handlers are named `on_<event>`. They receive an `Event` that offers both typed
attributes and raw mapping access, so you rarely need to know which native field
carries the payload:

```python
from ResolveScript.ui import Event

def on_change(event: Event) -> None:
    event.type      # "TextChanged"
    event.target    # the native element
    event.text      # payload for text events
    event.value     # numeric payload (ValueChanged, CurrentIndexChanged, ...)
    event.checked   # boolean payload (Toggled)
    event.index     # selection index
    event.item      # selected tree item
    event.modifiers # ["Shift", "Ctrl", ...]
    event["Text"]   # the raw native field, when you need something specific
```

| Widget | Handlers |
| --- | --- |
| `Button`, `IconButton` | `on_click`, `on_toggle` |
| `TextField` | `on_click`, `on_change`, `on_submit`, `on_focus`, `on_blur` |
| `TextArea` | `on_change`, `on_focus`, `on_blur` |
| `Number`, `Slider`, `Progress` | `on_change`; `on_submit` / `on_release` |
| `Check`, `Switch`, `Radio`, `Combo`, `ColorPicker` | `on_change` |
| `Label` | `on_click`, `on_double_click` |
| `Tree`, `List` | `on_select`, `on_click`, `on_double_click`, `on_activate` |
| `Tabs` | `on_change`, `on_close` |
| `Window`, `Dialog` | `on_close`, `on_show`, `on_hide`, `on_resize` |

Only the events a handler actually needs are enabled on the native element, so
the framework does not turn on every signal under the sun.

---

## Keys, identity and reconciliation

This is the part that makes updates feel native.

Each node gets a key, and each key maps to exactly one live native element. When
the tree is re-rendered, the renderer walks the new tree and, for each key it has
seen before, **patches the existing element** rather than tearing it down and
building a new one. Focus, caret position, scroll offset, selection and tree
expansion therefore survive updates that do not logically change them.

Keys are assigned automatically and are stable across re-authoring. Override
them in two situations:

- **Generating lists**, where two siblings would otherwise collide — use
  `key=` or `Node(...).keyed(...)`:

  ```python
  Column(*(Button(row.name, on_click=make_handler(row)) for row in rows))
  Column(*(ui.node("button", {"text": row.name}).keyed(row.id) for row in rows))
  ```

- **Replacing a node's identity** — pass `key="slot"` to the replacement so the
  renderer knows to patch that slot in place.

`key_id=` is separate and more specific: it names the *native* element (the
Fusion `ID`), which is what events are routed by, and it is adopted as the node
key when no explicit key is given:

```python
Button("Render", key_id="render-btn")   # native ID "render-btn", findable by that id
```

`App.find(key)` and `App.require(key)` accept either a key or a `key_id`.

Lists like `Tree(rows=...)` are diffed rather than rebuilt, so an in-place update
(a renamed clip, a new duration) updates just that cell:

```python
rows = Value([{"cells": ["A001", "00:00:10:00"]}])
mount(Window("t", children=[Tree(["Clip", "Duration"], rows, key_id="clips")]),
      backend=backend)

rows.set([{"cells": ["A001", "00:00:12:00"]}])   # second cell only
```

---

## Components

`Component` is the base class for reusable UI with state. `@widget` registers it
by name so JSON documents can use it.

```python
from ResolveScript.ui import Component, Card, Heading, Muted, Value, widget

@widget("status-panel")
class StatusPanel(Component):
    def __init__(self, title="Status", **props):
        super().__init__(title=title, **props)
        self.message = Value("Idle")

    def build(self):
        return Card(Heading(self.props["title"]), Muted(self.message))
```

- `self.props` holds the declared props plus any extra keyword arguments.
- `self.<Value>` attributes are the component's own state.
- `App.refresh()` rebuilds the tree and patches, so components re-render in
  place rather than flickering.
- `build()` may return another `Component`, not just a `Node` — a panel is often
  just a composition of smaller ones:

  ```python
  @widget("toolbar")
  class Toolbar(Component):
      def build(self):
          return Row(Button("New"), Button("Open"), Button("Save"), Spacer(), gap="sm")

  class Editor(Component):
      def build(self):
          return Column(Toolbar(), Tree(["Clip"], []), gap=0)
  ```

  Refreshing the parent invalidates the child's cache too, so a child held as an
  instance attribute still rebuilds.

`register_component(name, cls)`, `get_component(name)` and `all_components()`
are available for programmatic registration and lookup.

---

## Native escape hatches

Anything the framework has not wrapped is one line away, and mixes freely with
framework widgets in the same container.

```python
from ResolveScript.ui import Row, native, raw_element

# Full access to the element factory.
Row(native(lambda ui: ui.SpinBox({"ID": "custom", "Value": 3, "Maximum": 10})))

# Or name the element type and pass its native properties directly.
Row(raw_element("TextEdit", {"ID": "notes", "Placeholder": "Notes"}))
```

Raw elements adopt the node key as their native `ID` if you did not set one, so
they stay event-addressable and `find`-able. Attach framework children to them
and the container logic adds them normally.

---

## Theming

Themes are real Qt stylesheets, not cosmetic metadata — they drive hover,
pressed, focus and disabled painting. `theme.dark` and `theme.light` ship ready
made; both are frozen, so derive rather than mutate.

```python
from ResolveScript.ui import theme, dark_theme, light_theme, use_theme, Button

midnight = dark_theme.replace(
    name="midnight",
    colors={**dark_theme.colors, "bg": "#0b0d10"},
)
```

A `theme=` on any widget applies to that widget and everything inside it, so a
single override re-skins a whole panel:

```python
Column(Button("Go", theme=light_theme), theme=light_theme)
```

`use_theme(...)` is a context manager for a global swap:

```python
with use_theme(light_theme):
    mount(Window("Settings", children=[Card(Button("Go"), Button("Cancel"))]))
    # every theme-less widget inside follows
```

### Tokens

| Group | Tokens |
| --- | --- |
| Space | `xs` 4, `sm` 8, `md` 12, `lg` 16, `xl` 24, `xxl` 32, `none` 0 |
| Radius | `none` 0, `sm` 4, `md` 6, `lg` 10, `pill` 999 |
| Font | `xs` 9, `sm` 10, `md` 11, `lg` 13, `xl` 16, `title` 20 (bold) |
| Colour | `bg`, `surface`, `surface_alt`, `surface_hover`, `border`, `border_strong`, `text`, `text_muted`, `text_subtle`, `accent`, `accent_hover`, `accent_active`, `on_accent`, `danger`, `danger_hover`, `success`, `warning` |

`Color` supports `from_hex`, `rgb`, `rgba`, `mix`, `lighten`, `darken`,
`with_alpha` and converts to CSS, Qt or normalised Fusion RGBA.

---

## Dicts and JSON

```python
from ResolveScript.ui import to_dict, from_dict, to_json, from_json

tree = Window("t", children=[Button("Go", key_id="go")])

doc = to_dict(tree)                 # a plain, JSON-safe dict
text = to_json(tree)                # ...as a string

from_dict(doc)                     # back to a Node
from_json(text)                    # ...and back again
```

Handlers cannot be serialised, so they are supplied separately, keyed by node
key and event name:

```python
def save(event):
    print("saved")

node = Button("Go", on_click=save)
data = to_dict(node, handlers={"go": {"on_click": save}})
```

```python
from_dict(data, handlers={"go": {"on_click": save}})
```

Other options:

- `to_dict(source, values=False)` keeps live `Value` objects in the output
  instead of snapshotting them, so a serialised document stays reactive.
- `to_dict(source, skip=[...])` leaves named props out entirely.
- `from_dict(doc, strict=False)` skips prop validation, for documents that
  target a different Resolve version.

---

## Testing headlessly

`MockBackend` mirrors the native element tree in memory. No Resolve, no Qt, no
display.

```python
from ResolveScript.ui import MockBackend, mount, Window, TextField, Button, Value

def test_render_button_writes_the_sequence():
    backend = MockBackend()
    sequence = Value("A001")
    mount(Window("t", children=[
        TextField(value=sequence, key_id="name"),
        Button("Render", key_id="go", on_click=lambda: sequence.set("B002")),
    ]), backend=backend)

    backend.require("go").Click()
    assert sequence.get() == "B002"
```

### Helpers

| Call | Purpose |
| --- | --- |
| `MockBackend()` | the mirror itself |
| `require(id)` | fetch an element by native `ID`, failing the test if absent |
| `text(id)` | current value of a text-ish element |
| `fire(id, event, info=None)` | deliver a native event; `True` if a handler was connected |
| `type_into(id, text)` | set text and fire `TextChanged` |
| `select_index(id, i)` | move a combo/tab selection and fire the change event |
| `rows(id)` | a tree/list's rows as `list[list[str]]` |
| `row_elements(id)` | the row objects themselves, for identity assertions |
| `tree(element=None)` | an indented dump, handy when a test fails |
| `element.properties` | the raw native property dict |

Because `require` returns the live element, you can assert patching directly —
the row object is the same one before and after the update:

```python
backend = MockBackend()
rows = Value([{"cells": ["A001", "00:00:10:00"]}])
mount(Window("t", children=[Tree(["Clip", "Duration"], rows, key_id="clips")]),
      backend=backend)

item = backend.row_elements("clips")[0]
rows.set([{"cells": ["A001", "00:00:12:00"]}])

assert backend.row_elements("clips")[0] is item      # patched, not rebuilt
assert backend.rows("clips") == [["A001", "00:00:12:00"]]
```

`get_backend()` picks `FusionBackend` inside Resolve and `MockBackend`
elsewhere; pass `backend=` explicitly to `mount`/`run` to override.

---

## Runtime control

```python
from ResolveScript.ui import mount, run, App, Window, Button

panel = Window("Tools", children=[Button("Render", key_id="render-btn")])

app = mount(panel)                     # build and show, no event loop
app = mount(panel, theme=light_theme)  # ...with a theme override

app.find("render-btn")       # -> Bound (a mounted node), or None
app.require("render-btn")   # -> Bound, raises if missing

app.refresh()                # rebuild the tree and patch
app.update()                 # flush pending state
app.show()                   # display
app.close()                  # close and stop
app.element                  # the native root element
app.window                   # the root Bound
app.run()                    # block on the event loop, returns an exit code

with mount(panel) as app:    # context manager: closes on exit
    app.refresh()

App(panel)                   # construct without showing
```

`run(panel, on_close=...)` is `mount(...).run()` and returns the exit code — that
is what a Resolve script's entry point wants.

`refresh()` re-derives the tree, including rebuilding any registered
`Component` nodes, and then patches. Use it when a change cannot be expressed as
a `Value` (e.g. a list of plain objects got replaced wholesale).

---

## Errors

All framework errors derive from `UIError`:

| Error | Raised when |
| --- | --- |
| `ElementError` | unknown widget kind, unknown prop, non-container child, wrong root |
| `BindingError` | a `TwoWay` over an unsettable source, a missing binding target |
| `SchemaError` | a dict/JSON document is structurally wrong |
| `BackendUnavailable` | the live Resolve/Fusion API is not reachable |
| `BackendError` | the backend rejected a native call |

`BackendUnavailable` is worth calling out: if you run against a stubbed Resolve
that has no `Fusion()`, you get a clear message rather than a bare
`AttributeError`.

---

## Extending: custom widget specs

A widget is a `WidgetSpec` — a table mapping logical props to native ones. No
renderer changes needed.

```python
from ResolveScript.ui import PropSpec, WidgetSpec, register_spec, node

register_spec(WidgetSpec(
    kind="led",
    native_type="Label",
    props={
        "caption": PropSpec("caption", "Text", kind="str"),
        "lit": PropSpec("lit", "Enabled", True, kind="bool"),
    },
    events={"on_click": "Clicked"},
    documented=False,          # not part of the wrapped Resolve surface
))

node("led", caption="REC", lit=True)
```

`PropSpec` fields: `name`, `native`, `default`, `kind` (`value`, `str`, `int`,
`bool`, `float`, `list`, `size`, `font`, `color`, `align`, `geometry`, `scroll`),
`two_way`, `event`, `read`/`write` transforms, `via` (deliver through a method
such as `AddItems`), `strategy` (`bulk`, `each`, `rows`) and `remove`.

`all_specs()` and `get_spec(kind)` introspect the registry.

---

## How it fits together

```
   Window(Column(Button("Go", variant="primary"), gap="md"))
        │  dsl.py            composition functions -> Node
        ▼
   Node(kind="column", props={...}, children=(Node(kind="button", ...),))
        │  node.py           identity (keys), TwoWay, Raw escape hatches
        │  state.py          Value / Computed subscriptions
        │  spec.py           logical prop -> native Fusion property
        ▼
   Renderer                      retained mount + keyed reconcile + patching
        │  backends/fusion.py  real Resolve   (UIManager + UIDispatcher)
        │  backends/mock.py    headless mirror (tests)
        │  jsonio.py           dict / JSON
        ▼
   native properties
```

The renderer never rebuilds an element that already has the right key. That
single rule is what gives you a modern, declarative API on top of a Qt toolkit
that was designed to be driven imperatively.
