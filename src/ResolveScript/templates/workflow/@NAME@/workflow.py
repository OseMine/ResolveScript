"""The @NAME@ Workflow Integration.

This is the file to edit. Everything else — the launcher Resolve runs, the
Electron shell, the plugin manifest — is generated from what is declared here,
so there is exactly one place where the integration is defined.

Try it without Resolve:

    resolvescript workflow build --out dist
    resolvescript workflow install

Then restart Resolve and pick **@NAME@** from **Workspace → Workflow
Integrations**.
"""

from __future__ import annotations

from ResolveScript.ui import (
    Button,
    Column,
    Heading,
    Label,
    Muted,
    PrimaryButton,
    Row,
    TextField,
    Value,
    Window,
)
from ResolveScript.workflow import Context, Integration

__all__ = [
    "INTEGRATION",
    "Context",
    "destination",
    "status",
    "render_job",
    "on_render_start",
    "on_render_stop",
    "screen",
]


# Value is the UI framework's reactive cell. A bound widget writes into it and
# the framework patches the single native property that changed — no rebuild, so
# the caret in the text field stays put while you type.
destination = Value("~/Movies/Delivery")
status = Value("Ready.")


def render_job(context: Context, to: str) -> str:
    """The real work — replace this body with your own.

    :param context: the live :class:`~ResolveScript.workflow.Context`. Read
        ``context.timeline``, ``context.media_pool``, ``context.render_jobs``
        and the rest through it rather than holding on to a project object, so
        the integration keeps working when the user switches projects.
    """
    timeline = context.timeline
    name = timeline.GetName() if timeline is not None else "no timeline"
    return f"Queued {name} -> {to}"


def on_render_start(context: Context) -> str:
    """Resolve calls this when a render starts.

    A real callback: the Electron shell registers it with Resolve, and the
    script artifact reaches the same transition by watching the render job
    list. `resolvescript workflow` wires up whichever artifact you installed.
    """
    return f"Render started in {context.project_name or 'no project'}"


def on_render_stop(context: Context) -> str:
    """Called when a render finishes."""
    return f"Render stopped in {context.project_name or 'no project'}"


def screen(context: Context) -> Window:
    """Build the window Resolve shows.

    Two things are worth noticing. ``context`` is closed over by the click
    handler, so it gets the :class:`~ResolveScript.workflow.Context` rather
    than a UI event — the framework hands handlers an ``Event``, and the screen
    is the natural place to bridge that to the integration's own vocabulary.
    And the framework rebuilds this when a ``Value`` changes, so reading
    ``destination`` below is always current without any manual invalidation.
    """

    def on_render_clicked() -> None:
        status.set(render_job(context, destination.get()))

    return Window(
        title="@NAME@",
        children=[
            Column(
                Heading("@NAME@"),
                Muted(context.project_name or "No project open"),
                Label("Deliver to", key_id="destination-label"),
                TextField(value=destination, key_id="destination"),
                Row(
                    PrimaryButton("Render", key_id="render", on_click=on_render_clicked),
                    Button("Clear", key_id="clear", on_click=lambda: status.set("Ready.")),
                    gap="sm",
                ),
                # A Label binds one-way, through its text argument — it shows
                # the Value but the user never types into it.
                Label(status, key_id="status", variant="muted"),
                gap="md",
                padding="md",
            )
        ],
    )


INTEGRATION = Integration(
    # Change this to your own reverse-DNS id before publishing — it becomes the
    # folder name in Resolve's plugins root, and Resolve keys callbacks on it.
    id="@ID@",
    name="@NAME_LABEL@",
    version="@VERSION@",
    description="@DESCRIPTION@",
    author="@AUTHOR@",
    build_ui=screen,
    callbacks={
        "RenderStart": on_render_start,
        "RenderStop": on_render_stop,
    },
)
