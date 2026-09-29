"""@NAME@ package - using pydavinci wrapper."""

from typing import Any

from pydavinci import davinci


def run(resolve: davinci.Resolve) -> str:
    """Main entry point for the Resolve script."""
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject()
    
    if not project:
        return "No project open"
    
    return f"Hello from @NAME@ in project '{project.GetName()}'!"