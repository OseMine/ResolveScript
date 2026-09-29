"""Run @NAME@ directly.

    python @NAME@_workflow.py              # launch, like Resolve does
    python @NAME@_workflow.py --describe   # print the metadata as JSON
    python @NAME@_workflow.py --no-ui      # on_launch only, no window

Resolve does not use this file. It launches the *generated* launcher, written
by `resolvescript workflow build`, which is the same three lines over a project
root that Resolve can import. This one is here so the integration can be run
and debugged from a terminal.
"""

from ResolveScript.workflow import main

from @NAME@.workflow import INTEGRATION

raise SystemExit(main(INTEGRATION))
