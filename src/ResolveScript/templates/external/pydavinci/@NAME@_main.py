"""In-app entry point for @NAME@ using pydavinci.

Run inside DaVinci Resolve (Workspace → Scripts) after installing.
Uses pydavinci for type hints and autocomplete.
"""

from pydavinci import davinci
from @NAME@.menu import run

# Use pydavinci's Resolve wrapper for better IDE support
resolve = davinci.Resolve()
print(run(resolve))