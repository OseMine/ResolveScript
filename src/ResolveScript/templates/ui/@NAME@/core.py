"""Core UI logic for @NAME@.

This module contains the UI implementation, separated from the entry point
for better testability and maintainability.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def build_ui(resolve) -> None:
    """Build the UI components for the script.

    Args:
        resolve: The DaVinci Resolve application object.
    """
    log.info("Building UI for @NAME@")
    # Add your UI construction logic here
    # Example:
    # fu = resolve.Fusion()
    # ui = fu.UIManager
    # disp = ui.AddWindow(...)
    pass


def run_ui() -> int:
    """Run the UI application.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    # When running in DaVinci Resolve, the resolve object is available globally
    # In the test sandbox, it's injected via the mock
    try:
        import DaVinciResolveScript as dvr_script
        resolve = dvr_script.scriptapp("Resolve")
    except ImportError:
        # Running outside Resolve (e.g., in tests)
        resolve = None

    if resolve is None:
        print("@NAME@: No Resolve instance found. Running in test mode.")
        return 0

    try:
        build_ui(resolve)
        print("@NAME@: UI built successfully")
        return 0
    except Exception as exc:
        print(f"@NAME@: Failed to build UI: {exc}")
        return 1