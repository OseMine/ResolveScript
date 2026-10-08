"""Example ResolveScript framework extension.

Registers an ``analyze-extra`` command on the resolvescript CLI. The CLI
imports this module at startup (see ``ResolveScript.plugins``) and calls
``register_commands`` with the top-level subparser action.

Plugins are imported as top-level modules, so use absolute imports of your
own files (the plugin directory is on ``sys.path`` during import).
"""

from __future__ import annotations

import argparse


def _cmd_analyze_extra(args: argparse.Namespace) -> int:
    del args
    print("analyze-extra: 0 issues (example plugin)")
    return 0


def register_commands(parser: argparse.ArgumentParser) -> None:
    """Entry point required by ResolveScript.plugins.register_plugin_commands."""
    sub = parser.add_parser(
        "analyze-extra",
        help="extra static checks provided by the example plugin",
    )
    sub.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors (example flag)",
    )
    sub.set_defaults(func=_cmd_analyze_extra)
