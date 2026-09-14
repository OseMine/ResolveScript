"""Command-line entry point for ``resolvescript``.

Every subcommand maps to a handler function returning an exit code
(0 = ok, 1 = error, 2 = usage). Production implementations are wired in by
their owning milestone; anything still on the M0 skeleton prints a notice.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from . import __version__
from .consolidate import (
    BuildConfig,
    ConsolidateError,
    config_from_manifest,
    consolidate,
    summarize,
)
from .manifest.model import ManifestError
from .scaffold import ScaffoldError, scaffold_project

USAGE = 2


def _skeleton(name: str) -> Callable[[argparse.Namespace], int]:
    """Return a stub handler until the owning milestone wires the command."""

    def run(args: argparse.Namespace) -> int:
        del args
        print(f"resolvescript: '{name}' is not implemented yet (M0 skeleton)", file=sys.stderr)
        return 1

    return run


def _cmd_create(args: argparse.Namespace) -> int:
    destination = Path(args.dir) if args.dir else None
    try:
        root, written = scaffold_project(
            args.name,
            destination=destination,
            fmt=args.fmt,
            template=args.template,
        )
    except ScaffoldError as exc:
        print(f"resolvescript: cannot create: {exc}", file=sys.stderr)
        return 1
    print(f"Created {args.fmt.upper()} manifest Resolve script project in {root}")
    for rel in sorted(written):
        print(f"  {rel}")
    print("\nNext steps:")
    print(f"  cd {root}")
    print("  resolvescript dev     # iterate against the mock Resolve API")
    print("  resolvescript test    # run the smoke tests")
    print("  resolvescript build   # consolidate into a single file")
    print("  resolvescript install # install into DaVinci Resolve")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    root = Path.cwd()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        manifest_path = root / "manifest.xml"
        if not manifest_path.is_file():
            print(
                "resolvescript: no manifest.json or manifest.xml in the current directory "
                "(run 'resolvescript create' or use 'resolvescript consolidate <dir>')",
                file=sys.stderr,
            )
            return 1
    try:
        if manifest_path.suffix == ".xml":
            from .manifest.xml_reader import load_manifest
        else:
            from .manifest.json_reader import load_manifest
        manifest = load_manifest(manifest_path)
    except ManifestError as exc:
        print(f"resolvescript: {exc}", file=sys.stderr)
        return 1

    if not manifest.consolidate.enabled:
        print("resolvescript: consolidate is disabled in the manifest; nothing to build")
        return 0
    output = Path(args.output) if args.output else None
    config = config_from_manifest(root, manifest, output_override=output)
    try:
        result = consolidate(config)
    except ConsolidateError as exc:
        print(f"resolvescript: build failed: {exc}", file=sys.stderr)
        return 1
    print(summarize(result, config))
    return 0


def _cmd_consolidate(args: argparse.Namespace) -> int:
    config = BuildConfig(
        package_root=Path(args.package_dir),
        output=Path(args.output),
    )
    try:
        result = consolidate(config)
    except ConsolidateError as exc:
        print(f"resolvescript: consolidate failed: {exc}", file=sys.stderr)
        return 1
    print(summarize(result, config))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resolvescript",
        description="Build, test, package and install DaVinci Resolve scripts.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("create", help="scaffold a new Resolve script project")
    p.add_argument("name", help="project name / output directory")
    p.add_argument("--json", dest="fmt", action="store_const", const="json", default="json", help="generate manifest.json (default)")
    p.add_argument("--xml", dest="fmt", action="store_const", const="xml", help="generate manifest.xml")
    p.add_argument("--dir", help="parent directory to create the project in")
    p.add_argument("--template", default="minimal", help="scaffold flavor (minimal, toolkit)")
    p.set_defaults(func=_cmd_create)

    p = sub.add_parser("dev", help="sandboxed dev loop / REPL against the mock Resolve API")
    p.add_argument("--built", action="store_true", help="run against the consolidated single file")
    p.add_argument("--repl", action="store_true", help="drop into an interactive REPL")
    p.add_argument("--editor", action="store_true", help="print the in-app Resolve script to run")
    p.set_defaults(func=_skeleton("dev"))

    p = sub.add_parser("test", help="run the extension's pytest suite against the mock API")
    p.add_argument("--built", action="store_true", help="test the consolidated single file")
    p.add_argument("-k", dest="pattern", help="only run tests matching the expression")
    p.add_argument("--api-coverage", action="store_true", help="report used-vs-mocked Resolve API methods")
    p.set_defaults(func=_skeleton("test"))

    p = sub.add_parser("analyze", help="static checks on the extension (imports, manifest, API usage)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=_skeleton("analyze"))

    p = sub.add_parser("build", help="consolidate the multi-file package into a single file")
    p.add_argument("--output", help="output path (default: dist/<manifest output>)")
    p.set_defaults(func=_cmd_build)

    p = sub.add_parser("package", help="assemble release artifacts into dist/")
    p.add_argument("--dist", help="output directory (default: dist/)")
    p.set_defaults(func=_skeleton("package"))

    p = sub.add_parser("add", help="install a Resolve script and record it in resolvescript.json")
    p.add_argument("spec", help="specifier (name, owner/repo, github:, URL, archive, file:, ./dir)")
    p.add_argument("--target", help="override the install target (Comp, Utility, …)")
    p.add_argument("--no-save", action="store_true", help="install without recording")
    p.set_defaults(func=_skeleton("add"))

    p = sub.add_parser("install", help="materialize recorded deps, or install a single spec one-off")
    p.add_argument("spec", nargs="?", help="one-off specifier (without it, installs recorded deps)")
    p.add_argument("--scripts-root", help="override OS-detected Scripts root / RESOLVESCRIPT_SCRIPTS_ROOT")
    p.add_argument("--locked", action="store_true", help="fail if recorded artifacts no longer satisfy ranges")
    p.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    p.set_defaults(func=_skeleton("install"))

    p = sub.add_parser("update", help="re-resolve recorded deps within their ranges")
    p.add_argument("name", nargs="?", help="update only this dependency")
    p.add_argument("--precise", help="pin an exact version")
    p.add_argument("--fix", action="store_true", help="realign installed versions to manifest compat")
    p.set_defaults(func=_skeleton("update"))

    p = sub.add_parser("remove", help="uninstall a Resolve script and unrecord it")
    p.add_argument("name", help="installed extension name")
    p.add_argument("--no-save", action="store_true", help="uninstall but keep the recorded specifier")
    p.set_defaults(func=_skeleton("remove"))

    p = sub.add_parser("search", help="discover Resolve scripts (known table + conventions)")
    p.add_argument("query", help="search term")
    p.set_defaults(func=_skeleton("search"))

    p = sub.add_parser("consolidate", help="merge a package directory into a single .py (no manifest needed)")
    p.add_argument("package_dir", help="package directory to consolidate")
    p.add_argument("--output", required=True, help="output file path")
    p.set_defaults(func=_cmd_consolidate)

    p = sub.add_parser("manage", help="low-level install registry operations")
    manage = p.add_subparsers(dest="manage_command", metavar="<manage>", required=True)
    mp = manage.add_parser("list", help="list installed extensions")
    mp.add_argument("--json", action="store_true", help="machine-readable output")
    mp.set_defaults(func=_skeleton("manage list"))
    mp = manage.add_parser("remove", help="delete tracked files without touching config")
    mp.add_argument("name")
    mp.add_argument("--all", action="store_true", help="also remove the registry")
    mp.set_defaults(func=_skeleton("manage remove"))

    p = sub.add_parser("extensions", help="manage ResolveScript framework extensions (plugins)")
    ext = p.add_subparsers(dest="ext_command", metavar="<ext>", required=True)
    ep = ext.add_parser("add", help="install a plugin into the CLI config dir")
    ep.add_argument("spec", help="plugin specifier")
    ep.add_argument("--force", action="store_true", help="reinstall even if present")
    ep.set_defaults(func=_skeleton("extensions add"))
    ep = ext.add_parser("remove", help="uninstall a plugin")
    ep.add_argument("name")
    ep.set_defaults(func=_skeleton("extensions remove"))
    ep = ext.add_parser("list", help="list installed plugins")
    ep.set_defaults(func=_skeleton("extensions list"))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", None)
    if command is None:
        parser.print_help()
        return USAGE
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
