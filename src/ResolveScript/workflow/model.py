"""Declaring a Workflow Integration.

A DaVinci Resolve Workflow Integration is not a script in the usual sense: it is
a module Resolve *scans for*, launches on demand from
``Workspace > Workflow Integrations``, and may call back into while it runs.
This module is the part you write — everything else in
:mod:`ResolveScript.workflow` turns it into the files Resolve expects.

    from ResolveScript.workflow import Integration, Context
    from ResolveScript.ui import Window, Column, Button, run

    def screen(context: Context):
        timeline = context.timeline
        return Window(
            title=f"Deliver — {timeline.GetName() if timeline else 'no timeline'}",
            children=[Column(Button("Render", key_id="go"), gap="md")],
        )

    INTEGRATION = Integration(
        id="com.acme.deliver",
        name="Deliver",
        description="Kick off a delivery render.",
        build_ui=screen,
    )

Every field is optional except ``name``. An :class:`Integration` with no
``build_ui`` is a headless integration, which is a legitimate thing to be: it
just does its work in ``on_launch`` and exits.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..errors import ResolveScriptError

__all__ = ["CALLBACKS", "Context", "Integration", "WorkflowError"]

#: The callbacks Resolve delivers to a Workflow Integration. This list is
#: exhaustive — the documentation names exactly these two, and anything else is
#: rejected at construction time rather than silently never firing.
CALLBACKS: tuple[str, ...] = ("RenderStart", "RenderStop")

_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z0-9][a-z0-9-]*)+$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class WorkflowError(ResolveScriptError):
    """Base error for the Workflow Integration framework."""


def _slug(value: str) -> str:
    return _SLUG_RE.sub("", value.lower())


@dataclass
class Context:
    """Everything an integration is allowed to touch.

    Resolve hands a launched script two globals, ``resolve`` and ``project``.
    :class:`Context` is the typed wrapper around them: it remembers the
    integration that is running, resolves the project when Resolve only supplied
    ``resolve``, and exposes the handful of lookups an integration actually
    needs without swallowing Resolve's own errors.

    Every attribute is a live lookup, so a ``Context`` stays correct after the
    user switches projects — do not cache ``context.timeline``.
    """

    resolve: Any = None
    project: Any = None
    integration: Integration | None = None

    @classmethod
    def detect(cls, resolve: Any = None, project: Any = None, **kwargs: Any) -> Context:
        """Build a context from whatever Resolve has on offer.

        Tries, in order: the arguments, the ``resolve`` global Resolve injects
        into launched scripts, then ``DaVinciResolveScript.scriptapp("Resolve")``.
        The project is only looked up from the project manager when it was not
        supplied, because a launched script is given one directly.
        """
        found = resolve if resolve is not None else _discover_resolve()
        if project is None and found is not None:
            project = _current_project(found)
        return cls(resolve=found, project=project, **kwargs)

    # -- lookups ---------------------------------------------------------
    @property
    def project_manager(self) -> Any:
        return self.resolve.GetProjectManager() if self.resolve is not None else None

    @property
    def media_pool(self) -> Any:
        return self.project.GetMediaPool() if self.project is not None else None

    @property
    def timeline(self) -> Any:
        """The project's current timeline, or ``None``."""
        return self.project.GetCurrentTimeline() if self.project is not None else None

    @property
    def timelines(self) -> list[Any]:
        if self.project is None:
            return []
        return [self.project.GetTimelineByIndex(i) for i in range(self.project.GetTimelineCount())]

    @property
    def render_jobs(self) -> list[Any]:
        """Current render jobs. The basis of the script-side render callbacks."""
        if self.project is None:
            return []
        return list(self.project.GetRenderJobList() or [])

    @property
    def is_open(self) -> bool:
        """Whether a project is actually open."""
        return self.project is not None

    @property
    def project_name(self) -> str:
        if self.project is None:
            return ""
        return self.project.GetName() or ""

    def describe(self) -> dict[str, Any]:
        """A JSON-safe snapshot, handy for logging and for the plugin's UI."""
        return {
            "connected": self.resolve is not None,
            "project": self.project_name,
            "timeline": _name_of(self.timeline),
            "timelines": [_name_of(t) for t in self.timelines],
            "render_jobs": len(self.render_jobs),
        }


@dataclass
class Integration:
    """A Workflow Integration, declared in Python.

    :param name: the label Resolve shows in the Workflow Integrations menu.
    :param id: the reverse-DNS plugin id, also the installed folder name. Must
        match :data:`_ID_RE`; derived from ``vendor`` and ``name`` when omitted.
    :param vendor: the company segment of a derived ``id``.
    :param version: shown in the plugin manifest.
    :param description: shown in the plugin manifest.
    :param author: metadata only.
    :param license: metadata only, defaults to ``MIT``.
    :param on_launch: ``(Context) -> Any``. Runs when the user opens the
        integration. An ``int`` return is used as the exit code.
    :param build_ui: ``(Context) -> Node``. Builds the window. Accepts the
        :mod:`ResolveScript.ui` DSL, a
        :class:`~ResolveScript.ui.components.Component`, or any callable
        returning either — the UI framework resolves all three.
    :param callbacks: ``{name: (Context) -> Any}``, keys restricted to
        :data:`CALLBACKS`.
    :param ui_backend: the UI backend for the built window. ``"auto"`` (the
        default) uses real Fusion when Resolve is reachable and the headless
        mock otherwise.
    :param python: the interpreter the Electron artifact runs this integration
        with. Defaults to the interpreter that is building it.
    :param api_timeout: seconds before the plugin's Resolve API calls time out;
        ``0`` disables the timeout, which is Resolve's own default.
    """

    name: str
    id: str = ""
    vendor: str = "resolvescript"
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    license: str = "MIT"
    on_launch: Callable[[Context], Any] | None = None
    build_ui: Callable[[Context], Any] | None = None
    callbacks: dict[str, Callable[[Context], Any]] = field(default_factory=dict)
    ui_backend: Any = None
    python: str = ""
    api_timeout: int = 0

    def __post_init__(self) -> None:
        self.name = (self.name or "").strip()
        if not self.name:
            raise WorkflowError("an integration needs a name")
        self.id = self.id.strip() or self._derive_id()
        if not _ID_RE.match(self.id):
            raise WorkflowError(
                f"integration id {self.id!r} is not reverse-DNS; use something "
                "like 'com.acme.deliver' (lowercase, dot-separated segments)"
            )
        for key in self.callbacks:
            if key not in CALLBACKS:
                raise WorkflowError(
                    f"{key!r} is not a Workflow Integration callback; "
                    f"Resolve supports {', '.join(CALLBACKS)}"
                )
            if not callable(self.callbacks[key]):
                raise WorkflowError(f"callback {key!r} must be callable")
        if not self.python:
            self.python = sys.executable or "python"

    def _derive_id(self) -> str:
        vendor = _slug(self.vendor) or "resolvescript"
        leaf = _slug(self.name)
        if not leaf:
            raise WorkflowError(
                f"cannot derive a plugin id from name {self.name!r} — pass id= explicitly"
            )
        return f"com.{vendor}.{leaf}"

    # -- identity --------------------------------------------------------
    @property
    def plugin_dir_name(self) -> str:
        """Folder name inside the plugins root — the plugin id."""
        return self.id

    @property
    def script_name(self) -> str:
        """File name of the generated Python launcher."""
        return f"{self.plugin_dir_name}.py"

    @property
    def has_ui(self) -> bool:
        return self.build_ui is not None

    # -- runtime ---------------------------------------------------------
    def context(self, resolve: Any = None, project: Any = None) -> Context:
        """A :class:`Context` bound to this integration."""
        return Context.detect(resolve, project, integration=self)

    def launch(self, context: Context) -> int:
        """Run ``on_launch`` only. Returns the exit code it asked for."""
        if self.on_launch is None:
            return 0
        result = self.on_launch(context)
        return int(result) if isinstance(result, int) else 0

    def trigger(self, name: str, context: Context) -> Any:
        """Invoke a declared callback by name.

        An undeclared name is an error rather than a no-op: a typo in a callback
        name is otherwise invisible until a render silently does nothing.
        """
        handler = self.callbacks.get(name)
        if handler is None:
            declared = ", ".join(sorted(self.callbacks)) or "none"
            raise WorkflowError(
                f"{self.name!r} has no {name!r} callback (declared: {declared})"
            )
        return handler(context)

    def build(self, context: Context) -> Any:
        """Build the UI tree. ``None`` when the integration has no UI."""
        if self.build_ui is None:
            return None
        return self.build_ui(context)

    def as_dict(self) -> dict[str, Any]:
        """Metadata, for manifests and for the plugin's status panel."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "callbacks": sorted(self.callbacks),
            "has_ui": self.has_ui,
        }

    def describe(self) -> list[str]:
        """Human-readable summary lines, for the CLI."""
        meta = self.as_dict()
        return [
            f"{meta['name']} {meta['version']}  ({meta['id']})",
            f"  menu:        Workspace > Workflow Integrations > {meta['name']}",
            f"  callbacks:   {', '.join(meta['callbacks']) or 'none'}",
            f"  interface:   {'UIManager window' if meta['has_ui'] else 'headless'}",
            f"  interpreter: {self.python}",
        ]


def _discover_resolve() -> Any:
    """Find the live Resolve object, the same way the UI backend does."""
    try:
        import builtins

        found = getattr(builtins, "resolve", None)
        if found is not None:
            return found
    except Exception:  # pragma: no cover - builtins always exists
        pass
    try:
        import DaVinciResolveScript as dvr_script  # type: ignore[import-not-found]

        return dvr_script.scriptapp("Resolve")
    except Exception:
        return None


def _current_project(resolve: Any) -> Any:
    manager = getattr(resolve, "GetProjectManager", None)
    if not callable(manager):
        return None
    try:
        return manager().GetCurrentProject()
    except Exception:
        return None


def _name_of(item: Any) -> str:
    getter = getattr(item, "GetName", None)
    if not callable(getter):
        return ""
    try:
        return getter() or ""
    except Exception:
        return ""
