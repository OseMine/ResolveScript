"""Plugin-specific errors."""

from __future__ import annotations

from ..errors import ResolveScriptError


class PluginError(ResolveScriptError):
    """A plugin could not be loaded or installed."""
    pass
