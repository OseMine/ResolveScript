"""Running a Workflow Integration without Resolve.

An integration is a menu entry that opens a window and calls back while you
work. Testing that normally means clicking through Resolve by hand, which is
exactly the thing a test suite exists to avoid. :class:`Harness` runs the real
code against :class:`~ResolveScript.ui.backends.MockBackend` and the project's
own :mod:`ResolveScript.sandbox` fakes, so ``on_launch``, the window and the
callbacks can all be exercised in CI:

    with Harness(INTEGRATION) as h:
        h.launch()
        h.click("render")
        assert h.context.project_name == "Demo Project"

The fakes are the same ones ``resolvescript sandbox`` uses, so a test written
here is a test that transfers to a real session. This is a *different* seam
from :class:`ResolveScript.sandbox.FakeWorkflowIntegration`, which models an
older invented registration API; this one models what Resolve actually does —
bind ``resolve`` and ``project``, then call the handlers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..ui.app import App
from ..ui.backends.mock import MockBackend
from .model import Context, Integration

__all__ = ["Harness", "HarnessError", "harness"]


class HarnessError(Exception):
    """Raised when a harness is driven before it is ready."""


@dataclass
class Harness:
    """An integration mounted on a mock backend, ready to be driven.

    Use it as a context manager: it closes the window and releases the
    subscriptions on the way out, which is the same bookkeeping a real session
    gets.

    :param integration: the integration under test.
    :param resolve: a Resolve object; defaults to the sandbox's mock session.
    :param project: a project; defaults to that session's current project.
    :param mount: set ``False`` to skip mounting the window, for a headless
        integration or a test that only cares about ``on_launch``.
    """

    integration: Integration
    resolve: Any = None
    project: Any = None
    mount: bool = True

    backend: MockBackend = field(init=False, default=None)  # type: ignore[assignment]
    app: App | None = field(init=False, default=None)
    context: Context = field(init=False, default=None)
    launched: bool = field(init=False, default=False)
    exit_code: int = field(init=False, default=0)
    delivered: list[tuple[str, str, bool]] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        if self.resolve is None or self.project is None:
            session, current = self._default_session()
            if self.resolve is None:
                self.resolve = session
            if self.project is None:
                self.project = current
        self.backend = MockBackend()
        self.context = Context.detect(
            self.resolve, self.project, integration=self.integration
        )

    @staticmethod
    def _default_session() -> tuple[Any, Any]:
        from ..sandbox.env import build_default_env

        resolve, _fusion = build_default_env()
        return resolve, resolve.GetProjectManager().GetCurrentProject()

    # -- lifecycle -------------------------------------------------------
    def __enter__(self) -> Harness:
        return self.mount_window() if self.mount else self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def mount_window(self) -> Harness:
        """Build and mount the integration's window on the mock backend."""
        if self.app is not None:
            return self
        window = self.integration.build(self.context)
        if window is None:
            if self.mount:
                raise HarnessError(
                    f"{self.integration.name!r} has no build_ui, so there is no "
                    "window to mount; pass mount=False to test the launch handler"
                )
            return self
        self.app = App(window, backend=self.backend)
        self.app.show()
        return self

    def close(self) -> None:
        """Unmount the window and drop every subscription it held."""
        if self.app is not None:
            self.app.close()
            self.app = None

    # -- driving ---------------------------------------------------------
    def launch(self) -> int:
        """Run ``on_launch``. Returns its exit code.

        The window is not run here even when mounted: the mock event loop has
        nothing to pump until a test says so, so the handler runs and returns.
        """
        self.exit_code = self.integration.launch(self.context)
        self.launched = True
        return self.exit_code

    def trigger(self, name: str) -> Any:
        """Fire a declared callback, as Resolve would."""
        return self.integration.trigger(name, self.context)

    def fire(
        self,
        element_id: str,
        event: str,
        info: Mapping[str, Any] | None = None,
    ) -> bool:
        """Deliver a native event to a mounted element.

        Records the delivery in :attr:`delivered` and returns whether a handler
        was connected — ``False`` almost always means the event name is wrong
        or the node was never wired, and is much easier to spot here than in a
        silently unchanged UI.
        """
        self._require_window()
        connected = self.backend.fire(element_id, event, info)
        self.delivered.append((element_id, event, connected))
        return connected

    def click(self, element_id: str) -> bool:
        """Deliver ``Clicked`` to an element."""
        return self.fire(element_id, "Clicked")

    def tree(self) -> str:
        """The mounted element tree, as text — handy in a failure message."""
        self._require_window()
        return self.backend.tree()

    def element(self, element_id: str) -> Any:
        """The native element behind a mounted node."""
        self._require_window()
        return self.backend.require(element_id)

    def text(self, element_id: str) -> Any:
        """An element's current text value, for assertions."""
        return self.backend.text(element_id)

    def _require_window(self) -> None:
        if self.app is None:
            raise HarnessError(
                "no window is mounted; call mount_window() first, or open the harness"
            )


def harness(integration: Integration, **kwargs: Any) -> Harness:
    """Create a :class:`Harness`. Equivalent to constructing one directly."""
    return Harness(integration, **kwargs)
