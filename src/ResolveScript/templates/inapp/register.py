"""In-app helper: register the @NAME@ extension into the open Resolve project.

Paste this into Resolve's Console (Workspace > Console) or run it as a Utility
script to wire the installed @NAME@ script into the current project's Tools or
Edit menus for one session. The package must already be installed via
``resolvescript install`` (or on ``sys.path``).

Using ``addMenuItem`` is the standard non-persistent way to surface a script in
the Resolve UI menus.
"""

import DaVinciResolveScript as dvr_script


def _register() -> None:
    resolve = dvr_script.scriptapp("Resolve")
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        print("@NAME@: no project is open")
        return

    import @NAME@  # installed under the Scripts root

    project.AddMenuItem("Tools", "@NAME@", lambda: @NAME@.menu.run(resolve))


if __name__ == "__main__":
    _register()