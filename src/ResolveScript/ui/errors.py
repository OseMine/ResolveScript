"""Exceptions raised by the ResolveScript UI framework.

Everything derives from :class:`UIError` so a script can wrap a whole UI in a
single ``except`` clause, while still letting callers distinguish the failure
modes that actually need different handling.
"""

from __future__ import annotations


class UIError(Exception):
    """Base class for all UI framework errors."""


class ElementError(UIError):
    """An element could not be built, or was used incorrectly.

    Raised for unknown widget kinds, invalid prop names, duplicate keys and
    structural problems in a node tree.
    """


class BackendError(UIError):
    """A backend rejected an operation."""


class BackendUnavailable(BackendError):
    """The requested backend cannot be used in this environment.

    Typically raised when the Fusion backend is requested but DaVinci Resolve
    is not reachable from the current interpreter.
    """


class BindingError(UIError):
    """A reactive binding is malformed or cannot be applied."""


class SchemaError(UIError):
    """A declarative dict/JSON document could not be interpreted."""
