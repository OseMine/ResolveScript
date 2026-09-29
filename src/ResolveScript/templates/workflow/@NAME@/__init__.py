"""@NAME@ — a DaVinci Resolve Workflow Integration.

Declare the integration once; ResolveScript turns it into the files Resolve
actually loads, and drives the same code in tests without a running Resolve.
"""

from __future__ import annotations

__version__ = "@VERSION@"
__author__ = "@AUTHOR@"

from .workflow import INTEGRATION, Context, destination, screen, status

__all__ = [
    "INTEGRATION",
    "Context",
    "destination",
    "status",
    "screen",
    "__version__",
    "__author__",
]
