"""ResolveScript Workflow — building DaVinci Resolve Workflow Integrations.

A Workflow Integration is not a script you run; it is a module Resolve *scans
for* on startup, lists under ``Workspace > Workflow Integrations``, and launches
on demand with ``resolve`` and ``project`` already bound. This package is the
part you write, plus the tooling that turns it into the files Resolve expects.

Two artifacts
-------------

**The script** — one Python file, portable. Resolve launches it, and
:mod:`ResolveScript.ui` draws its window with Resolve's own Qt UIManager. No
npm, no Electron, and it works on Linux, where Resolve does not load plugins at
all.

**The plugin** — an Electron app that Resolve launches as its main process. It
is the only way to reach Resolve's JavaScript API and the only way Resolve
delivers callbacks, but it is Windows/macOS Studio only. The generated
``main.js`` starts the script and talks to it, so the plugin is a shell and the
script is the brain — you write the Python either way.

Declaring one
-------------

::

    from ResolveScript.workflow import Integration, Context
    from ResolveScript.ui import Window, Column, Heading, Button, Value

    def screen(context: Context):
        name = Value(context.project_name or "no project")
        return Window(
            title="Deliver",
            children=[
                Column(
                    Heading("Deliver"),
                    Button("Render", key_id="render", on_click=lambda: render(name())),
                    gap="md", padding="md",
                )
            ],
        )

    def render(destination: str) -> None:
        ...

    INTEGRATION = Integration(
        id="com.acme.deliver",
        name="Deliver",
        version="1.0.0",
        description="Kick off a delivery render.",
        build_ui=screen,
        callbacks={"RenderStart": lambda ctx: log(ctx), "RenderStop": lambda ctx: log(ctx)},
    )

Shipping it
------------

::

    resolvescript workflow build            # write the files into ./dist
    resolvescript workflow install          # into Resolve's plugins root
    resolvescript workflow list             # what is installed
    resolvescript workflow uninstall com.acme.deliver

or from Python::

    from ResolveScript.workflow import install, ScriptOptions, harness

    install(INTEGRATION, options=ScriptOptions("my_pkg.integration"))

Where it goes
-------------

Resolve scans a *Workflow Integration Plugins* directory, which is not the
Scripts root — see :mod:`ResolveScript.workflow.paths`. Scripts land directly
in it; plugins land in a subdirectory named after the plugin id. Resolve reads
this directory once, on launch, so it has to be restarted to see a change.

Testing without Resolve
-----------------------

:class:`~ResolveScript.workflow.testing.Harness` mounts the real window on the
UI framework's mock backend and runs the real handlers::

    with harness(INTEGRATION) as h:
        h.launch()
        h.click("render")
        assert h.delivered[-1] == ("render", "Clicked", True)
"""

from __future__ import annotations

from .bridge import ACTIONS, Bridge, callback_cli, dumps, loads, plain, serve
from .build import (
    BuildResult,
    build,
    describe_installed,
    install,
    install_plugin,
    install_script,
    list_installed,
    render,
    uninstall,
)
from .model import CALLBACKS, Context, Integration, WorkflowError
from .paths import (
    PLUGINS_DIR_NAME,
    WorkflowPathError,
    candidates,
    default_plugins_root,
    developer_examples,
    native_module_source,
    plugins_root,
    supported,
)
from .plugin import ELECTRON_VERSION, PLUGIN_FILES, render_plugin
from .runtime import main, run_integration, run_ui
from .script import ScriptOptions, render_script
from .testing import Harness, HarnessError, harness

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # -- declaring -------------------------------------------------------
    "Integration",
    "Context",
    "CALLBACKS",
    "WorkflowError",
    # -- building --------------------------------------------------------
    "render",
    "build",
    "install",
    "install_script",
    "install_plugin",
    "uninstall",
    "list_installed",
    "describe_installed",
    "BuildResult",
    "ScriptOptions",
    "render_script",
    # -- the Electron shell ----------------------------------------------
    "render_plugin",
    "PLUGIN_FILES",
    "ELECTRON_VERSION",
    # -- paths -----------------------------------------------------------
    "plugins_root",
    "default_plugins_root",
    "candidates",
    "supported",
    "developer_examples",
    "native_module_source",
    "PLUGINS_DIR_NAME",
    "WorkflowPathError",
    # -- running ---------------------------------------------------------
    "main",
    "run_integration",
    "run_ui",
    # -- the bridge ------------------------------------------------------
    "Bridge",
    "serve",
    "callback_cli",
    "dumps",
    "loads",
    "plain",
    "ACTIONS",
    # -- testing ---------------------------------------------------------
    "Harness",
    "HarnessError",
    "harness",
]
