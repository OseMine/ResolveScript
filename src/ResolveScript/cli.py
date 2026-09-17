"""Command-line entry point for ``resolvescript``.

Every subcommand maps to a handler function returning an exit code
(0 = ok, 1 = error, 2 = usage). Production implementations are wired in by
their owning milestone; anything still on the M0 skeleton prints a notice.
"""

from __future__ import annotations

import argparse
import json
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


def _cmd_package(args: argparse.Namespace) -> int:
    from .package import PackageError, package_project

    root = Path.cwd()
    dist_dir = Path(args.dist) if args.dist else None
    try:
        result = package_project(root, dist_dir)
    except (ManifestError, PackageError) as exc:
        print(f"resolvescript: package: {exc}", file=sys.stderr)
        return 1
    print(f"Created {result.archive.name} ({result.archive.stat().st_size} bytes)")
    print(f"SHA-256: {result.sha256}")
    if result.checksum_file:
        print(f"Wrote {result.checksum_file.name}")
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


def _resolve_scripts_root(override: str | None) -> Path:
    from .install.discovery import resolve_scripts_root

    return resolve_scripts_root(override)


def _cache_dir(cwd: Path) -> Path:
    path = cwd / ".resolvescript" / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _materialize(spec_text: str, scripts_root: Path, *, cwd: Path | None = None):
    from .resolver import resolve_spec

    cwd = cwd or Path.cwd()
    return resolve_spec(spec_text, cwd=cwd, work_dir=_cache_dir(cwd))


def _major(version: str) -> int:
    try:
        return int(version.split(".")[0])
    except (ValueError, IndexError):
        return -1


def _pin_spec(spec_text: str, precise: str, cwd: Path) -> str:
    from .spec import parse_specifier

    spec = parse_specifier(spec_text, cwd=cwd)
    if spec.kind == "github" and spec.owner and spec.repo:
        return f"github:{spec.owner}/{spec.repo}#{precise}"
    if spec.kind == "name":
        from .sources import known

        entry = known.lookup(spec.source)
        if entry and entry["source"].startswith("github:"):
            return entry["source"] + f"#{precise}"
    return spec_text


def _cmd_install(args: argparse.Namespace) -> int:
    from .install.discovery import resolve_scripts_root
    from .install.installer import InstallError, InstallOptions, install_package, install_project
    from .install.registry import get_extension, read_registry
    from .resolver import ResolveError, lockfile_satisfies
    from .workspace import read_workspace

    cwd = Path.cwd()
    scripts_root = resolve_scripts_root(args.scripts_root)

    def _report(result) -> int:
        for line in result.describe():
            print(line)
        if result.dry_run:
            print("(dry run - nothing was written)")
        else:
            print(f".resolvescript registry: {scripts_root / '.resolvescript' / 'install.json'}")
        return 0

    try:
        if args.spec:
            resolved = _materialize(args.spec, scripts_root, cwd=cwd)
            result = install_package(
                resolved.package_dir,
                resolved.manifest,
                InstallOptions(
                    scripts_root=scripts_root,
                    source=resolved.source,
                    resolved=resolved.source,
                    integrity=resolved.integrity,
                ),
            )
            return _report(result)

        has_manifest = (cwd / "manifest.json").is_file() or (cwd / "manifest.xml").is_file()
        if has_manifest:
            result = install_project(cwd, InstallOptions(scripts_root=scripts_root, dry_run=args.dry_run))
            return _report(result)

        if (cwd / "resolvescript.json").is_file():
            deps = read_workspace(cwd).get("dependencies", {})
            if not deps:
                print("resolvescript: no recorded dependencies in resolvescript.json")
                return 0
            registry = read_registry(scripts_root)
            errors = 0
            for name, spec in sorted(deps.items()):
                entry = get_extension(registry, name)
                if entry and lockfile_satisfies(entry, spec, cwd=cwd):
                    if args.locked:
                        print(f"locked {name} {entry.get('version', '?')} (registry)")
                    else:
                        print(f"already installed {name} {entry.get('version', '?')}")
                    continue
                if args.locked:
                    print(
                        f"resolvescript: --locked: {name}: recorded artifact no longer "
                        f"satisfies {spec!r}",
                        file=sys.stderr,
                    )
                    errors += 1
                    continue
                try:
                    resolved = _materialize(spec, scripts_root, cwd=cwd)
                    result = install_package(
                        resolved.package_dir,
                        resolved.manifest,
                        InstallOptions(
                            scripts_root=scripts_root,
                            source=resolved.source,
                            resolved=resolved.source,
                            integrity=resolved.integrity,
                        ),
                    )
                except (ResolveError, InstallError) as exc:
                    print(f"resolvescript: install {name}: {exc}", file=sys.stderr)
                    errors += 1
                    continue
                for line in result.describe():
                    print(line)
            return 1 if errors else 0

        print(
            "resolvescript: nothing to install - add a manifest.json, a resolvescript.json, "
            "or pass a specifier",
            file=sys.stderr,
        )
        return 2
    except (ManifestError, ResolveError, InstallError) as exc:
        print(f"resolvescript: install: {exc}", file=sys.stderr)
        return 1


def _cmd_remove(args: argparse.Namespace) -> int:
    from .install.installer import InstallError, InstallOptions, uninstall_package
    from .workspace import has_workspace, read_workspace, remove_dependency, save

    scripts_root = _resolve_scripts_root(args.scripts_root)
    cwd = Path.cwd()
    had_workspace_entry = (
        has_workspace(cwd)
        and args.name in read_workspace(cwd).get("dependencies", {})
    )
    try:
        removed = uninstall_package(args.name, InstallOptions(scripts_root=scripts_root))
    except InstallError as exc:
        if not had_workspace_entry or args.no_save:
            print(f"resolvescript: remove: {exc}", file=sys.stderr)
            return 1
        removed = []
    for path in removed:
        print(f"removed {path}")
    if had_workspace_entry and not args.no_save:
        save(remove_dependency(args.name, cwd), cwd)
        print(f"unrecorded {args.name} from resolvescript.json")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    from .install.installer import InstallError, InstallOptions, install_package
    from .resolver import ResolveError
    from .workspace import add_dependency, save

    cwd = Path.cwd()
    scripts_root = _resolve_scripts_root(args.scripts_root)
    try:
        resolved = _materialize(args.spec, scripts_root, cwd=cwd)
        result = install_package(
            resolved.package_dir,
            resolved.manifest,
            InstallOptions(
                scripts_root=scripts_root,
                source=resolved.source,
                resolved=resolved.source,
                integrity=resolved.integrity,
            ),
        )
    except (ResolveError, InstallError) as exc:
        print(f"resolvescript: add: {exc}", file=sys.stderr)
        return 1
    for line in result.describe():
        print(line)
    if not args.no_save:
        save(add_dependency(resolved.name, args.spec, cwd), cwd)
        print(f"recorded {resolved.name} -> {args.spec} in resolvescript.json")
    return 0


def _cmd_update(args: argparse.Namespace) -> int:
    from .install.installer import InstallError, InstallOptions, install_package
    from .resolver import ResolveError
    from .workspace import add_dependency, has_workspace, read_workspace, save

    cwd = Path.cwd()
    if not has_workspace(cwd):
        print(
            "resolvescript: update: no resolvescript.json in the current directory "
            "(run 'resolvescript add <spec>' first)",
            file=sys.stderr,
        )
        return 2
    scripts_root = _resolve_scripts_root(args.scripts_root)
    deps = read_workspace(cwd).get("dependencies", {})
    names = [args.name] if args.name else sorted(deps)
    compat_env = __import__("os").environ.get("RESOLVESCRIPT_COMPAT", "18")
    errors = 0
    for name in names:
        spec = deps.get(name)
        if spec is None:
            print(
                f"resolvescript: update: '{name}' is not recorded in resolvescript.json",
                file=sys.stderr,
            )
            errors += 1
            continue
        pinned = _pin_spec(spec, args.precise, cwd) if args.precise else spec
        try:
            resolved = _materialize(pinned, scripts_root, cwd=cwd)
        except ResolveError as exc:
            print(f"resolvescript: update {name}: {exc}", file=sys.stderr)
            errors += 1
            continue
        if args.precise and resolved.version != args.precise:
            print(
                f"resolvescript: --precise {args.precise}: got version {resolved.version}",
                file=sys.stderr,
            )
            errors += 1
            continue
        if args.fix:
            compat = getattr(resolved.manifest, "compat", None)
            compat_str = getattr(compat, "resolve", None) if compat else None
            if compat_str and _major(compat_str) != _major(compat_env):
                print(
                    f"resolvescript: update {name}: not compatible with DaVinci "
                    f"Resolve {compat_env} (manifest declares resolve {compat_str}); "
                    f"keeping previous version (--fix)",
                    file=sys.stderr,
                )
                continue
        try:
            result = install_package(
                resolved.package_dir,
                resolved.manifest,
                InstallOptions(
                    scripts_root=scripts_root,
                    source=resolved.source,
                    resolved=resolved.source,
                    integrity=resolved.integrity,
                ),
            )
        except InstallError as exc:
            print(f"resolvescript: update {name}: {exc}", file=sys.stderr)
            errors += 1
            continue
        for line in result.describe():
            print(line)
        if args.precise and pinned != spec:
            save(add_dependency(name, pinned, cwd), cwd)
            print(f"updated resolvescript.json: {name} -> {pinned}")
    return 1 if errors else 0


def _cmd_search(args: argparse.Namespace) -> int:
    from .sources.known import search

    results = search(args.query)
    if not results:
        print(f"no known Resolve scripts match {args.query!r}")
        return 0
    for entry in results:
        print(f"{entry['name']:20} {entry['source']}")
        print(f"    {entry['desc']}")
    return 0


def _cmd_manage_list(args: argparse.Namespace) -> int:
    from .install.registry import read_registry

    scripts_root = _resolve_scripts_root(getattr(args, "scripts_root", None))
    extensions = read_registry(scripts_root).get("extensions", {})
    if getattr(args, "json", False):
        print(json.dumps(extensions, indent=2))
        return 0
    if not extensions:
        print("no extensions installed")
        return 0
    for key, entry in sorted(extensions.items()):
        targets = ",".join(entry.get("targets", []))
        version = entry.get("version", "?")
        source = entry.get("source", "")
        print(f"{key:24} {version:8} {targets:16} {source}")
    return 0


def _cmd_manage_remove(args: argparse.Namespace) -> int:
    import shutil

    from .install.discovery import target_dir
    from .install.installer import InstallError, validate_registry_name, validate_registry_relpath
    from .install.registry import get_extension, read_registry, remove_entry

    scripts_root = _resolve_scripts_root(args.scripts_root)
    registry = read_registry(scripts_root)
    entry = get_extension(registry, args.name)
    if entry is None:
        print(
            f"resolvescript: manage remove: '{args.name}' is not installed",
            file=sys.stderr,
        )
        return 1
    as_directory = bool(entry.get("as_directory", True))
    try:
        key = validate_registry_name(entry.get("id") or args.name)
        container_name = validate_registry_name(entry.get("name") or key)
    except InstallError as exc:
        print(f"resolvescript: manage remove: {exc}", file=sys.stderr)
        return 1
    for target in entry.get("targets", []):
        base = target_dir(scripts_root, target)
        if as_directory:
            container = base / container_name
            if container.is_dir():
                shutil.rmtree(container)
                print(f"removed {container}")
        else:
            for raw_rel in entry.get("files", []):
                try:
                    rel = validate_registry_relpath(str(raw_rel))
                except InstallError as exc:
                    print(f"resolvescript: manage remove: {exc}", file=sys.stderr)
                    return 1
                path = base / rel
                if path.is_file() or (path.is_symlink() and not path.exists()):
                    path.unlink()
                    print(f"removed {path}")
    if args.all:
        remove_entry(scripts_root, key) or remove_entry(scripts_root, key.split(":")[-1])
        print(f"removed registry entry '{args.name}'")
    else:
        print(f"kept registry entry '{args.name}' (use --all to remove it)")
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    import subprocess

    from .analyze import analyze_project

    cwd = Path.cwd()
    try:
        manifest, _path = _load_manifest_from(cwd)
    except ManifestError as exc:
        print(f"resolvescript: test: {exc}", file=sys.stderr)
        return 1

    module_name = manifest.python or manifest.name
    env = dict(__import__("os").environ)
    pytest_args = ["-p", "no:cacheprovider", "-q"]
    if args.pattern:
        pytest_args += ["-k", args.pattern]

    if args.built:
        built_file = _resolve_built_file(module_name, manifest.consolidate.output)
        if not built_file.is_file():
            print(
                f"resolvescript: test: built package not found: {built_file} "
                "(run 'resolvescript build' first)",
                file=sys.stderr,
            )
            return 1
        env["RESOLVESCRIPT_TARGET"] = "built"
        env["RESOLVESCRIPT_MODULE"] = module_name
        env["RESOLVESCRIPT_BUILT_PATH"] = str(built_file)
        runner = (
            "import os, sys, pathlib\n"
            "from ResolveScript.sandbox.env import install_fake_resolve\n"
            "from ResolveScript.sandbox.loader import load_built_module\n"
            "install_fake_resolve()\n"
            "if os.environ.get('RESOLVESCRIPT_TARGET') == 'built':\n"
            "    name = os.environ['RESOLVESCRIPT_MODULE']\n"
            "    mod = load_built_module(name, os.environ['RESOLVESCRIPT_BUILT_PATH'])\n"
            "    sys.modules[name] = mod\n"
            "    for pkg_sub in sorted((pathlib.Path.cwd() / name).glob('*.py')):\n"
            "        if pkg_sub.stem != '__init__':\n"
            "            sys.modules[f'{name}.{pkg_sub.stem}'] = mod\n"
            "import pytest\n"
            "sys.exit(pytest.main(sys.argv[1:]))\n"
        )
        cmd = [sys.executable, "-c", runner] + pytest_args
    else:
        env["RESOLVESCRIPT_TARGET"] = "source"
        cmd = [sys.executable, "-m", "pytest"] + pytest_args

    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        return 1
    if args.api_coverage:
        analysis = analyze_project(cwd, manifest)
        for line in analysis.api_report():
            print(line)
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    from .analyze import analyze_project, issues_to_json

    try:
        manifest, _path = _load_manifest_from(Path.cwd())
    except ManifestError as exc:
        print(f"resolvescript: analyze: {exc}", file=sys.stderr)
        return 1
    analysis = analyze_project(Path.cwd(), manifest)
    if getattr(args, "json", False):
        print(issues_to_json(analysis))
        return 0
    if not analysis.issues:
        for line in analysis.api_report():
            print(line)
        print("no issues found")
        return 0
    for issue in analysis.issues:
        where = f"{issue.file}:{issue.line}" if issue.file else "-"
        print(f"[{issue.severity.upper()}] {issue.code} {where}: {issue.message}")
    for line in analysis.api_report():
        print(line)
    return 1 if any(i.severity == "error" for i in analysis.issues) else 0


def _load_manifest_from(root: Path):
    """Load manifest.json or manifest.xml from ``root`` or raise ManifestError."""
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        manifest_path = root / "manifest.xml"
        if not manifest_path.is_file():
            raise ManifestError(
                f"no manifest.json or manifest.xml in {root} (run 'resolvescript create')"
            )
    if manifest_path.suffix == ".xml":
        from .manifest.xml_reader import load_manifest
    else:
        from .manifest.json_reader import load_manifest
    return load_manifest(manifest_path), manifest_path


def _resolve_built_file(module_name: str, output: str | None) -> Path:
    return Path.cwd() / "dist" / (output or f"{module_name}.py")


def _cmd_dev(args: argparse.Namespace) -> int:
    from .sandbox.env import install_fake_resolve
    from .sandbox.loader import load_built_module, load_source_module
    from .sandbox.repl import start_repl
    from .sandbox.smoke import run_smoke

    try:
        manifest, _path = _load_manifest_from(Path.cwd())
    except ManifestError as exc:
        print(f"resolvescript: dev: {exc}", file=sys.stderr)
        return 1

    module_name = manifest.python or manifest.name
    install_fake_resolve()

    try:
        if args.built:
            built_file = _resolve_built_file(module_name, manifest.consolidate.output)
            if not built_file.is_file():
                raise FileNotFoundError(
                    f"built package not found: {built_file} (run 'resolvescript build' first)"
                )
            module = load_built_module(module_name, built_file)
            try:
                display = built_file.relative_to(Path.cwd()).as_posix()
            except ValueError:
                display = built_file.as_posix()
            mode = f"built: {display}"
        else:
            module = load_source_module(module_name, Path.cwd())
            mode = f"source: {module_name}/"
    except (FileNotFoundError, ImportError) as exc:
        print(f"resolvescript: dev: {exc}", file=sys.stderr)
        return 1

    print(f"Sandbox environment ready ({mode})")

    if args.editor:
        from .scaffold import TEMPLATES_DIR, render

        template = TEMPLATES_DIR / "inapp" / "register.py"
        text = template.read_text(encoding="utf-8")
        print(render(text, {"NAME": manifest.name}))
        return 0

    result = run_smoke(module, verbose=True)

    if args.repl:
        if not result.ok:
            print("Some checks failed; dropping into the REPL anyway.")
        start_repl(module)
        return 0
    if not result.ok:
        print("Some checks failed.")
        return 1
    print("All checks passed.")
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
    p.set_defaults(func=_cmd_dev)

    p = sub.add_parser("test", help="run the extension's pytest suite against the mock API")
    p.add_argument("--built", action="store_true", help="test the consolidated single file")
    p.add_argument("-k", dest="pattern", help="only run tests matching the expression")
    p.add_argument("--api-coverage", action="store_true", help="report used-vs-mocked Resolve API methods")
    p.set_defaults(func=_cmd_test)

    p = sub.add_parser("analyze", help="static checks on the extension (imports, manifest, API usage)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=_cmd_analyze)

    p = sub.add_parser("build", help="consolidate the multi-file package into a single file")
    p.add_argument("--output", help="output path (default: dist/<manifest output>)")
    p.set_defaults(func=_cmd_build)

    p = sub.add_parser("package", help="assemble release artifacts into dist/")
    p.add_argument("--dist", help="output directory (default: dist/)")
    p.set_defaults(func=_cmd_package)

    p = sub.add_parser("add", help="install a Resolve script and record it in resolvescript.json")
    p.add_argument("spec", help="specifier (name, owner/repo, github:, URL, archive, file:, ./dir)")
    p.add_argument("--scripts-root", help="override OS-detected Scripts root / RESOLVESCRIPT_SCRIPTS_ROOT")
    p.add_argument("--target", help="override the install target (Comp, Utility, ...)")
    p.add_argument("--no-save", action="store_true", help="install without recording")
    p.set_defaults(func=_cmd_add)

    p = sub.add_parser("install", help="materialize recorded deps, or install a single spec one-off")
    p.add_argument("spec", nargs="?", help="one-off specifier (without it, installs recorded deps)")
    p.add_argument("--scripts-root", help="override OS-detected Scripts root / RESOLVESCRIPT_SCRIPTS_ROOT")
    p.add_argument("--locked", action="store_true", help="fail if recorded artifacts no longer satisfy ranges")
    p.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    p.set_defaults(func=_cmd_install)

    p = sub.add_parser("update", help="re-resolve recorded deps within their ranges")
    p.add_argument("name", nargs="?", help="update only this dependency")
    p.add_argument("--scripts-root", help="override OS-detected Scripts root / RESOLVESCRIPT_SCRIPTS_ROOT")
    p.add_argument("--precise", help="pin an exact version")
    p.add_argument("--fix", action="store_true", help="realign installed versions to manifest compat")
    p.set_defaults(func=_cmd_update)

    p = sub.add_parser("remove", help="uninstall a Resolve script and unrecord it")
    p.add_argument("name", help="installed extension name")
    p.add_argument("--scripts-root", help="override OS-detected Scripts root / RESOLVESCRIPT_SCRIPTS_ROOT")
    p.add_argument("--no-save", action="store_true", help="uninstall but keep the recorded specifier")
    p.set_defaults(func=_cmd_remove)

    p = sub.add_parser("search", help="discover Resolve scripts (known table + conventions)")
    p.add_argument("query", help="search term")
    p.set_defaults(func=_cmd_search)

    p = sub.add_parser("consolidate", help="merge a package directory into a single .py (no manifest needed)")
    p.add_argument("package_dir", help="package directory to consolidate")
    p.add_argument("--output", required=True, help="output file path")
    p.set_defaults(func=_cmd_consolidate)

    p = sub.add_parser("manage", help="low-level install registry operations")
    manage = p.add_subparsers(dest="manage_command", metavar="<manage>", required=True)
    mp = manage.add_parser("list", help="list installed extensions")
    mp.add_argument("--scripts-root", help="override OS-detected Scripts root / RESOLVESCRIPT_SCRIPTS_ROOT")
    mp.add_argument("--json", action="store_true", help="machine-readable output")
    mp.set_defaults(func=_cmd_manage_list)
    mp = manage.add_parser("remove", help="delete tracked files without touching config")
    mp.add_argument("name")
    mp.add_argument("--scripts-root", help="override OS-detected Scripts root / RESOLVESCRIPT_SCRIPTS_ROOT")
    mp.add_argument("--all", action="store_true", help="also remove the registry entry")
    mp.set_defaults(func=_cmd_manage_remove)

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
