"""Single-file consolidator (M3).

Generic port of Rotoscope ``scripts/build.py``: collect a multi-file Python
package, strip internal/relative imports, order modules by dependency, hoist
``from __future__ import`` statements, and emit one importable ``.py`` file
that DaVinci Resolve can consume (or that ``resolvescript add`` can install).
"""

from __future__ import annotations

import ast
import logging
import re
import textwrap
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol

from .errors import ResolveScriptError
from .manifest.model import ConsolidateConfig

logger = logging.getLogger(__name__)

STDLIB_MODULES = frozenset(
    {
        "abc", "argparse", "array", "ast", "asyncio", "base64", "bisect",
        "builtins", "bz2", "collections", "concurrent", "configparser",
        "contextlib", "contextvars", "copy", "csv", "ctypes", "dataclasses",
        "datetime", "decimal", "dbm", "dis", "email", "enum", "errno",
        "fnmatch", "fractions", "functools", "gc", "getopt", "glob", "gzip",
        "hashlib", "heapq", "hmac", "html", "http", "importlib", "inspect",
        "io", "ipaddress", "itertools", "json", "keyword", "logging", "lzma",
        "marshal", "math", "mimetypes", "multiprocessing", "netrc", "numbers",
        "operator", "optparse", "os", "pathlib", "pickle", "platform",
        "plistlib", "pprint", "queue", "random", "re", "reprlib", "select",
        "selectors", "secrets", "shelve", "shutil", "signal", "site", "socket",
        "sqlite3", "ssl", "stat", "statistics", "string", "struct", "subprocess",
        "sys", "tarfile", "tempfile", "textwrap", "threading", "time", "token",
        "tokenize", "traceback", "types", "typing", "unicodedata", "urllib",
        "uuid", "warnings", "weakref", "xml", "zipfile", "zlib",
    }
)


class ConsolidateError(ResolveScriptError):
    """A package could not be consolidated."""


@dataclass
class BuildConfig:
    """Parameters for a consolidation run."""

    package_root: Path
    output: Path
    package_name: str = ""
    entry: str | None = None
    exclude: tuple[str, ...] = ()
    no_comment: tuple[str, ...] = ()
    noqa: bool = True

    def __post_init__(self) -> None:
        self.package_root = Path(self.package_root)
        self.output = Path(self.output)
        if not self.package_name:
            self.package_name = self.package_root.name


@dataclass
class ConsolidateResult:
    """Outcome of a consolidation run."""

    output: Path
    modules: tuple[str, ...]
    cycles: tuple[str, ...]
    size: int


def module_dotted_name(file_path: Path, package_root: Path, package_name: str) -> str:
    """Return the dotted module name for a file under the package root."""
    rel = file_path.relative_to(package_root)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([package_name, *parts])


def _matches_pattern(pattern: str, rel_str: str) -> bool:
    """Match an exclude/no_comment pattern against a posix relative path."""
    if any(ch in pattern for ch in "*?["):
        return fnmatch(rel_str, pattern)
    return rel_str == pattern or rel_str.startswith(pattern.rstrip("/") + "/")


def collect_python_files(root: Path, exclude: tuple[str, ...] = ()) -> list[Path]:
    """Collect package ``.py`` files, sorted for a stable build."""
    files = []
    for py_file in root.rglob("*.py"):
        rel = py_file.relative_to(root)
        if "__pycache__" in rel.parts:
            continue
        rel_str = rel.as_posix()
        if any(_matches_pattern(pattern, rel_str) for pattern in exclude):
            continue
        files.append(py_file)
    return sorted(files, key=lambda f: (len(f.relative_to(root).parts), str(f)))


def extract_imports(file_path: Path) -> set[str]:
    """Return the top-level module names imported by a file.

    Used to hoist standard-library imports to the top of the output.
    """
    imports: set[str] = set()
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def _import_candidates(node: ast.AST, mod_name: str) -> list[str]:
    """Candidate module names an import node may reference (longest first)."""
    candidates: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name not in candidates:
                candidates.append(alias.name)
        return candidates

    base_parts = mod_name.split(".")
    if isinstance(node, ast.ImportFrom) and node.level:
        for _ in range(node.level):
            if base_parts:
                base_parts.pop()
        if node.module:
            parent = ".".join(base_parts)
            candidates.append(f"{parent}.{node.module}" if parent else node.module)
        else:
            parent = ".".join(base_parts)
            for alias in node.names:
                candidates.append(f"{parent}.{alias.name}" if parent else alias.name)
    elif isinstance(node, ast.ImportFrom):
        candidates.append(node.module or "")
        base = node.module or ""
        for alias in node.names:
            candidates.append(f"{base}.{alias.name}" if base else alias.name)
    return candidates


def local_file_dependencies(
    file_path: Path,
    package_root: Path,
    package_name: str,
    known_modules: set[str],
) -> set[str]:
    """Return the known modules a file depends on (for ordering)."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise ConsolidateError(f"cannot parse {file_path}: {exc}") from exc
    mod_name = module_dotted_name(file_path, package_root, package_name)
    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for candidate in _import_candidates(node, mod_name):
                if candidate != mod_name and candidate in known_modules:
                    deps.add(candidate)
    return deps


def order_modules(names_to_deps: dict[str, set[str]]) -> tuple[list[str], tuple[str, ...]]:
    """Order modules so dependencies come first; cycles fall back to sorted."""
    remaining = set(names_to_deps)
    ordered: list[str] = []
    resolved: set[str] = set()
    cycles: set[str] = set()
    while remaining:
        batch = [
            mod
            for mod in sorted(remaining)
            if (names_to_deps[mod] - {mod}) <= resolved
        ]
        if batch:
            ordered.extend(batch)
            resolved.update(batch)
            remaining.difference_update(batch)
            continue
        batch = sorted(remaining)
        ordered.extend(batch)
        cycles.update(batch)
        remaining.clear()
    return ordered, tuple(sorted(cycles))


def _statement_open(joined: str) -> bool:
    """True if the joined statement still needs continuation lines."""
    if joined.count("(") > joined.count(")"):
        return True
    if joined.count("[") > joined.count("]"):
        return True
    return bool(joined.rstrip().endswith(("\\", ",")))


def _is_internal_import_line(line: str, prefix: str) -> bool:
    """True if a line begins an internal (relative or package) import."""
    stripped = line.strip()
    if stripped.startswith("from .") or stripped.startswith("import ."):
        return True
    return (
        stripped
        in {
            f"from {prefix}",
            f"import {prefix}",
        }
        or stripped.startswith(f"from {prefix}.")
        or stripped.startswith(f"from {prefix} ")
        or stripped.startswith(f"import {prefix}.")
        or stripped.startswith(f"import {prefix} ")
    )


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _comment_lines(buf: list[str]) -> list[str]:
    """Neutralize an internal-import statement (safe inside empty blocks)."""
    indent = _leading_ws(buf[0])
    if indent:
        return [f"{indent}pass  # {buf[0].strip()}"]
    return ["# " + line for line in buf]


def _rewrite_or_comment(
    buf: list[str],
    known: set[str],
    mod_name: str,
    prefix: str,
) -> tuple[list[str], set[str]]:
    """Decide how to neutralize an internal import.

    Returns ``(inline_lines, hoisted_binds)``. Member-level imports (``from
    pkg.core import VALUE``) are commented out — the members already live in
    the shared namespace from the inlined module. Module-binding imports
    (``from . import core``, ``import pkg.util``) are commented out AND a
    namespace binding is hoisted to the top of the output so ``core.attr()``
    style access keeps working. When ``known`` is not given, everything is
    commented (Rotoscope-compatible default).
    """
    if not known:
        return _comment_lines(buf), set()

    joined = "\n".join(buf).lstrip("\n")
    parsed = ast.parse(textwrap.dedent(joined)) if joined[:1] in (" ", "\t") else ast.parse(joined)
    node = parsed.body[0] if parsed.body else None

    if node is None:
        return _comment_lines(buf), set()

    if isinstance(node, ast.Import):
        binds: set[str] = set()
        for alias in node.names:
            dotted = alias.name
            if dotted != prefix and not dotted.startswith(prefix + "."):
                continue
            if alias.asname:
                binds.add(f"{alias.asname} = _rs_shared")
            else:
                top, _, rest = dotted.partition(".")
                binds.add(f"{top} = _rs_shared")
                if rest:
                    binds.add(f"{dotted} = _rs_shared")
        return _comment_lines(buf), binds

    if isinstance(node, ast.ImportFrom):
        if node.module is None and node.level:
            binds = {
                f"{alias.asname or alias.name} = _rs_shared" for alias in node.names
            }
            return _comment_lines(buf), binds

        module = node.module
        if node.level:
            parts = mod_name.split(".")
            for _ in range(node.level):
                if parts:
                    parts.pop()
            module = ".".join([*parts, node.module]) if parts and node.module else None
        if not module or (module != prefix and not module.startswith(prefix + ".")):
            return _comment_lines(buf), set()
        binds = {
            f"{alias.asname or alias.name} = _rs_shared"
            for alias in node.names
            if f"{module}.{alias.name}" in known
        }
        return _comment_lines(buf), binds

    return _comment_lines(buf), set()


def _strip_internal_imports_ex(
    content: str,
    prefix: str,
    known: set[str] | None = None,
    mod_name: str = "",
) -> tuple[str, set[str]]:
    """Comment/rewrite internal imports, returning hoisted namespace binds."""
    lines = content.splitlines()
    out: list[str] = []
    binds: set[str] = set()
    buf: list[str] = []
    in_block = False

    for line in lines:
        if not in_block and _is_internal_import_line(line, prefix):
            buf = [line]
            in_block = True
        elif in_block:
            buf.append(line)

        if in_block:
            if _statement_open("\n".join(buf)):
                continue
            inline, statement_binds = _rewrite_or_comment(buf, known or set(), mod_name, prefix)
            out.extend(inline)
            binds.update(statement_binds)
            buf = []
            in_block = False
        else:
            out.append(line)

    if buf:
        inline, statement_binds = _rewrite_or_comment(buf, known or set(), mod_name, prefix)
        out.extend(inline)
        binds.update(statement_binds)
    return "\n".join(out), binds


def strip_internal_imports(
    content: str,
    prefix: str,
    known: set[str] | None = None,
    mod_name: str = "",
) -> str:
    """Rewrite internal imports so the flat output stays importable."""
    text, _ = _strip_internal_imports_ex(content, prefix, known, mod_name)
    return text


def read_module_content(
    file_path: Path,
    package_root: Path,
    prefix: str,
    no_comment: bool = False,
    known: set[str] | None = None,
    mod_name: str = "",
) -> tuple[str, list[str], set[str]]:
    """Read and preprocess a module for consolidation.

    Returns ``(content, future_imports, binds)``: the ``__future__`` imports
    are extracted for re-emission at the top of the file, and ``binds`` are the
    namespace-binding lines that must be hoisted before any module body runs.
    """
    content = file_path.read_text(encoding="utf-8")
    future_imports = re.findall(r"^from __future__ import .+$", content, flags=re.MULTILINE)
    content = re.sub(r"^#!.*\n", "", content)
    content = re.sub(r"^# -\*- coding:.*-\*-\n?", "", content)
    content = re.sub(r"^from __future__ import .+$\n?", "", content, flags=re.MULTILINE)
    if no_comment or not prefix:
        return content, future_imports, set()
    content, binds = _strip_internal_imports_ex(content, prefix, known, mod_name)
    return content, future_imports, binds


def _is_noop(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    return bool(isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))


def _is_main_test(node: ast.AST) -> bool:
    """True for ``__name__ == "__main__"`` (in either order)."""
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    left, op, right = node.left, node.ops[0], node.comparators[0]
    main_name = isinstance(left, ast.Name) and left.id == "__name__"
    string_right = isinstance(right, ast.Constant) and right.value == "__main__"
    string_left = isinstance(left, ast.Constant) and left.value == "__main__"
    name_right = isinstance(right, ast.Name) and right.id == "__name__"
    return (main_name and string_right or string_left and name_right) and isinstance(op, ast.Eq)


def _find_main_blocks(tree: ast.Module) -> list[ast.If]:
    """Top-level ``if __name__ == "__main__":`` blocks that would break a library."""
    blocks: list[ast.If] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.If) and _is_main_test(stmt.test) and any(
            not _is_noop(s) for s in stmt.body
        ):
            blocks.append(stmt)
    return blocks


def _entry_candidates(
    entry: str, package_root: Path, package_name: str
) -> list[str]:
    """Dotted-name candidates for a manifest ``entry`` (name or path form).

    Path-form entries (e.g. ``pkg/__init__.py``) may be written relative to
    either the package root or the project root; emit both candidates and let
    the caller pick the one that exists.
    """
    normalized = entry.replace("\\", "/")
    if "/" not in normalized:
        base = normalized[:-3] if normalized.endswith(".py") else normalized
        return [base if base.startswith(package_name) else f"{package_name}.{base}"]
    path = normalized[:-3] if normalized.endswith(".py") else normalized
    candidates: list[str] = []
    for base_path in (package_root, package_root.parent):
        try:
            candidates.append(module_dotted_name(base_path / path, package_root, package_name))
        except ValueError:
            continue
    return candidates


def _module_is_no_comment(
    file_path: Path,
    package_root: Path,
    package_name: str,
    no_comment: tuple[str, ...],
) -> bool:
    dotted = module_dotted_name(file_path, package_root, package_name)
    rel = file_path.relative_to(package_root).as_posix()
    rel_stem = rel[:-3] if rel.endswith(".py") else rel
    return any(dotted == item or rel == item or rel_stem == item for item in no_comment)


def consolidate(config: BuildConfig) -> ConsolidateResult:
    """Consolidate ``config.package_root`` into ``config.output``."""
    files = collect_python_files(config.package_root, config.exclude)
    if not files:
        raise ConsolidateError(
            f"no Python files found under {config.package_root} "
            f"(checked exclude patterns: {', '.join(config.exclude) or 'none'})"
        )

    known = {
        module_dotted_name(f, config.package_root, config.package_name): f
        for f in files
    }
    if config.entry:
        entry = next(
            (
                candidate
                for candidate in _entry_candidates(
                    config.entry, config.package_root, config.package_name
                )
                if candidate in known
            ),
            None,
        )
        if entry is None:
            raise ConsolidateError(f"consolidate.entry '{config.entry}' is not a module in the package")
        config.entry = entry

    for file_path in files:
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise ConsolidateError(f"cannot parse {file_path}: {exc}") from exc
        if _find_main_blocks(tree):
            raise ConsolidateError(
                f"module {file_path} has a standalone 'if __name__ == \"__main__\"' "
                "block; the consolidated output must be an importable library"
            )

    names_to_deps = {
        module_dotted_name(f, config.package_root, config.package_name): local_file_dependencies(
            f, config.package_root, config.package_name, set(known)
        )
        for f in files
    }
    ordered, cycles = order_modules(names_to_deps)

    all_imports: set[str] = set()
    all_future: set[str] = set()
    for file_path in files:
        all_imports.update(extract_imports(file_path))
        for future in re.findall(
            r"^from __future__ import .+$",
            file_path.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        ):
            all_future.add(future)

    output_lines: list[str] = []
    output_lines.append('"""')
    output_lines.append(f"{config.package_name} - Consolidated single-file module for DaVinci Resolve.")
    output_lines.append("")
    output_lines.append("This file is auto-generated by 'resolvescript build'/'consolidate'.")
    output_lines.append(
        "Do not edit directly - edit the source modules under "
        f"{config.package_root.as_posix()} instead."
    )
    output_lines.append('"""')
    output_lines.append("")

    if all_future:
        for future in sorted(all_future):
            output_lines.append(future)
        output_lines.append("")

    if config.noqa:
        output_lines.append("# ruff: noqa: E402,F401,F403,F405")
        output_lines.append("# flake8: noqa: E402,F401,F403,F405")
        output_lines.append("")

    root = config.package_root
    bindings: set[str] = set()
    processed: list[tuple[str, str]] = []
    for mod in ordered:
        file_path = known[mod]
        no_comment = _module_is_no_comment(
            file_path, root, config.package_name, config.no_comment
        )
        content, _, binds = read_module_content(
            file_path,
            root,
            config.package_name,
            no_comment,
            known=set(known),
            mod_name=mod,
        )
        bindings.update(binds)
        processed.append((mod, content))

    if bindings:
        output_lines.append("import sys as _rs_sys")
        output_lines.append("_rs_shared = _rs_sys.modules[__name__]")
        output_lines.extend(sorted(bindings))
        output_lines.append("")

    stdlib_imports = sorted(all_imports & STDLIB_MODULES)
    if stdlib_imports:
        output_lines.append("# Standard library imports")
        output_lines.extend(f"import {name}" for name in stdlib_imports)
        output_lines.append("")

    for mod, content in processed:
        output_lines.append(f"# ==== Module: {mod} ====")
        output_lines.append(content)
        output_lines.append("")

    text = "\n".join(output_lines).rstrip() + "\n"
    config.output.parent.mkdir(parents=True, exist_ok=True)
    config.output.write_text(text, encoding="utf-8")

    try:
        compile(text, str(config.output), "exec")
    except SyntaxError as exc:
        raise ConsolidateError(f"consolidated output failed syntax check: {exc}") from exc

    logger.info("consolidated %d modules -> %s (%d bytes)", len(ordered), config.output, len(text))

    return ConsolidateResult(
        output=config.output,
        modules=tuple(ordered),
        cycles=cycles,
        size=config.output.stat().st_size,
    )


class _ManifestLike(Protocol):
    """The slice of a Manifest that ``config_from_manifest`` actually reads."""

    name: str
    @property
    def default_package_dir(self) -> str:
        """Where this manifest's package lives, relative to the project root."""
        ...  # pragma: no cover - protocol placeholder
    consolidate: ConsolidateConfig


def config_from_manifest(
    project_root: Path,
    manifest: _ManifestLike,
    output_override: Path | None = None,
) -> BuildConfig:
    """Build a :class:`BuildConfig` from a manifest's ``consolidate`` section.

    The ``manifest`` argument only needs the ``name``, ``package_dir`` and
    ``consolidate`` attributes, so no manifest module import is required here.
    """
    consolidate_cfg = manifest.consolidate
    package_root = project_root / manifest.default_package_dir
    if not package_root.is_dir():
        package_root = project_root
    output = output_override or project_root / "dist" / (consolidate_cfg.output or f"{manifest.name}.py")
    return BuildConfig(
        package_root=package_root,
        output=output,
        entry=consolidate_cfg.entry,
        exclude=tuple(consolidate_cfg.exclude),
        no_comment=tuple(consolidate_cfg.no_comment),
    )


def summarize(result: ConsolidateResult, config: BuildConfig) -> str:
    """Human-readable one-liner summary for CLI output."""
    note = " (circular deps emitted in sorted order)" if result.cycles else ""
    return (
        f"Consolidated {len(result.modules)} module(s) into {result.output} "
        f"({result.size} bytes){note}"
    )
