"""Reactive primitives that keep the screen in sync with Python state.

The framework uses a small pull-based reactivity system in the spirit of
SolidJS/Svelte rather than a virtual-DOM re-render. A :class:`Value` notifies
its subscribers when it changes; the renderer subscribes once per bound prop
and then writes *only* that native property. Nothing else on screen is
touched, so focus, scroll position and cursor placement survive updates.

Three primitives are enough to describe a tool UI:

``Value``
    A mutable cell. ``.get()`` reads it, ``.set()`` writes it, ``.update()``
    transforms it. Assigning an unchanged value is a no-op, which keeps
    feedback loops from spinning.
``Computed``
    A read-only value derived from other values. It re-evaluates lazily, and
    only re-runs if something it actually read has changed.
``batch()``
    Groups several writes so subscribers are notified once at the end instead
    of after every assignment.

Anywhere a ``Value`` or ``Computed`` is passed as a prop, the renderer binds it
automatically::

    name = Value("Untitled")

    Column(
        TextField(value=name),      # two-way: typing writes back to ``name``
        Label(text=lambda: ...),    # one-way: re-reads on every change
    )
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")

__all__ = [
    "Subscription",
    "Value",
    "Computed",
    "batch",
    "batched",
    "watch",
    "value",
    "computed",
    "changed",
    "is_reactive",
]


def _changed(old: Any, new: Any) -> bool:
    """Compare two values, tolerating types with unusual ``__eq__``.

    Some objects (notably numpy arrays and Qt objects) return a non-boolean
    from ``==``. Those fall back to identity, which is conservative but never
    reports a spurious change.
    """
    if old is new:
        return False
    try:
        result = old != new
    except Exception:  # pragma: no cover - exotic __ne__
        return True
    if result is True or result is False:
        return result
    return True


class Subscription:
    """Handle returned by :meth:`Value.subscribe`. Unsubscribes on ``unsubscribe()``.

    The handle is optional to keep — ``watch(...)`` is a fire-and-forget call
    site — but dropping it must not cancel anything. Lifetime is therefore
    explicit: whoever needs to stop a subscription later stores this object and
    unsubscribes it, and the renderer releases every handle it takes when a node
    is torn down.
    """

    __slots__ = ("_source", "_fn", "_active")

    def __init__(self, source: Any, fn: Callable[[Any], Any]):
        self._source = source
        self._fn = fn
        self._active = True

    def unsubscribe(self) -> None:
        if not self._active:
            return
        self._active = False
        subs = getattr(self._source, "_subscribers", None)
        if subs is not None and self._fn in subs:
            subs.remove(self._fn)

    # Allow ``with source.subscribe(fn): ...`` for scoped handlers.
    def __enter__(self) -> Subscription:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.unsubscribe()

    @property
    def active(self) -> bool:
        return self._active

    def __repr__(self) -> str:
        state = "active" if self._active else "closed"
        return f"<Subscription {state}>"


class _Observer:
    """Collects the values read during one :class:`Computed` evaluation."""

    __slots__ = ("deps",)

    def __init__(self) -> None:
        self.deps: list[Any] = []


# Stack of active observers. A module-level list is enough: evaluation is
# synchronous and never interleaves across threads in this framework.
_observers: list[_Observer] = []
_observer_lock = threading.Lock()


def _track(source: Any) -> None:
    if _observers:
        observer = _observers[-1]
        if source not in observer.deps:
            observer.deps.append(source)


class Value(Generic[T]):
    """A mutable reactive cell.

    >>> n = Value(0)
    >>> seen = []
    >>> n.subscribe(seen.append)
    <Subscription active>
    >>> n.set(5)
    True
    >>> seen
    [5]
    """

    __slots__ = ("_value", "_subscribers", "_version", "_name", "_lock")

    def __init__(self, initial: T, name: str | None = None):
        self._value = initial
        self._subscribers: list[Callable[[Any], Any]] = []
        self._version = 0
        self._name = name
        self._lock = threading.RLock()

    # -- reading ---------------------------------------------------------
    def get(self) -> T:
        """Return the current value, registering a dependency if evaluated."""
        _track(self)
        return self._value

    @property
    def version(self) -> int:
        """How many times this value has actually changed."""
        return self._version

    @property
    def name(self) -> str | None:
        return self._name

    # -- writing ---------------------------------------------------------
    def set(self, new_value: T) -> bool:
        """Write a new value. Returns ``True`` if it changed anything."""
        with self._lock:
            if not _changed(self._value, new_value):
                return False
            self._value = new_value
            self._version += 1
            _notify(self, new_value)
        return True

    def update(self, fn: Callable[[T], T]) -> bool:
        """Derive the next value from the current one."""
        return self.set(fn(self.get()))

    # -- observing -------------------------------------------------------
    def subscribe(
        self, fn: Callable[[Any], Any], immediate: bool = False
    ) -> Subscription:
        """Call ``fn(new_value)`` whenever the value changes.

        With ``immediate=True`` the handler is also called once up front,
        which is what the renderer relies on for the initial paint. Keep the
        returned handle to unsubscribe; discarding it leaves the subscription
        running.
        """
        sub = Subscription(self, fn)
        self._subscribers.append(fn)
        if immediate:
            fn(self._value)
        return sub

    def bind_to(self, fn: Callable[[Any], Any]) -> Subscription:
        """Call ``fn(new_value)`` on every change (not initially)."""
        return self.subscribe(fn)

    def __repr__(self) -> str:
        label = f" {self._name!r}" if self._name else ""
        return f"Value({self._value!r}{label})"


def _notify(source: Any, new_value: Any) -> None:
    """Fan a change out to subscribers, deferring while a batch is active."""
    if _batch_depth:
        _pending.setdefault(id(source), source)
        return
    for fn in list(source._subscribers):
        try:
            fn(new_value)
        except Exception:
            # One broken handler must not stop the rest of the UI from
            # updating, and Resolve gives us nowhere useful to log to.
            import traceback

            traceback.print_exc()


class Computed(Generic[T]):
    """A value derived from other reactive values, re-evaluated on demand.

    Dependencies are discovered automatically: any :class:`Value` read while
    the compute function runs is remembered and re-checked next time.
    """

    __slots__ = ("_fn", "_value", "_dirty", "_deps", "_subscribers", "_version", "_name")

    def __init__(self, fn: Callable[[], T], name: str | None = None, initial: T | None = None):
        self._fn = fn
        self._value: Any = initial
        self._dirty = True
        self._deps: list[Any] = []
        self._subscribers: list[Callable[[Any], Any]] = []
        self._version = 0
        self._name = name
        if not self._dirty:  # pragma: no cover - only via initial
            self._dirty = False

    def get(self) -> T:
        _track(self)
        if self._dirty:
            self._recompute()
        return self._value

    def _recompute(self) -> None:
        observer = _Observer()
        with _observer_lock:
            _observers.append(observer)
            try:
                new_value = self._fn()
            finally:
                _observers.pop()

        # Swap dependencies before notifying, so a handler that re-enters
        # ``get()`` sees a consistent graph.
        for dep in self._deps:
            with contextlib.suppress(Exception):
                dep._subscribers.remove(self._on_dep_change)
        self._deps = list(observer.deps)
        for dep in self._deps:
            dep._subscribers.append(self._on_dep_change)

        if _changed(self._value, new_value):
            self._version += 1
        self._value = new_value
        self._dirty = False

    def _on_dep_change(self, _new_value: Any = None) -> None:
        if self._dirty:
            return
        self._dirty = True
        # Evaluate eagerly so subscribers see the fresh value, and only
        # notify if it actually differs.
        previous = self._value
        self._recompute()
        if _changed(previous, self._value):
            _notify(self, self._value)

    def subscribe(
        self, fn: Callable[[Any], Any], immediate: bool = False
    ) -> Subscription:
        sub = Subscription(self, fn)
        self._subscribers.append(fn)
        self.get()  # establish dependencies
        if immediate:
            fn(self._value)
        return sub

    @property
    def version(self) -> int:
        return self._version

    @property
    def name(self) -> str | None:
        return self._name

    def __repr__(self) -> str:
        label = f" {self._name!r}" if self._name else ""
        return f"Computed({self._value!r}{label})"


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------

_batch_depth = 0
_pending: dict[int, Any] = {}


@contextlib.contextmanager
def batch() -> Iterator[None]:
    """Collapse several writes into a single notification round.

    Inside the block each source is recorded once. On exit every distinct
    source is notified with its current value, so a component that depends on
    several values still refreshes exactly once.
    """
    global _batch_depth
    _batch_depth += 1
    try:
        yield
    finally:
        _batch_depth -= 1
        if _batch_depth == 0:
            sources = list(_pending.values())
            _pending.clear()
            for source in sources:
                with contextlib.suppress(Exception):
                    source.get()  # let Computed settle before notifying
                _notify(source, source._value)


def batched() -> Any:
    """Alias for :func:`batch` (reads better inside ``with``)."""
    return batch()


def watch(source: Any, fn: Callable[[Any], Any], immediate: bool = False) -> Subscription:
    """Run ``fn(new_value)`` whenever ``source`` (Value or Computed) changes."""
    return source.subscribe(fn, immediate=immediate)


def value(initial: T, name: str | None = None) -> Value[T]:
    """Create a :class:`Value`."""
    return Value(initial, name=name)


def computed(fn: Callable[[], T], name: str | None = None) -> Computed[T]:
    """Create a :class:`Computed`."""
    return Computed(fn, name=name)


def is_reactive(obj: Any) -> bool:
    """Whether ``obj`` is a :class:`Value` or :class:`Computed`."""
    return isinstance(obj, (Value, Computed))


#: Public alias, so callers do not have to reach for the private name.
changed = _changed
