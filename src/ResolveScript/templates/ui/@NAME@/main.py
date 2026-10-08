"""Main entry point for @NAME@.

A DaVinci Resolve script with a UI built using the ResolveScript UI framework.
"""

from __future__ import annotations

import sys

from .core import run_ui


def main() -> int:
    """Entry point for the script when installed in DaVinci Resolve."""
    try:
        return run_ui()
    except Exception as exc:
        print(f"Error in @NAME@: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())