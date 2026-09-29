"""The backend interface the renderer targets.

Everything above this line is pure Python; everything below it talks to a
concrete widget system. The framework ships two implementations:

``FusionBackend``
    Real DaVinci Resolve. Creates elements via ``resolve.Fusion().UIManager``
    and wires events through ``bmd.UIDispatcher``'s ``On`` namespace.

``MockBackend``
    A faithful, headless mirror of the same API — same element names, same
    property names, same ``win.On[id].Event = handler`` event routing. It
    exists so tool UIs can be built and asserted in CI without Resolve
    running, and so a bad widget name fails in a test rather than in front of
    a user.

Because the mock implements this interface faithfully, a passing test suite is
real evidence that a UI is well-formed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from ..errors import BackendError

__all__ = ["Backend", "ElementTypes"]


class ElementTypes:
    """Element names the Fusion UIManager is known to expose.

    Split into ``documented`` (the published reference) and ``qt`` (further Qt
    widgets reachable because the UIManager is Qt-based). The mock uses this to
    reject typos early while still allowing the wider Qt surface.
    """

    DOCUMENTED = frozenset(
        {
            "Window",
            "Dialog",
            "Label",
            "Button",
            "CheckBox",
            "ComboBox",
            "SpinBox",
            "Slider",
            "LineEdit",
            "TextEdit",
            "TabBar",
            "Tree",
            "TreeItem",
            "ColorPicker",
            "Font",
            "Icon",
        }
    )

    LAYOUT = frozenset({"VGroup", "HGroup", "VGap", "HGap"})

    QT = frozenset(
        {
            "ScrollArea",
            "GroupBox",
            "ProgressBar",
            "Splitter",
            "RadioButton",
            "StackedWidget",
            "HLine",
            "VLine",
            "Spacer",
        }
    )

    @classmethod
    def all(cls) -> frozenset[str]:
        return cls.DOCUMENTED | cls.LAYOUT | cls.QT

    @classmethod
    def is_documented(cls, name: str) -> bool:
        return name in cls.DOCUMENTED or name in cls.LAYOUT


class Backend(ABC):
    """Creates and manipulates native widgets for the renderer."""

    #: Short identifier, e.g. ``"fusion"`` or ``"mock"``.
    name: str = "backend"

    # -- construction -----------------------------------------------------
    @abstractmethod
    def create_root(
        self, kind: str, props: Mapping[str, Any], children: Sequence[Any]
    ) -> Any:
        """Create a root window/dialog through the dispatcher."""

    @abstractmethod
    def create_element(
        self, native_type: str, props: Mapping[str, Any], children: Sequence[Any]
    ) -> Any:
        """Create a child element from the element factory."""

    @abstractmethod
    def connect(
        self, root: Any, element_id: str, event: str, handler: Callable[..., Any]
    ) -> None:
        """Route a native event on ``element_id`` to a Python handler."""

    # -- mutation --------------------------------------------------------
    @abstractmethod
    def set_prop(self, element: Any, name: str, value: Any) -> None:
        """Write a native property."""

    @abstractmethod
    def get_prop(self, element: Any, name: str) -> Any:
        """Read a native property."""

    @abstractmethod
    def add_child(self, parent: Any, child: Any) -> None:
        """Append a child element."""

    @abstractmethod
    def remove_child(self, parent: Any, child: Any) -> None:
        """Detach a child element."""

    @abstractmethod
    def children_of(self, element: Any) -> list[Any]:
        """Current child elements, in order."""

    @abstractmethod
    def call(self, element: Any, method: str, *args: Any) -> Any:
        """Invoke a native method such as ``Show`` or ``Click``."""

    # -- lifecycle -------------------------------------------------------
    @abstractmethod
    def show(self, root: Any) -> None:
        """Display a root window."""

    @abstractmethod
    def run_loop(self) -> int:
        """Process events until :meth:`exit_loop` is called."""

    @abstractmethod
    def exit_loop(self, code: int = 0) -> None:
        """Stop the event loop started by :meth:`run_loop`."""

    @abstractmethod
    def destroy(self, element: Any) -> None:
        """Tear down an element and its children."""

    # -- optional capabilities -------------------------------------------
    def create_item(self, kind: str, props: Mapping[str, Any]) -> Any:
        """Create a detached item (e.g. a ``TreeItem``) for later insertion."""
        raise BackendError(f"{self.name} backend cannot create {kind} items")

    def repaint(self, element: Any) -> None:
        """Ask Qt to repaint; a no-op where unnecessary."""
        with_suppress = getattr(element, "Update", None)
        if callable(with_suppress):
            with_suppress()

    def describe(self) -> str:
        return self.name
