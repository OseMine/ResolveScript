"""In-app entry point for @NAME@.

Run inside DaVinci Resolve (Workspace → Scripts) after installing.
The mock API mirrors ``DaVinciResolveScript`` so this also runs in the
sandbox via ``resolvescript dev --editor``.
"""

import DaVinciResolveScript as dvr_script

from @NAME@.menu import run

resolve = dvr_script.scriptapp("Resolve")
print(run(resolve))