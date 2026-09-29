"""The entry point the generated launcher calls.

The generated module is a thin shim; everything that decides *what* happens when
the user opens the integration lives here, so it is testable without a file on
disk. :func:`main` supports three modes:

``(no flags)``
    Launch. Runs ``on_launch``, then builds and runs the UI window if the
    integration has one. This is the mode Resolve uses.

``--callback NAME``
    Run one callback, report it as JSON on stdout, exit non-zero on failure.
    This is how the Electron shell reaches a callback, because Resolve's own
    callback API only exists in JavaScript.

``--serve``
    Answer the :mod:`~ResolveScript.workflow.bridge` line protocol on
    stdin/stdout until ``quit`` or EOF. The Electron shell uses this so the
    integration is imported once per window rather than once per click.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

from ..ui.app import App
from ..ui.errors import UIError
from .bridge import callback_cli, dumps, serve
from .model import CALLBACKS, Context, Integration

__all__ = ["main", "run_integration", "run_ui"]


def run_ui(integration: Integration, context: Context) -> int:
    """Build the integration's window and run its event loop.

    Returns the exit code. A headless integration (no ``build_ui``) has nothing
    to run and returns immediately, which is the correct behaviour — Resolve
    does not require a window.
    """
    window = integration.build(context)
    if window is None:
        return 0
    backend = integration.ui_backend
    if backend is None:
        backend = "auto"
    try:
        return App(window, backend=backend).run()
    except UIError as exc:
        # A UIError here means the environment cannot host the window (no
        # Resolve, no bmd module, a bad node). That is worth reporting rather
        # than letting a bare traceback reach Resolve's console.
        print(f"{integration.name}: {exc}", file=sys.stderr)
        return 1


def run_integration(
    integration: Integration,
    context: Context,
    *,
    show: bool = True,
) -> int:
    """Run ``on_launch`` and then the window. Returns the exit code.

    :param show: set ``False`` to run only the launch handler, which is what
        the tests and the ``launch`` bridge action want.
    """
    code = integration.launch(context)
    if code:
        return code
    if not show or not integration.has_ui:
        return 0
    return run_ui(integration, context)


def main(
    integration: Integration,
    *,
    resolve: Any = None,
    project: Any = None,
    argv: Sequence[str] | None = None,
) -> int:
    """Parse ``argv`` and run the integration. Returns a process exit code."""
    parser = _parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse already printed the message
        return int(exc.code or 0)

    context = Context.detect(resolve, project, integration=integration)

    if args.serve:
        return serve(integration, context)
    if args.callback:
        return callback_cli(integration, args.callback, context)
    if args.describe:
        print(dumps({"ok": True, "result": integration.as_dict()}))
        return 0
    return run_integration(integration, context, show=not args.no_ui)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workflow",
        description="Run a DaVinci Resolve Workflow Integration.",
        add_help=True,
    )
    parser.add_argument(
        "--callback",
        metavar="NAME",
        choices=CALLBACKS,
        help="run one Resolve callback and print its result as JSON",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="answer the bridge line protocol on stdin/stdout",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="print the integration's metadata as JSON and exit",
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="run the launch handler without opening a window",
    )
    return parser
