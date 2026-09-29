"""Smoke tests — the real integration, driven headlessly.

Every test here runs the integration exactly as Resolve would, against the mock
backend and the mock Resolve API. There is no Resolve and no display.
"""

from __future__ import annotations

import pytest

import @NAME@
from ResolveScript.ui import walk
from ResolveScript.workflow import (
    CALLBACKS,
    Integration,
    ScriptOptions,
    build,
    harness,
    install,
    list_installed,
    uninstall,
)

INTEGRATION = @NAME@.INTEGRATION


def test_metadata() -> None:
    assert INTEGRATION.name == "@NAME_LABEL@"
    assert INTEGRATION.id == "@ID@"
    assert INTEGRATION.version == "@VERSION@"
    assert INTEGRATION.has_ui is True


def test_callbacks_are_the_ones_resolve_sends() -> None:
    """Resolve documents exactly two. Anything else would never fire."""
    assert set(INTEGRATION.callbacks) == set(CALLBACKS)


def test_window_opens_and_renders() -> None:
    with harness(INTEGRATION) as h:
        assert h.context.project_name  # the mock session has a project open
        tree = h.tree()
        assert "Window" in tree
        assert "destination" in tree  # the destination field is on screen


def test_the_render_button_reaches_the_real_work() -> None:
    with harness(INTEGRATION) as h:
        @NAME@.destination.set("~/Out")
        @NAME@.status.set("Ready.")
        assert h.click("render") is True
        # start() writes its result into the bound status Value, so the click
        # landing proves the binding, the handler and the context are all
        # connected.
        assert @NAME@.status.get() == "Queued Main Timeline -> ~/Out"
        assert h.text("status") == "Queued Main Timeline -> ~/Out"


def test_callbacks_run_with_a_live_context() -> None:
    with harness(INTEGRATION) as h:
        assert h.trigger("RenderStart")
        assert h.trigger("RenderStop")


def test_an_undeclared_callback_raises() -> None:
    """A typo in a callback name must not look like a callback that never fires."""
    with harness(INTEGRATION) as h, pytest.raises(Exception, match="RenderNope"):
        h.trigger("RenderNope")


def test_a_headless_integration_needs_no_window() -> None:
    headless = Integration(
        id="com.example.headless", name="Headless", on_launch=lambda ctx: 3
    )
    with harness(headless, mount=False) as h:
        assert h.launch() == 3  # the int return is the exit code
        with pytest.raises(Exception, match="has no 'RenderStart' callback"):
            h.trigger("RenderStart")


def test_build_writes_the_files_resolve_loads(tmp_path) -> None:
    options = ScriptOptions("@NAME@.workflow", project_root=".")
    result = build(INTEGRATION, tmp_path, options=options)

    launcher = tmp_path / f"{INTEGRATION.id}.py"
    plugin = tmp_path / INTEGRATION.id
    assert launcher.is_file()
    assert (plugin / "manifest.xml").is_file()
    assert (plugin / "package.json").is_file()
    assert (plugin / "main.js").is_file()
    assert result.files

    # The launcher is what Resolve executes, so it has to be valid Python.
    compile(launcher.read_text(encoding="utf-8"), str(launcher), "exec")

    # manifest.xml is what Resolve reads to build the menu entry.
    manifest = (plugin / "manifest.xml").read_text(encoding="utf-8")
    assert f"<Id>{INTEGRATION.id}</Id>" in manifest
    assert "<FilePath>main.js</FilePath>" in manifest


def test_install_then_uninstall(tmp_path) -> None:
    options = ScriptOptions("@NAME@.workflow", project_root=".")
    install(INTEGRATION, tmp_path, options=options)
    assert INTEGRATION.id in list_installed(tmp_path)

    removed = uninstall(INTEGRATION, tmp_path)
    assert removed
    assert INTEGRATION.id not in list_installed(tmp_path)
    assert not (tmp_path / INTEGRATION.id).exists()


def test_the_window_is_built_from_the_framework_dsl() -> None:
    """The screen is an ordinary UI tree, so it composes and inspects like one."""
    window = INTEGRATION.build(INTEGRATION.context())
    # Window/Column/Button are factories, so the node's kind is what identifies it.
    assert window.kind == "window"
    body = window.children[0]
    assert body.kind == "column"
    assert body.children[0].kind in {"label", "title"}
    assert "button" in {node.kind for node in walk(window)}
