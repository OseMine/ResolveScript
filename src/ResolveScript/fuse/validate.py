"""Checking a generated ``.fuse`` file before anyone drops it into Fusion.

A fuse is loaded by the *Fusion page inside Resolve*, whose only symptom of a
broken tool is a tool that does not appear in the registry. There is no console,
no stack trace and no error dialog, so a mistake here is invisible until
somebody reports that the menu entry is missing. Everything checkable without
Fusion is therefore checked here, at build time.

Two layers, and it says which one ran
------------------------------------

**Structural** — always. Balanced brackets outside strings and comments, the
three required top-level functions, no unsubstituted template token, and every
port the ``Process`` body touches actually being declared.

**Real parse** — when a Lua interpreter is on ``PATH``. ``luac -p`` is asked to
compile the file, which is the same parser Fusion's own loader uses. Without a
Lua binary the structural layer still runs, and
:func:`checked_with` reports that it was the only layer, so a build never
implies a guarantee it did not verify.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .model import Fuse, FuseError

__all__ = [
    "REQUIRED_FUNCTIONS",
    "check_process_references",
    "check_source",
    "checked_with",
    "lua_compiler",
    "parse_file",
    "problems",
    "validate",
]

#: The three things Fusion calls on a fuse, all at the top level.
REQUIRED_FUNCTIONS: tuple[str, ...] = (
    "FuRegisterClass",
    "function Create",
    "function Process",
)

_TOKEN_RE = re.compile(r"@@[A-Z0-9_]+@@")
_LOCAL_RE = re.compile(r"\blocal\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)")
_PORT_USE_RE = re.compile(r"\b([A-Za-z_]\w*)\s*:\s*(?:GetValue|GetValueEx|Set|GetID)\b")

#: Comment openers. Both are stripped before anything counts brackets, because a
#: bracket inside a comment is not an unbalanced bracket.
_COMMENTS = (
    re.compile(r"--\[\[.*?\]\]", re.DOTALL),
    re.compile(r"--[^\n]*"),
)
_STRINGS = (
    # Long brackets first, and leveled (``[=[ ... ]=]``) as well as plain: a
    # pixel expression written with a level would otherwise be read as code and
    # counted for brackets.
    re.compile(r'"""[\s\S]*?"""'),
    re.compile(r"\[(=*)\[.*?\]\1\]", re.DOTALL),
    re.compile(r'"(?:\\.|[^"\\])*"'),
    re.compile(r"'(?:\\.|[^'\\])*'"),
)


def _strip_noise(source: str) -> str:
    """Remove comments and string literals, keeping offsets stable.

    Everything is replaced with spaces rather than deleted so a bracket count
    still lines up with the original if a problem has to be located.
    """

    def blank(match: re.Match[str]) -> str:
        return " " * len(match.group(0))

    for pattern in (*_COMMENTS, *_STRINGS):
        source = pattern.sub(blank, source)
    return source


def check_source(source: str) -> list[str]:
    """Structural problems in a rendered fuse, as human-readable lines.

    An empty list means the structure looks right. It does **not** mean the file
    is valid Lua — only :func:`parse_file` can say that.
    """
    found: list[str] = []
    if leftover := _TOKEN_RE.findall(source):
        found.append(f"unsubstituted template token(s): {', '.join(sorted(set(leftover)))}")

    for name in REQUIRED_FUNCTIONS:
        if name not in source:
            found.append(f"missing required top-level declaration: {name}")

    code = _strip_noise(source)
    for opener, closer in (("(", ")"), ("{", "}"), ("[", "]")):
        depth_open = code.count(opener)
        depth_close = code.count(closer)
        if depth_open != depth_close:
            found.append(
                f"unbalanced {opener}{closer}: {depth_open} '{opener}' vs "
                f"{depth_close} '{closer}'"
            )
    return found


def check_process_references(fuse: Fuse) -> list[str]:
    """Ports the ``Process`` body uses that :class:`~ResolveScript.fuse.Fuse` does not declare.

    ``InLevels:GetValue(req)`` only resolves if ``InLevels`` is a global that
    ``Create()`` bound, so a body written against a renamed control fails at
    runtime with a nil index. Locals declared in the body are ignored, and so is
    anything that is not a port accessor.
    """
    body = fuse.process
    known = fuse.variables
    declared = set(known)
    local_names: set[str] = set()
    for match in _LOCAL_RE.finditer(body):
        local_names.update(name.strip() for name in match.group(1).split(","))

    unknown = sorted(
        {
            name
            for name in _PORT_USE_RE.findall(body)
            if name not in declared and name not in local_names
        }
    )
    if not unknown:
        return []
    return [
        f"Process references undeclared port(s): {', '.join(unknown)} — "
        f"declared are {', '.join(known)}"
    ]


def lua_compiler() -> str | None:
    """Path to a Lua compiler, or ``None`` when none is installed.

    ``luac -p`` is preferred over ``lua`` because it only parses; ``lua -e
    "assert(loadfile(...))"`` is the same thing spelled out, for installs that
    ship the interpreter without the compiler.
    """
    for name in ("luac", "luajit", "lua"):
        found = shutil.which(name)
        if found:
            return found
    return None


def parse_file(path: str | Path) -> list[str]:
    """Ask a real Lua parser to compile ``path``. Returns problems, or ``[]``.

    Raises :class:`RuntimeError` when no interpreter is installed, so a caller
    can tell "no problems" apart from "nothing was checked" — see
    :func:`checked_with`.
    """
    target = Path(path)
    compiler = lua_compiler()
    if compiler is None:
        raise RuntimeError("no Lua interpreter found on PATH")
    if Path(compiler).stem.lower().startswith(("luac", "luajit")):
        command = [compiler, "-p", str(target)]
    else:
        command = [compiler, "-e", f"assert(loadfile({str(target)!r}))"]
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"could not run {compiler}: {exc}") from exc
    if done.returncode == 0:
        return []
    detail = (done.stderr or done.stdout or "").strip() or f"exit status {done.returncode}"
    return [f"lua: {line}" for line in detail.splitlines()]


def checked_with(path: str | Path) -> str:
    """What the last check at ``path`` actually verified, for honest output."""
    try:
        compiler = lua_compiler()
    except Exception:  # pragma: no cover - which() does not raise in practice
        compiler = None
    if compiler is None:
        return "structure only (no Lua interpreter on PATH)"
    return f"structure + {Path(compiler).stem} parse"


def problems(fuse: Fuse, path: str | Path | None = None) -> list[str]:
    """Everything checkable about a fuse, plus the parse if ``path`` is given.

    :param path: a file to hand to the Lua parser. Omit it to skip that layer —
    useful for checking a declaration before anything is written.
    """
    found = check_process_references(fuse)
    if path is not None:
        source = Path(path).read_text(encoding="utf-8")
        found.extend(check_source(source))
        try:
            found.extend(parse_file(path))
        except RuntimeError:
            # Reported, not swallowed: the structural result stands on its own,
            # and a build that claims more than it checked is worse than one
            # that says so.
            found.append("no Lua interpreter on PATH — checked structure only")
    return found


def validate(fuse: Fuse, path: str | Path | None = None) -> None:
    """Raise :class:`~ResolveScript.fuse.FuseError` if anything is wrong."""
    found = problems(fuse, path)
    if found:
        detail = "\n  ".join(found)
        raise FuseError(f"{fuse.name!r} is not a loadable fuse:\n  {detail}")
