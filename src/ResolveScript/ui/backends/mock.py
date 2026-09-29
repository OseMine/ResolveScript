"""A headless mirror of the Fusion UIManager / UIDispatcher API.

The mock deliberately reproduces the *shape* of the real API rather than a
convenient abstraction: elements are created through a ``UIManager`` factory,
roots come from a ``UIDispatcher``, and events are routed via
``window.On[element_id].Event = handler``. A UI that behaves here behaves in
Resolve.

It also *validates*. ``MockUIManager`` rejects element names that do not exist
in the real API, so ``TextArea`` fails in your test suite instead of throwing
silently inside Resolve. Widgets outside the published reference are accepted
but recorded in :attr:`MockBackend.undocumented` so you know what you are
relying on.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

from ..errors import BackendError
from .base import Backend, ElementTypes

__all__ = [
    "MockBackend",
    "MockUIManager",
    "MockUIDispatcher",
    "MockElement",
]


class _EventSlot:
    """``win.On["someId"]["Clicked"] = handler`` / ``win.On.someId.Clicked = fn``."""

    __slots__ = ("_handlers", "_element_id")

    def __init__(self, handlers: dict[tuple[str, str], Callable[..., Any]], element_id: str):
        object.__setattr__(self, "_handlers", handlers)
        object.__setattr__(self, "_element_id", element_id)

    def __setitem__(self, event: str, handler: Callable[..., Any]) -> None:
        self._handlers[(self._element_id, event)] = handler

    def __getitem__(self, event: str) -> Callable[..., Any] | None:
        return self._handlers.get((self._element_id, event))

    def __setattr__(self, event: str, handler: Callable[..., Any]) -> None:
        self._handlers[(self._element_id, event)] = handler

    def __getattr__(self, event: str) -> Callable[..., Any] | None:
        try:
            return self._handlers[(self._element_id, event)]
        except KeyError:
            raise AttributeError(event) from None

    def __repr__(self) -> str:
        bound = sorted(e for (eid, e) in self._handlers if eid == self._element_id)
        return f"<EventSlot {self._element_id!r} events={bound}>"


class _OnNamespace:
    """``win.On`` — the per-element event router of a root window."""

    __slots__ = ("_handlers",)

    def __init__(self, handlers: dict[tuple[str, str], Callable[..., Any]]):
        object.__setattr__(self, "_handlers", handlers)

    def __getitem__(self, element_id: str) -> _EventSlot:
        return _EventSlot(self._handlers, element_id)

    def __getattr__(self, element_id: str) -> _EventSlot:
        return _EventSlot(self._handlers, element_id)

    def __repr__(self) -> str:
        return f"<On handlers={len(self._handlers)}>"


class MockElement:
    """A widget in the fake widget system.

    Property access is dynamic: reading or writing an unknown attribute goes
    through the element's property table, which is exactly how the real
    elements behave.
    """

    def __init__(
        self,
        type_name: str,
        props: Mapping[str, Any] | None = None,
        children: Sequence[MockElement] | None = None,
    ):
        object.__setattr__(self, "_type", type_name)
        object.__setattr__(self, "_props", dict(props or {}))
        object.__setattr__(self, "_children", [])
        object.__setattr__(self, "_parent", None)
        object.__setattr__(self, "_visible", True)
        object.__setattr__(self, "_closed", False)
        object.__setattr__(self, "_repaints", 0)
        for child in children or ():
            self.AddChild(child)

    # -- property table --------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        props = object.__getattribute__(self, "_props")
        if name in props:
            return props[name]
        raise AttributeError(f"{self._type} has no property {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self._props[name] = value

    def __delattr__(self, name: str) -> None:
        self._props.pop(name, None)

    @property
    def properties(self) -> dict[str, Any]:
        """A copy of the property table (for assertions)."""
        return dict(self._props)

    # -- tree ------------------------------------------------------------
    def AddChild(self, child: MockElement) -> None:
        if child._parent is not None:
            child._parent.RemoveChild(child)
        self._children.append(child)
        child._parent = self

    def RemoveChild(self, child: MockElement) -> None:
        if child in self._children:
            self._children.remove(child)
            child._parent = None

    def GetChildren(self) -> list[MockElement]:
        return list(self._children)

    def SetParent(self, parent: MockElement) -> None:
        if self._parent is not None:
            self._parent.RemoveChild(self)
        if parent is not None:
            parent.AddChild(self)

    def GetParent(self) -> MockElement | None:
        return self._parent

    def Find(self, element_id: str) -> MockElement | None:
        return self.FindWindow(element_id)

    def FindWindow(self, element_id: str) -> MockElement | None:
        if self._props.get("ID") == element_id:
            return self
        for child in self._children:
            found = child.FindWindow(element_id)
            if found is not None:
                return found
        return None

    def GetItems(self) -> dict[str, MockElement]:
        found: dict[str, MockElement] = {}
        self._collect(found)
        return found

    def _collect(self, out: dict[str, MockElement]) -> None:
        element_id = self._props.get("ID")
        if isinstance(element_id, str):
            out[element_id] = self
        for child in self._children:
            child._collect(out)

    def AddTopLevelItem(self, item: Any) -> Any:
        return self.AddChild(item)

    def AddTopLevelItems(self, items: Sequence[Any]) -> None:
        for item in items:
            self.AddTopLevelItem(item)

    def SetHeaderLabels(self, labels: Sequence[str]) -> None:
        self._props["HeaderLabels"] = list(labels)
        self._props["ColumnCount"] = len(labels)

    def TopLevelItemCount(self) -> int:
        return len(self._children)

    def Clear(self) -> None:
        for child in list(self._children):
            self.RemoveChild(child)

    # -- lifecycle -------------------------------------------------------
    def Show(self) -> None:
        object.__setattr__(self, "_visible", True)

    def Hide(self) -> None:
        object.__setattr__(self, "_visible", False)

    def Close(self) -> None:
        object.__setattr__(self, "_closed", True)
        object.__setattr__(self, "_visible", False)

    def Update(self) -> None:
        object.__setattr__(self, "_repaints", self._repaints + 1)

    def Repaint(self) -> None:
        self.Update()

    def RecalcLayout(self) -> None:
        self.Update()

    def SetFocus(self, reason: str = "OtherFocusReason") -> None:
        self._props["HasFocus"] = True

    def HasFocus(self) -> bool:
        return bool(self._props.get("HasFocus", False))

    def Size(self) -> list[int]:
        geometry = self._props.get("Geometry") or [0, 0, 400, 300]
        return [geometry[2], geometry[3]]

    def Pos(self) -> list[int]:
        geometry = self._props.get("Geometry") or [0, 0, 400, 300]
        return [geometry[0], geometry[1]]

    def Resize(self, size: Sequence[int]) -> None:
        geometry = list(self._props.get("Geometry") or [0, 0, 400, 300])
        geometry[2], geometry[3] = int(size[0]), int(size[1])
        self._props["Geometry"] = geometry

    def Move(self, point: Sequence[int]) -> None:
        geometry = list(self._props.get("Geometry") or [0, 0, 400, 300])
        geometry[0], geometry[1] = int(point[0]), int(point[1])
        self._props["Geometry"] = geometry

    def IsActiveWindow(self) -> bool:
        return bool(self._props.get("IsActive", True))

    def QueueEvent(self, name: str, info: Mapping[str, Any] | None = None) -> None:
        """Directly invoke this element's registered handler, if any."""
        element_id = self._props.get("ID")
        if not isinstance(element_id, str):
            return
        handler = self._backend_handlers.get((element_id, name))  # type: ignore[attr-defined]
        if handler is not None:
            handler(dict(info or {}))

    # -- widget-specific methods ----------------------------------------
    def Click(self) -> None:
        """Simulate a user click: fire the Clicked handler and flip Checked."""
        if self._props.get("Checkable"):
            self._props["Checked"] = not self._props.get("Checked", False)
        self.QueueEvent("Clicked", {"sender": self})

    def Toggle(self) -> None:
        self._props["Checked"] = not self._props.get("Checked", False)
        self.QueueEvent("Toggled", {"Checked": self._props["Checked"], "sender": self})

    def AddItem(self, text: str) -> int:
        items = self._props.setdefault("ItemText", [])
        items.append(text)
        self._props["Count"] = len(items)
        return len(items) - 1

    def AddItems(self, texts: Sequence[str]) -> None:
        for text in texts:
            self.AddItem(text)

    def AddTab(self, text: str) -> int:
        items = self._props.setdefault("TabText", [])
        items.append(text)
        self._props["Count"] = len(items)
        return len(items) - 1

    def RemoveTab(self, index: int) -> None:
        items = self._props.get("TabText") or []
        if 0 <= index < len(items):
            items.pop(index)
            self._props["Count"] = len(items)

    def SetRange(self, minimum: float, maximum: float) -> None:
        self._props["Minimum"] = minimum
        self._props["Maximum"] = maximum

    def __repr__(self) -> str:
        element_id = self._props.get("ID")
        label = f" id={element_id!r}" if element_id else ""
        return f"<Mock{self._type}{label} children={len(self._children)}>"


class MockUIManager:
    """Stand-in for ``fusion.UIManager``: a factory of elements by name."""

    def __init__(self, backend: MockBackend, strict: bool = True):
        object.__setattr__(self, "_backend", backend)
        object.__setattr__(self, "_strict", strict)

    def __getattr__(self, type_name: str) -> Callable[..., MockElement]:
        if type_name.startswith("_"):
            raise AttributeError(type_name)
        allowed = ElementTypes.all()
        if type_name not in allowed:
            if self._strict:
                raise BackendError(
                    f"UIManager has no element type {type_name!r}. "
                    f"Known types: {sorted(allowed)}. "
                    "Pass strict=False to allow undocumented Qt widgets."
                )
            self._backend.undocumented.add(type_name)

        def factory(
            props: Mapping[str, Any] | None = None, children: Sequence[MockElement] | None = None
        ) -> MockElement:
            return self._backend._register(
                MockElement(type_name, props or {}, children or ()), type_name
            )

        return factory

    def __repr__(self) -> str:
        return "<MockUIManager>"


class MockUIDispatcher:
    """Stand-in for ``bmd.UIDispatcher``: creates roots and owns the event loop."""

    def __init__(self, ui: MockUIManager, backend: MockBackend):
        object.__setattr__(self, "_ui", ui)
        object.__setattr__(self, "_backend", backend)

    def _make(self, type_name: str, props: Mapping[str, Any] | None, children: Any) -> MockElement:
        payload = list(children) if isinstance(children, (list, tuple)) else (
            [] if children is None else [children]
        )
        element = MockElement(type_name, props or {}, payload)
        element._backend_handlers = self._backend.handlers  # type: ignore[attr-defined]
        element.On = _OnNamespace(self._backend.handlers)  # type: ignore[attr-defined]
        return self._backend._register(element, type_name)

    def AddWindow(self, props: Mapping[str, Any] | None = None, children: Any = None) -> MockElement:
        return self._make("Window", props, children)

    def AddDialog(self, props: Mapping[str, Any] | None = None, children: Any = None) -> MockElement:
        return self._make("Dialog", props, children)

    def FindWindow(self, element_id: str) -> MockElement | None:
        for root in self._backend.roots:
            found = root.FindWindow(element_id)
            if found is not None:
                return found
        return None

    def FindWindows(self, element_id: str) -> list[MockElement]:
        return [root for root in self._backend.roots if root.FindWindow(element_id) is not None]

    def QueueEvent(
        self, element: MockElement, event: str, info: Mapping[str, Any] | None = None
    ) -> None:
        element.QueueEvent(event, info)

    def RunLoop(self) -> int:
        return self._backend._run_loop()

    def ExitLoop(self, code: int = 0) -> None:
        self._backend._exit_loop(code)

    def __repr__(self) -> str:
        return "<MockUIDispatcher>"


class MockBackend(Backend):
    """A :class:`Backend` that builds an inspectable fake widget tree.

    :param strict: reject element names outside the known API (default on).
    """

    name = "mock"

    def __init__(self, strict: bool = True):
        self.strict = strict
        self.handlers: dict[tuple[str, str], Callable[..., Any]] = {}
        self.roots: list[MockElement] = []
        self.elements: list[MockElement] = []
        self.undocumented: set[str] = set()
        self.ui = MockUIManager(self, strict=strict)
        self.dispatcher = MockUIDispatcher(self.ui, self)
        self._loop_code: int | None = None
        self._loop_runs = 0

    # -- bookkeeping -----------------------------------------------------
    def _register(self, element: MockElement, type_name: str) -> MockElement:
        if not ElementTypes.is_documented(type_name) and type_name not in ElementTypes.LAYOUT:
            self.undocumented.add(type_name)
        element._backend_handlers = self.handlers  # type: ignore[attr-defined]
        self.elements.append(element)
        return element

    # -- Backend interface -----------------------------------------------
    def create_root(
        self, kind: str, props: Mapping[str, Any], children: Sequence[Any]
    ) -> MockElement:
        builder = self.dispatcher.AddDialog if kind == "dialog" else self.dispatcher.AddWindow
        element = builder(dict(props), list(children))
        self.roots.append(element)
        return element

    def create_element(
        self, native_type: str, props: Mapping[str, Any], children: Sequence[Any]
    ) -> MockElement:
        factory = getattr(self.ui, native_type)
        return factory(dict(props), list(children))

    def connect(
        self, root: Any, element_id: str, event: str, handler: Callable[..., Any]
    ) -> None:
        self.handlers[(element_id, event)] = handler
        if isinstance(root, MockElement):
            root.On[element_id][event] = handler

    def set_prop(self, element: MockElement, name: str, value: Any) -> None:
        if name == "BackgroundColor" and isinstance(value, (list, tuple)):
            element._props[name] = list(value)
        else:
            setattr(element, name, value)

    def get_prop(self, element: MockElement, name: str) -> Any:
        return getattr(element, name)

    def add_child(self, parent: MockElement, child: MockElement) -> None:
        parent.AddChild(child)

    def remove_child(self, parent: MockElement, child: MockElement) -> None:
        parent.RemoveChild(child)

    def children_of(self, element: MockElement) -> list[MockElement]:
        return element.GetChildren()

    def call(self, element: MockElement, method: str, *args: Any) -> Any:
        handler = getattr(element, method, None)
        if not callable(handler):
            raise BackendError(f"{element._type} has no method {method!r}")
        return handler(*args)

    def show(self, root: MockElement) -> None:
        root.Show()

    def run_loop(self) -> int:
        return self.dispatcher.RunLoop()

    def exit_loop(self, code: int = 0) -> None:
        self.dispatcher.ExitLoop(code)

    def destroy(self, element: MockElement) -> None:
        if element in self.roots:
            self.roots.remove(element)
        if element in self.elements:
            self.elements.remove(element)
        parent = element.GetParent()
        if parent is not None:
            parent.RemoveChild(element)

    def create_item(self, kind: str, props: Mapping[str, Any]) -> MockElement:
        return self._register(MockElement(kind, dict(props)), kind)

    # -- test helpers ----------------------------------------------------
    def _run_loop(self) -> int:
        self._loop_runs += 1
        # A real dispatcher blocks. Headless there is nothing to wait for, so
        # return immediately; tests drive interaction with ``fire``.
        return 0

    def _exit_loop(self, code: int) -> None:
        self._loop_code = code

    @property
    def exit_code(self) -> int | None:
        """The code passed to the most recent :meth:`exit_loop`."""
        return self._loop_code

    def find(self, element_id: str) -> MockElement | None:
        """Find any element by its ``ID``."""
        for root in self.roots:
            found = root.FindWindow(element_id)
            if found is not None:
                return found
        return None

    def require(self, element_id: str) -> MockElement:
        """Find an element by ``ID``, raising if absent — handy in tests."""
        found = self.find(element_id)
        if found is None:
            raise BackendError(f"no element with ID {element_id!r}")
        return found

    def fire(
        self, element_id: str, event: str, info: Mapping[str, Any] | None = None
    ) -> bool:
        """Deliver a native event, as Resolve would.

        Returns ``True`` if a handler was registered — a falsey result usually
        means the event name is wrong or the handler was never connected.
        """
        handler = self.handlers.get((element_id, event))
        if handler is None:
            return False
        element = self.find(element_id)
        payload: dict[str, Any] = {"sender": element, "ID": element_id}
        if element is not None:
            payload.update(element.properties)
        payload.update(info or {})
        handler(payload)
        return True

    def type_into(self, element_id: str, text: str, event: str = "TextChanged") -> bool:
        """Simulate typing: set ``Text`` then deliver the change event.

        The two-way binding path in the renderer only fires from a real native
        event, so tests need to raise both halves to be faithful.
        """
        self.require(element_id)._props["Text"] = text
        return self.fire(element_id, event, {"Text": text})

    def select_index(self, element_id: str, index: int, event: str = "CurrentIndexChanged") -> bool:
        """Simulate picking entry ``index`` of a combo box or tab bar."""
        self.require(element_id)._props["CurrentIndex"] = index
        return self.fire(element_id, event, {"CurrentIndex": index})

    def text(self, element_id: str) -> Any:
        """Current value of an element, for assertions."""
        return self.require(element_id).properties.get("Text")

    def rows(self, element_id: str) -> list[list[str]]:
        """Cell contents of a tree/list element's top-level rows."""
        return [
            list(child.properties.get("Text") or [])
            for child in self.require(element_id).GetChildren()
        ]

    def row_elements(self, element_id: str) -> list[MockElement]:
        """The ``TreeItem`` elements of a tree/list — handy for event payloads."""
        return list(self.require(element_id).GetChildren())

    def children_ids(self, element_id: str) -> list[str]:
        """The ``ID``s of an element's children, in order."""
        return [
            str(child.properties.get("ID"))
            for child in self.require(element_id).GetChildren()
        ]

    def tree(self, element: Any | None = None, depth: int = 0) -> str:
        """A readable dump of the element tree — useful in test failures."""
        if element is None:
            return "\n".join(self.tree(root) for root in self.roots)
        label = element.properties.get("ID") or element.properties.get("Text") or ""
        lines = ["  " * depth + f"{element._type}({label!r})"]
        for child in element.GetChildren():
            lines.append(self.tree(child, depth + 1))
        return "\n".join(lines)

    def describe(self) -> str:
        return f"mock (strict={self.strict}, elements={len(self.elements)})"
