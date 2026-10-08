"""Entry module for the @NAME@ ResolveScript extension (plugin).

This module is imported by the CLI at startup and must expose
``register_commands(parser)`` which receives the top-level subparser action.
"""

from __future__ import annotations

import argparse


def _cmd_example(args: argparse.Namespace) -> int:
    del args
    print("@NAME@ example command ran successfully")
    return 0


def register_commands(parser: argparse.ArgumentParser) -> None:
    """Register this plugin's commands with the resolvescript CLI."""
    sub = parser.add_parser(
        "@NAME_KEBAB@-cmd",
        help="Example command contributed by the @NAME@ plugin",
    )
    sub.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    sub.set_defaults(func=_cmd_example)