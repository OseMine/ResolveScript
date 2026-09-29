"""Tests for the UI framework, driven through the headless mock backend.

The mock mirrors Fusion's element and event API, so these assertions are
evidence about the real thing: the same ``ui.Label({...})`` calls happen here
and in Resolve, and events travel the same ``win.On[id].Event`` path.
"""

from __future__ import annotations

import json

import pytest

from ResolveScript import ui
from ResolveScript.ui.backends.mock import MockBackend
from ResolveScript.ui.render import Renderer


@pytest.fixture
def backend() -> MockBackend:
    return MockBackend()


def mount(node, backend: MockBackend) -> ui.App:
    app = ui.App(node, backend=backend)
    app.show()
    return app


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------


class TestNodes:
    def test_dsl_builds_nodes(self):
        assert ui.Column(ui.Label("hi")).kind == "column"
        assert ui.Window("t").kind == "window"
        assert ui.Dialog("t").kind == "dialog"

    def test_children_accept_both_spellings(self):
        positional = ui.Window("t", ui.Label("a"))
        keyword = ui.Window("t", children=[ui.Label("a")])
        assert [c.kind for c in positional.children] == ["label"]
        assert [c.kind for c in keyword.children] == ["label"]

    def test_nested_sequences_are_flattened(self):
        column = ui.Column([ui.Label("a"), (ui.Label("b"), ui.Label("c"))], None)
        assert [child.props["text"] for child in column.children] == ["a", "b", "c"]

    def test_none_children_are_ignored(self):
        assert ui.Row(ui.Label("a"), None).children[0].props["text"] == "a"

    def test_key_defaults_to_kind_and_counter(self):
        assert ui.Label("a").id.startswith("label-")

    def test_explicit_key_survives_dsl_kwargs(self):
        # The DSL forwards **props, so ``key=`` must not become a prop.
        node = ui.Column(ui.Label("a"), key="body")
        assert node.id == "body"
        assert "key" not in node.props

    def test_forwarded_key_is_dropped_even_when_the_node_has_one(self, backend):
        # Helpers that build sub-nodes with generated keys (Tabs) would
        # otherwise pass a forwarded ``key=`` straight through as a prop.
        node = ui.Tabs(["A", "B"], ui.Label("a"), key="mine")
        bar = node.children[0]
        assert bar.id == "tab-bar"
        assert "key" not in bar.props
        mount(ui.Window("t", node), backend)

    def test_children_must_be_renderable(self):
        with pytest.raises(ui.ElementError, match="expected a Node"):
            ui.Column("just a string")

    def test_rejects_non_container_children(self, backend):
        leaf = ui.Node("label", {"text": "b"}, key="inner")
        with pytest.raises(ui.ElementError, match="does not accept children"):
            mount(ui.Window("t", ui.Node("label", {"text": "a"}, (leaf,), key="a")), backend)

    def test_root_must_be_a_window(self, backend):
        with pytest.raises(ui.ElementError, match="must be 'window' or 'dialog'"):
            mount(ui.Label("orphan"), backend)

    def test_raw_escape_hatch(self, backend):
        node = ui.Column(
            ui.Label("a"),
            ui.native(lambda factory: factory.SpinBox({"ID": "custom", "Value": 3})),
        )
        app = mount(ui.Window("t", node), backend)
        assert backend.require("custom")._type == "SpinBox"
        assert app.window.find(app.window.key) is app.window

    def test_raw_element_by_name(self, backend):
        editor = ui.raw_element("TextEdit", {"Text": "raw"}, key="editor")
        mount(ui.Window("t", key_id="main", children=[editor]), backend)
        assert backend.require("main")._type == "Window"
        assert backend.require("editor")._type == "TextEdit"

    def test_raw_element_reports_unknown_types(self, backend):
        with pytest.raises(ui.BackendError, match="no element type"):
            mount(ui.Window("t", ui.raw_element("Nope")), backend)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_unknown_widget_kind(self):
        with pytest.raises(ui.ElementError, match="unknown widget kind"):
            ui.node("flibbertigibbet")

    def test_unknown_prop_names_the_known_ones(self, backend):
        with pytest.raises(ui.ElementError, match="tooltipe"):
            mount(ui.Window("t", ui.Button("Go", tooltipe="hi")), backend)

    def test_unknown_event_is_rejected(self, backend):
        with pytest.raises(ui.ElementError, match="on_hoverer"):
            mount(ui.Window("t", ui.Button("Go", on_hoverer=print)), backend)

    def test_strict_renderer_allows_unknown_props(self, backend):
        renderer = Renderer(backend, strict=False)
        renderer.mount(ui.Window("t", ui.Button("Go", key_id="go", tooltipe="hi")))
        assert backend.require("go")._type == "Button"

    def test_mock_rejects_unknown_element_types(self):
        with pytest.raises(ui.BackendError, match="no element type"):
            ui.App(ui.Window("t", ui.raw_element("Wobble")), backend=MockBackend(strict=True))

    def test_key_id_cannot_change_after_mount(self, backend):
        app = mount(ui.Window("t", ui.Button("Go", key="slot", key_id="go")), backend)
        with pytest.raises(ui.ElementError, match="key_id cannot change"):
            app.renderer.update(ui.Window("t", ui.Button("Go", key="slot", key_id="gone")))


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


class TestLayout:
    def test_column_stacks_vertically(self, backend):
        app = mount(
            ui.Window("t", ui.Column(ui.Label("a"), ui.Label("b"), key_id="col")), backend
        )
        types = [child._type for child in app.require("col").element.GetChildren()]
        assert types == ["Label", "VGap", "Label"]

    def test_row_uses_hgap(self, backend):
        app = mount(ui.Window("t", ui.Row(ui.Label("a"), ui.Label("b"), key_id="row")), backend)
        types = [child._type for child in app.require("row").element.GetChildren()]
        assert types == ["Label", "HGap", "Label"]

    def test_no_gap_elements_when_gap_is_zero(self, backend):
        app = mount(
            ui.Window("t", ui.Column(ui.Label("a"), ui.Label("b"), gap=0, key_id="col")), backend
        )
        assert [c._type for c in app.require("col").element.GetChildren()] == ["Label", "Label"]

    def test_gap_size_follows_the_space_scale(self, backend):
        app = mount(
            ui.Window("t", ui.Column(ui.Label("a"), ui.Label("b"), gap="xl", key_id="col")),
            backend,
        )
        gap = app.require("col").element.GetChildren()[1]
        assert gap._type == "VGap"
        assert gap.properties["Size"] == ui.theme.gap("xl")

    def test_spacer_follows_the_parent_axis(self, backend):
        app = mount(
            ui.Window(
                "t",
                ui.Row(ui.Spacer(), key_id="row"),
                ui.Column(ui.Spacer(vertical=True), key_id="col"),
            ),
            backend,
        )
        assert app.require("row").element.GetChildren()[0]._type == "HGroup"
        assert app.require("col").element.GetChildren()[0]._type == "VGroup"

    def test_divider_orientation(self, backend):
        app = mount(
            ui.Window("t", ui.Row(ui.Divider(), ui.Divider("vertical"), key_id="row")), backend
        )
        types = [c._type for c in app.require("row").element.GetChildren()]
        assert "HLine" in types and "VLine" in types

    def test_weight_maps_to_native(self, backend):
        mount(ui.Window("t", ui.Label("a", weight=1, key_id="lbl")), backend)
        assert backend.require("lbl").properties["Weight"] == 1

    def test_padding_becomes_stylesheet_padding(self, backend):
        mount(ui.Window("t", ui.Column(ui.Label("a"), padding="md", key_id="col")), backend)
        assert "padding" in backend.require("col").properties["StyleSheet"]


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


class TestReconcile:
    def test_children_are_matched_by_key(self, backend):
        keep = ui.Label("keep", key="keep")
        drop = ui.Label("drop", key="drop")
        app = mount(ui.Window("t", ui.Column(keep, drop, key_id="col")), backend)
        before = app.require("col").element.GetChildren()[0]

        app.renderer.update(ui.Window("t", ui.Column(keep, key_id="col")))
        after = app.require("col").element.GetChildren()
        assert [c.properties["Text"] for c in after] == ["keep"]
        assert after[0] is before

    def test_changed_widget_is_patched_not_recreated(self, backend):
        app = mount(ui.Window("t", ui.Label("before", key_id="lbl")), backend)
        element = backend.require("lbl")

        app.renderer.update(ui.Window("t", ui.Label("after", key_id="lbl")))
        assert backend.require("lbl") is element
        assert backend.text("lbl") == "after"

    def test_changing_widget_kind_swaps_the_element(self, backend):
        app = mount(ui.Window("t", ui.Label("x", key="slot")), backend)
        app.renderer.update(ui.Window("t", ui.Button("x", key="slot")))
        assert backend.require("slot")._type == "Button"

    def test_reorder_moves_existing_elements(self, backend):
        a = ui.Label("a", key="a")
        b = ui.Label("b", key="b")
        app = mount(ui.Window("t", ui.Column(a, b, gap=0, key_id="col")), backend)
        app.renderer.update(ui.Window("t", ui.Column(b, a, gap=0, key_id="col")))
        assert [c.properties["Text"] for c in app.require("col").element.GetChildren()] == [
            "b",
            "a",
        ]

    def test_new_node_reuses_a_stable_key(self, backend):
        app = mount(ui.Window("t", ui.Label("a", key_id="lbl")), backend)
        element = backend.require("lbl")
        app.renderer.update(ui.Window("t", ui.Label("b", key_id="lbl")))
        assert backend.require("lbl") is element


class TestStack:
    def test_only_the_active_child_is_visible(self, backend):
        index = ui.Value(0)
        app = mount(
            ui.Window("t", ui.Stack(ui.Label("one"), ui.Label("two"), index=index, key_id="s")),
            backend,
        )
        children = app.require("s").element.GetChildren()
        assert [c.properties["Visible"] for c in children] == [True, False]

        index.set(1)
        assert [c.properties["Visible"] for c in children] == [False, True]

    def test_tabs_share_one_source_of_truth(self, backend):
        index = ui.Value(0)
        app = mount(ui.Window("t", ui.Tabs(["A", "B"], ui.Label("one"), ui.Label("two"),
                                  value=index)), backend)
        body = app.require("tab-body").element.GetChildren()
        assert body[0].properties["Visible"] is True
        backend.select_index("tab-bar", 1, "CurrentChanged")
        assert index.get() == 1
        assert body[1].properties["Visible"] is True


# ---------------------------------------------------------------------------
# Reactivity
# ---------------------------------------------------------------------------


class TestReactivity:
    def test_value_pushes_to_the_widget(self, backend):
        name = ui.Value("a")
        mount(ui.Window("t", ui.TextField(value=name, key_id="f")), backend)
        name.set("b")
        assert backend.text("f") == "b"

    def test_typing_writes_back_to_the_value(self, backend):
        name = ui.Value("a")
        mount(ui.Window("t", ui.TextField(value=name, key_id="f")), backend)
        assert backend.type_into("f", "typed")
        assert name.get() == "typed"

    def test_feedback_loop_does_not_spin(self, backend):
        name = ui.Value("a")
        mount(ui.Window("t", ui.TextField(value=name, key_id="f")), backend)
        name.set("b")
        before = name.version
        backend.type_into("f", "b")  # the widget already agrees
        assert name.version == before

    def test_computed_derives(self, backend):
        first = ui.Value("Ada")
        last = ui.Value("Lovelace")
        full = ui.Computed(lambda: f"{first.get()} {last.get()}")
        mount(ui.Window("t", ui.TextField(value=full, key_id="f")), backend)
        assert backend.text("f") == "Ada Lovelace"
        last.set("King")
        assert backend.text("f") == "Ada King"

    def test_computed_is_not_written_back(self, backend):
        source = ui.Value(1)
        derived = ui.Computed(lambda: source.get() * 2)
        mount(ui.Window("t", ui.Slider(value=derived, key_id="s")), backend)
        backend.require("s")._props["Value"] = 50
        backend.fire("s", "ValueChanged")
        assert source.get() == 1

    def test_computed_writes_back_to_a_two_way_wrapper(self, backend):
        # The slider shows the derived value; editing it stores the source.
        amount = ui.Value(10)
        mount(
            ui.Window(
                "t",
                ui.Slider(
                    value=ui.TwoWay(amount, read=lambda a: a * 2, write=lambda v: v // 2),
                    key_id="s",
                ),
            ),
            backend,
        )
        assert backend.require("s").properties["Value"] == 20

        backend.require("s")._props["Value"] = 30
        backend.fire("s", "ValueChanged")
        assert amount.get() == 15

    def test_two_way_over_a_computed_is_rejected(self, backend):
        doubled = ui.Computed(lambda: 4)
        with pytest.raises(ui.BindingError, match="write="):
            mount(ui.Window("t", ui.Slider(value=ui.TwoWay(doubled), key_id="s")), backend)

    def test_batch_notifies_once(self, backend):
        seen = []
        a, b = ui.Value(0), ui.Value(0)
        with ui.batch():
            a.subscribe(lambda v: seen.append(("a", v)))
            a.set(1)
            b.set(1)
        assert seen == [("a", 1)]

    def test_events_table_is_enabled_for_bound_inputs(self, backend):
        mount(ui.Window("t", ui.Slider(value=ui.Value(1), key_id="s")), backend)
        assert backend.require("s").properties["Events"] == {"ValueChanged": True}

    def test_a_plain_handler_still_enables_its_event(self, backend):
        # Qt only delivers ValueChanged for widgets that asked for it, so a
        # handler has to switch the event on whether or not it is bound.
        mount(ui.Window("t", ui.Slider(value=1, key_id="s", on_change=lambda e: None)), backend)
        assert backend.require("s").properties["Events"] == {"ValueChanged": True}

    def test_no_handler_and_no_binding_needs_no_event_table(self, backend):
        mount(ui.Window("t", ui.Slider(value=1, key_id="s")), backend)
        assert "Events" not in backend.require("s").properties

    def test_two_way_value_updates_many_widgets(self, backend):
        amount = ui.Value(5)
        mount(
            ui.Window(
                "t",
                ui.Column(
                    ui.Number(value=amount, key_id="n"),
                    ui.Slider(value=amount, key_id="s"),
                    ui.Label(text=amount, key_id="l"),
                    key_id="col",
                ),
            ),
            backend,
        )
        amount.set(7)
        assert backend.require("n").properties["Value"] == 7
        assert backend.require("s").properties["Value"] == 7
        assert backend.text("l") == "7"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class TestEvents:
    def test_click_reaches_the_handler(self, backend):
        seen = []
        app = mount(ui.Window("t", ui.Button("Go", key_id="go", on_click=seen.append)), backend)
        app.backend.require("go").Click()
        assert [event.type for event in seen] == ["Clicked"]

    def test_zero_argument_handlers_work(self, backend):
        calls = []
        mount(ui.Window("t", ui.Button("Go", key_id="go", on_click=lambda: calls.append(1))), backend)
        backend.require("go").Click()
        assert calls == [1]

    def test_selection_event_carries_an_index(self, backend):
        seen = []
        mount(
            ui.Window(
                "t",
                ui.Combo(["a", "b"], key_id="c", on_change=seen.append),
            ),
            backend,
        )
        backend.select_index("c", 1)
        assert seen[0].index == 1

    def test_unknown_event_reports_no_handler(self, backend):
        app = mount(ui.Window("t", ui.Button("Go", key_id="go", on_click=lambda: None)), backend)
        assert app.backend.fire("go", "Slid") is False

    def test_window_close_exits_the_loop(self, backend):
        app = mount(ui.Window("t", key_id="main"), backend)
        app.backend.fire("main", "Close")
        assert backend.exit_code == 0

    def test_user_on_close_runs_before_the_loop_stops(self, backend):
        seen = []
        app = ui.App(
            ui.Window("t", key_id="main", on_close=lambda: seen.append("closed")), backend=backend
        )
        app.show()
        backend.fire("main", "Close")
        assert seen == ["closed"]

    def test_app_level_on_close(self, backend):
        seen = []
        app = ui.App(ui.Window("t", key_id="main"), backend=backend, on_close=seen.append)
        app.show()
        backend.fire("main", "Close")
        assert len(seen) == 1

    def test_run_returns_an_exit_code(self, backend):
        assert ui.run(ui.Window("t", key_id="main"), backend=backend) == 0


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


class TestCollections:
    def test_combo_items_are_added_through_the_method(self, backend):
        mount(ui.Window("t", ui.Combo(["a", "b"], key_id="c")), backend)
        assert backend.require("c").properties["ItemText"] == ["a", "b"]

    def test_combo_index_is_two_way(self, backend):
        choice = ui.Value(0)
        mount(ui.Window("t", ui.Combo(["a", "b"], value=choice, key_id="c")), backend)
        backend.select_index("c", 1)
        assert choice.get() == 1

    def test_tabs_grow_and_shrink(self, backend):
        items = ui.Value(["a", "b", "c"])
        mount(ui.Window("t", ui.Node("tabs", {"items": items, "key_id": "t"})), backend)
        assert backend.require("t").properties["TabText"] == ["a", "b", "c"]

        items.set(["a", "b"])
        assert backend.require("t").properties["TabText"] == ["a", "b"]

        items.set(["z", "y", "x", "w"])
        assert backend.require("t").properties["TabText"] == ["z", "y", "x", "w"]

    def test_tree_columns_use_set_header_labels(self, backend):
        mount(ui.Window("t", ui.Tree(["A", "B"], key_id="g")), backend)
        assert backend.require("g").properties["HeaderLabels"] == ["A", "B"]

    def test_tree_rows_render(self, backend):
        rows = [{"cells": ["a", "1"]}, {"cells": ["b", "2"]}]
        mount(ui.Window("t", ui.Tree(["A", "B"], rows, key_id="g")), backend)
        assert backend.rows("g") == [["a", "1"], ["b", "2"]]

    def test_row_updates_patch_the_existing_items(self, backend):
        rows = ui.Value([{"cells": ["a", "1"]}])
        mount(ui.Window("t", ui.Tree(["A", "B"], rows, key_id="g")), backend)
        item = backend.row_elements("g")[0]

        rows.set([{"cells": ["a", "2"]}])
        assert backend.rows("g") == [["a", "2"]]
        assert backend.row_elements("g")[0] is item

    def test_reshaped_rows_rebuild_the_items(self, backend):
        rows = ui.Value([{"cells": ["a", "1"]}])
        mount(ui.Window("t", ui.Tree(["A"], rows, key_id="g")), backend)
        first = backend.row_elements("g")[0]

        rows.set([{"cells": ["a", "1"]}, {"cells": ["b", "2"]}])
        assert backend.rows("g") == [["a", "1"], ["b", "2"]]
        assert backend.row_elements("g")[0] is not first

    def test_nested_rows(self, backend):
        rows = [{"cells": ["a", "1"], "children": [{"cells": ["a.1", "child"]}]}]
        app = mount(ui.Window("t", ui.Tree(["A", "B"], rows, key_id="g")), backend)
        child = app.require("g").row_item(0)
        assert len(child.children) == 1
        assert backend.row_elements("g")[0].GetChildren()[0].properties["Text"] == ["a.1", "child"]

    def test_nested_row_updates_are_patched(self, backend):
        rows = ui.Value([{"cells": ["a", "1"], "children": [{"cells": ["a.1", "x"]}]}])
        app = mount(ui.Window("t", ui.Tree(["A", "B"], rows, key_id="g")), backend)
        child_element = app.require("g").row_item(0).children[0].element
        rows.set([{"cells": ["a", "1"], "children": [{"cells": ["a.1", "y"]}]}])
        assert child_element.properties["Text"] == ["a.1", "y"]

    def test_rows_accept_plain_strings(self, backend):
        mount(ui.Window("t", ui.List(["one", "two"], key_id="l")), backend)
        assert backend.rows("l") == [["one"], ["two"]]

    def test_row_selection_flag(self, backend):
        rows = [{"cells": ["a"], "selected": True}]
        app = mount(ui.Window("t", ui.List(rows, key_id="l")), backend)
        assert app.require("l").row_item(0).element.properties["Selected"] is True

    def test_empty_rows_fill_nothing(self, backend):
        mount(ui.Window("t", ui.Tree(["A"], [], key_id="g")), backend)
        assert backend.rows("g") == []

    def test_bad_row_shape_is_reported(self, backend):
        with pytest.raises(ui.ElementError, match="cannot use"):
            mount(ui.Window("t", ui.Tree(["A"], [object()], key_id="g")), backend)

    def test_bound_rows_accessor(self, backend):
        rows = ui.Value([["a", "1"]])
        app = mount(ui.Window("t", ui.Node("tree", {"rows": rows, "key_id": "g"})), backend)
        assert app.require("g").rows() == [["a", "1"]]
        assert app.require("g").row_item(5) is None


# ---------------------------------------------------------------------------
# Deriving rows from objects
# ---------------------------------------------------------------------------


class Pool:
    """Resolve's shape: GetSomething() and nothing else.

    ``Pool`` is the little both kinds share. ``Clip`` and ``Bin`` deliberately
    do *not* subclass each other — Resolve's MediaPoolItem and MediaPoolFolder
    are unrelated types, which is exactly why a column spanning both levels
    has to tolerate a missing method.
    """

    def __init__(self, name):
        self.name = name

    def GetName(self):
        return self.name


class Clip(Pool):
    def __init__(self, name, kind=None, tags=()):
        super().__init__(name)
        self.kind, self.tags = kind, list(tags)

    def GetClipProperty(self, key):
        return {"Type": self.kind, "Frames": len(self.tags)}.get(key)


class Bin(Pool):
    def __init__(self, name, kids=()):
        super().__init__(name)
        self.kids = list(kids)

    def GetClipList(self):
        return self.kids


class TestRows:
    def test_a_string_column_reads_a_method(self):
        assert ui.rows([Clip("A001")], "GetName")[0]["cells"] == ["A001"]

    def test_a_string_column_reads_a_plain_attribute(self):
        assert ui.rows([Clip("A001", kind="Video")], "kind")[0]["cells"] == ["Video"]

    def test_a_callable_column_is_called(self):
        assert ui.rows([Clip("A001", kind="Video")], lambda c: c.kind.upper())[0]["cells"] == [
            "VIDEO"
        ]

    def test_call_passes_arguments(self):
        assert ui.rows([Clip("A001", kind="Video")], ui.call("GetClipProperty", "Type"))[0][
            "cells"
        ] == ["Video"]

    def test_several_columns(self):
        clips = [Clip("A001", "Video"), Clip("B002", "Audio")]
        built = ui.rows(clips, "GetName", ui.call("GetClipProperty", "Type"))
        assert [row["cells"] for row in built] == [["A001", "Video"], ["B002", "Audio"]]

    def test_missing_becomes_the_placeholder_not_the_word_none(self):
        # str(None) in a cell reads as a bug in the tool, not as absent data.
        built = ui.rows([Clip("A001")], ui.call("GetClipProperty", "Type"))
        assert built[0]["cells"] == [""]
        assert ui.rows([Clip("A001")], ui.call("GetClipProperty", "Type"), placeholder="-")[
            0
        ]["cells"] == ["-"]

    def test_maybe_does_not_substitute_for_a_none_result(self):
        # maybe() forgives a *missing method*. A method that ran and said "no
        # value" is a different thing, and the placeholder rule applies.
        assert ui.rows([Clip("A001")], ui.maybe("GetClipProperty", "Type", default="?"))[0][
            "cells"
        ] == [""]

    def test_no_columns_is_an_error(self):
        with pytest.raises(ui.ElementError, match="at least one column"):
            ui.rows([Clip("A001")])

    def test_a_typo_names_the_type_and_the_attribute(self):
        with pytest.raises(ui.ElementError, match="cannot read 'GetNmae' from Clip"):
            ui.rows([Clip("A001")], "GetNmae")

    def test_a_method_needing_arguments_says_so(self):
        with pytest.raises(ui.ElementError, match="use call"):
            ui.rows([Clip("A001")], "GetClipProperty")

    def test_call_on_a_missing_method_is_reported(self):
        with pytest.raises(ui.ElementError, match="has no callable 'GetNmae'"):
            ui.rows([Clip("A001")], ui.call("GetNmae"))

    def test_a_non_accessor_column_is_rejected(self):
        with pytest.raises(ui.ElementError, match="must be a string or a callable"):
            ui.rows([Clip("A001")], 7)

    def test_maybe_yields_the_default_for_a_missing_method(self):
        # A Bin has no GetClipProperty at all; that is what maybe() forgives.
        assert ui.rows([Bin("Bins")], ui.maybe("GetClipProperty", "Type", default="folder"))[
            0
        ]["cells"] == ["folder"]

    def test_maybe_reads_the_method_when_present(self):
        clips = [Clip("A001", "Video")]
        assert ui.rows(clips, ui.maybe("GetClipProperty", "Type", default="folder"))[0][
            "cells"
        ] == ["Video"]

    def test_maybe_with_no_arguments_reads_an_attribute_or_method(self):
        bins = [Bin("Reels", [Bin("A001")])]
        built = ui.rows(bins, "GetName", children=ui.maybe("GetClipList", default=()))
        assert built[0]["children"][0]["cells"] == ["A001"]

    def test_maybe_returns_a_present_attribute_unread(self):
        assert ui.rows([Clip("A001", "Video")], ui.maybe("kind", default="?"))[0]["cells"] == [
            "Video"
        ]

    def test_a_folder_and_a_clip_tolerate_being_different_types(self):
        built = ui.rows(
            [Bin("Bins", [Clip("A001", "Video")])],
            "GetName",
            ui.maybe("GetClipProperty", "Type", default="folder"),
            children=ui.maybe("GetClipList", default=()),
        )
        assert built[0]["cells"] == ["Bins", "folder"]
        # A clip has no children accessor at all, so it is a leaf.
        assert built[0]["children"][0]["cells"] == ["A001", "Video"]
        assert built[0]["children"][0]["children"] == []

    def test_maybe_does_not_swallow_a_typo_in_a_strict_column(self):
        # call() stays strict; only maybe() forgives an absent method.
        with pytest.raises(ui.ElementError, match="has no callable 'GetNmae'"):
            ui.rows([Clip("A001")], ui.call("GetNmae"))

    def test_an_accessor_returning_none_children_is_an_empty_list(self):
        assert ui.rows([Clip("A001")], "GetName", children=lambda c: None)[0]["children"] == []

    def test_children_recurse_with_the_same_columns(self):
        built = ui.rows(
            [Bin("Bins", [Bin("Reels", [Bin("A001")])])],
            "GetName",
            children=lambda b: b.GetClipList(),
        )
        assert built[0]["children"][0]["cells"] == ["Reels"]
        assert built[0]["children"][0]["children"][0]["cells"] == ["A001"]

    def test_children_may_be_prebuilt_rows_for_differing_columns(self):
        built = ui.rows(
            [Bin("Bins", [Bin("Reels")])],
            "GetName",
            children=lambda b: [{"cells": [b.GetName(), "1 clip"]}],
        )
        assert built[0]["children"][0]["cells"] == ["Bins", "1 clip"]

    def test_a_clip_is_a_leaf_when_its_accessor_returns_nothing(self):
        built = ui.rows(
            [Bin("Reels", [Bin("A001")])], "GetName", children=lambda b: b.GetClipList()
        )
        assert built[0]["children"][0]["children"] == []

    def test_the_id_option_is_stringified(self):
        assert ui.rows([Clip("A001")], "GetName", id="GetName")[0]["id"] == "A001"

    def test_the_selected_option_only_sets_the_flag_when_truthy(self):
        clips = [Clip("A001"), Clip("B002")]
        assert "selected" not in ui.rows(clips, "GetName")[0]
        assert ui.rows(clips, "GetName", selected=lambda c: c.name == "B002")[1]["selected"] is True

    def test_tooltip_and_icon(self):
        built = ui.rows([Clip("A001")], "GetName", tooltip="GetName", icon="GetName")
        assert built[0]["tooltip"] == "A001"
        assert built[0]["icon"] == "A001"

    def test_the_rows_feed_a_tree_directly(self, backend):
        clips = [Clip("A001", "Video"), Clip("B002", "Audio")]
        built = ui.rows(clips, "GetName", ui.call("GetClipProperty", "Type"))
        mount(ui.Window("t", ui.Tree(["Clip", "Type"], built, key_id="g")), backend)
        assert backend.rows("g") == [["A001", "Video"], ["B002", "Audio"]]

    def test_the_rows_feed_a_list_directly(self, backend):
        clips = [Clip("A001"), Clip("B002")]
        mount(ui.Window("t", ui.List(ui.rows(clips, "GetName"), key_id="l")), backend)
        assert backend.rows("l") == [["A001"], ["B002"]]


# ---------------------------------------------------------------------------
# Theming
# ---------------------------------------------------------------------------


class TestTheming:
    def test_button_variant_reaches_the_stylesheet(self, backend):
        mount(
            ui.Window("t", ui.Button("Go", variant="primary", key_id="b"), ui.Button("No", key_id="n")),
            backend,
        )
        primary = backend.require("b").properties["StyleSheet"]
        default = backend.require("n").properties["StyleSheet"]
        assert primary != default
        assert ui.theme.color("accent").hex in primary

    def test_window_receives_the_window_stylesheet(self, backend):
        app = mount(ui.Window("t"), backend)
        assert "QWidget" in backend.require(app.root.id).properties["StyleSheet"]

    def test_theme_cascades_to_children(self, backend):
        light = ui.light_theme
        mount(
            ui.Window("t", ui.Column(ui.Button("Go", key_id="b"), theme=light), theme=light),
            backend,
        )
        assert ui.light_theme.color("surface").hex in backend.require("b").properties["StyleSheet"]

    def test_use_theme_is_scoped(self, backend):
        with ui.use_theme(ui.light_theme):
            mount(ui.Window("t", ui.Label("a", key_id="inside")), backend)
            inside = backend.require("inside").properties["StyleSheet"]
        with ui.use_theme(ui.dark_theme):
            mount(ui.Window("t", ui.Label("a", key_id="outside")), backend)
            outside = backend.require("outside").properties["StyleSheet"]
        assert inside != outside


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


@ui.widget("test-panel")
class Panel(ui.Component):
    def __init__(self, title: str = "Panel"):
        super().__init__(title=title)
        self.count = ui.Value(0)

    def build(self):
        return ui.Card(
            ui.Heading(self.props["title"], key_id="title"),
            ui.Label(text=self.count, key_id="count"),
            gap="sm",
        )


class TestComponents:
    def test_component_renders_as_a_node(self, backend):
        mount(ui.Window("t", Panel("Hello")), backend)
        assert backend.text("count") == "0"

    def test_component_children_see_its_value(self, backend):
        panel = Panel("Hello")
        mount(ui.Window("t", panel), backend)
        panel.count.set(3)
        assert backend.text("count") == "3"

    def test_component_is_cached(self):
        panel = Panel("x")
        first = panel.to_node()
        assert panel.to_node() is first

        second = panel.refresh()
        assert second is not first
        assert panel.to_node() is second

    def test_component_must_return_a_node(self):
        class Bad(ui.Component):
            def build(self):
                return "nope"

        with pytest.raises(ui.ElementError, match="expected a Node"):
            Bad().to_node()

    def test_a_component_may_return_another_component(self, backend):
        class Inner(ui.Component):
            def build(self):
                return ui.Label("deep", key_id="deep")

        class Outer(ui.Component):
            def build(self):
                return Inner()

        mount(ui.Window("t", Outer()), backend)
        assert backend.text("deep") == "deep"

    def test_refreshing_a_parent_invalidates_a_held_child(self, backend):
        # Outer keeps Inner as an attribute, so Outer.refresh() has to reach
        # past its own cache or the child would stay frozen forever.
        class Inner(ui.Component):
            def build(self):
                return ui.Label("first", key_id="l")

        class Outer(ui.Component):
            def __init__(self, **props):
                super().__init__(**props)
                self.inner = Inner()

            def build(self):
                return self.inner

        outer = Outer()
        app = mount(ui.Window("t", outer), backend)
        assert backend.text("l") == "first"

        outer.inner.build = lambda: ui.Label("second", key_id="l")
        app.refresh()
        assert backend.text("l") == "second"

    def test_component_without_build(self):
        with pytest.raises(NotImplementedError):
            ui.Component().build()

    def test_component_instantiated_by_name(self):
        assert ui.get_component("test-panel") is Panel
        assert Panel.name == "test-panel"

    def test_unknown_component(self):
        with pytest.raises(ui.ElementError, match="unknown component"):
            ui.get_component("nope")

    def test_with_props_keeps_state(self):
        panel = Panel("a")
        panel.count.set(7)
        clone = panel.with_props(title="b")
        assert clone.props["title"] == "b"
        assert clone.count is panel.count

    def test_app_refresh_rebuilds(self, backend):
        panel = Panel("a")
        app = mount(ui.Window("t", panel), backend)
        panel.props["title"] = "changed"
        app.refresh()
        assert backend.text("title") == "changed"

    def test_app_refresh_patches_auto_keyed_nodes(self, backend):
        # build() mints fresh auto-keys each call, so without carrying them
        # across a refresh the renderer would see every node as new and
        # replace the subtree instead of patching it.
        class Auto(ui.Component):
            def build(self):
                return ui.Card(ui.Label("hi", key_id="l"), ui.Label("there"))

        app = mount(ui.Window("t", Auto()), backend)
        label = backend.require("l")
        app.refresh()
        assert backend.require("l") is label
        assert backend.text("l") == "hi"

    def test_an_explicit_key_wins_over_a_carried_one(self, backend):
        # A key the author chose is a statement about identity, so a refresh
        # must honour it instead of pinning the node to the old slot.
        counter = iter(["first", "second"])

        class Renamed(ui.Component):
            def build(self):
                return ui.Label("hi", key=next(counter))

        app = mount(ui.Window("t", Renamed()), backend)
        first = backend.require("first")
        app.refresh()
        assert backend.require("second") is not first

    def test_factory_is_accepted(self, backend):
        app = ui.App(lambda: ui.Window("t", ui.Label("made", key_id="l")), backend=backend)
        app.show()
        assert backend.text("l") == "made"

    def test_factory_must_make_a_window(self, backend):
        with pytest.raises(ui.ElementError, match="must be 'window'"):
            ui.App(lambda: ui.Label("x"), backend=backend)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


class TestJson:
    def test_round_trip(self, backend):
        panel = ui.Window(
            "Panel",
            ui.Column(ui.Heading("Out"), ui.Button("Go", key_id="go"), gap="md"),
        )
        data = ui.to_dict(panel)
        assert json.loads(json.dumps(data)) == data
        app = mount(ui.from_dict(data), backend)
        assert backend.require("go")._type == "Button"
        assert app.root.element._type == "Window"

    def test_defaults_are_omitted(self):
        data = ui.to_dict(ui.Window("t", ui.Button("Go")))
        button = data["children"][0]["props"]
        assert button == {"text": "Go", "variant": "default"}

    def test_handlers_round_trip_by_key(self, backend):
        seen = []

        def save(event):
            seen.append(event.type)

        panel = ui.Window("t", ui.Button("Go", key="go", on_click=save))
        data = ui.to_dict(panel, handlers={"go": {"on_click": save}})
        mount(ui.from_dict(data, handlers={"go": {"on_click": save}}), backend)
        backend.require("go").Click()
        assert seen == ["Clicked"]

    def test_reactive_values_are_inlined(self):
        data = ui.to_dict(ui.Window("t", ui.TextField(value=ui.Value("hello"))))
        assert data["children"][0]["props"]["value"] == "hello"

    def test_reactive_values_can_be_kept(self):
        kept = ui.to_dict(ui.Window("t", ui.TextField(value=ui.Value("hi"))), values=False)
        assert isinstance(kept["children"][0]["props"]["value"], ui.Value)

    def test_json_text_helpers(self, backend):
        text = ui.to_json(ui.Window("t", ui.Label("hi", key_id="l")))
        mount(ui.from_json(text), backend)
        assert backend.text("l") == "hi"

    def test_invalid_json_is_reported(self):
        with pytest.raises(ui.SchemaError, match="invalid JSON"):
            ui.from_json("{oops")

    def test_missing_kind_is_reported(self):
        with pytest.raises(ui.SchemaError, match="string 'kind'"):
            ui.from_dict({"props": {}})

    def test_unknown_widget_lists_alternatives(self):
        with pytest.raises(ui.SchemaError, match="neither a widget nor"):
            ui.from_dict({"kind": "nope"})

    def test_unknown_prop_is_reported(self):
        with pytest.raises(ui.SchemaError, match="no prop"):
            ui.from_dict({"kind": "button", "props": {"lable": "x"}})

    def test_lenient_mode_accepts_unknown_props(self):
        node = ui.from_dict({"kind": "button", "props": {"lable": "x"}}, strict=False)
        assert node.props["lable"] == "x"

    def test_component_from_a_document(self, backend):
        doc = {
            "kind": "window",
            "props": {"title": "C"},
            "children": [{"kind": "test-panel", "props": {"title": "From JSON"}}],
        }
        mount(ui.from_dict(doc), backend)
        assert backend.require("count")._type == "Label"

    def test_raw_node_from_a_document(self, backend):
        doc = {"kind": "window", "children": [{"kind": "raw", "type": "SpinBox"}]}
        mount(ui.from_dict(doc), backend)
        assert "SpinBox" in backend.tree()

    def test_raw_needs_a_type(self):
        with pytest.raises(ui.SchemaError, match="string 'type'"):
            ui.from_dict({"kind": "raw"})

    def test_bad_children_type(self):
        with pytest.raises(ui.SchemaError, match="'children' must be a list"):
            ui.from_dict({"kind": "column", "children": "nope"})

    def test_colour_serialises_as_hex(self):
        data = ui.to_dict(ui.Window("t", ui.ColorPicker("#ff8800")))
        assert data["children"][0]["props"]["value"] == "#ff8800"

    def test_a_document_is_accepted_where_a_node_is(self, backend):
        app = mount(
            ui.Window("t", ui.from_dict({"kind": "label", "props": {"text": "hi", "key_id": "l"}})),
            backend,
        )
        assert app.require("l").element_id == "l"
        assert backend.require("l")._type == "Label"


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


class TestApp:
    def test_backend_selection(self, monkeypatch):
        import builtins

        # Another test module may have left a fake ``resolve`` in builtins.
        monkeypatch.delattr(builtins, "resolve", raising=False)
        assert isinstance(ui.get_backend("mock"), MockBackend)
        with pytest.raises(ui.BackendUnavailable, match="unknown backend"):
            ui.get_backend("nope")
        with pytest.raises(ui.BackendUnavailable):
            ui.get_backend("fusion")

    def test_a_stub_resolve_is_reported_clearly(self):
        class StubResolve:
            pass

        with pytest.raises(ui.BackendUnavailable, match="no Fusion"):
            ui.FusionBackend(resolve=StubResolve())

    def test_backend_instance_is_passed_through(self, backend):
        assert ui.get_backend(backend) is backend

    def test_context_manager_shows_and_closes(self, backend):
        with ui.App(ui.Window("t", key_id="main"), backend=backend) as app:
            assert app.root.shown
        assert app.renderer.root is None

    def test_close_is_idempotent(self, backend):
        app = mount(ui.Window("t"), backend)
        app.close()
        app.close()
        assert app.renderer.root is None

    def test_find_and_require(self, backend):
        app = mount(ui.Window("t", ui.Label("a", key_id="l")), backend)
        assert app.require("l").get("Text") == "a"
        with pytest.raises(ui.ElementError, match="no mounted node"):
            app.require("nope")

    def test_reading_a_native_property(self, backend):
        app = mount(ui.Window("t", ui.Label("a", key_id="l")), backend)
        app.require("l").set("Text", "b")
        assert backend.text("l") == "b"
        app.require("l").call("SetFocus")
        assert backend.require("l").HasFocus()

    def test_update_is_an_alias_for_refresh(self, backend):
        app = mount(ui.Window("t", ui.Label("a", key_id="l")), backend)
        app.update()
        assert backend.text("l") == "a"

    def test_theme_argument(self, backend):
        app = ui.App(ui.Window("t", ui.Label("a", key_id="l")), backend=backend,
                      theme=ui.light_theme)
        app.show()
        assert ui.light_theme.color("bg").hex in backend.require(app.root.id).properties[
            "StyleSheet"
        ]

    def test_mount_helper_does_not_show(self, backend):
        app = ui.mount(ui.Window("t"), backend=backend)
        assert not app.root.shown
