"""Sample menu UI for @NAME@.

``run`` is the entry the sandbox and smoke tests exercise; it works against
either the mock API (``resolvescript dev``/``test``) or the real Resolve API.
"""


def run(resolve) -> str:
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        return "@NAME@: no project is open"
    return f"@NAME@ ready — project: {project.GetName()}"