"""Print the generated @NAME_LABEL@ fuse, without installing it.

    python -m @NAME@.fuse            # write dist/<Class>.fuse
    python -m @NAME@.fuse --print    # write it to stdout instead
    python -m @NAME@.fuse --check    # only validate; prints what was checked

Fusion loads the ``.fuse`` file, not this module — it is the declaration, and
this is the quickest way to see exactly what ``resolvescript fuse build`` will
write. A build validates the result with a real Lua parser when one is
installed, and ``--check`` reports which of the two checks actually ran.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ResolveScript.fuse import build, checked_with, problems, render_fuse

from .fuse import FUSE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=f"{FUSE.class_name.lower()}-fuse")
    parser.add_argument("-o", "--output", help="directory to write into (default: dist)")
    parser.add_argument("--print", dest="to_stdout", action="store_true", help="write to stdout")
    parser.add_argument(
        "--check", action="store_true", help="validate only; do not write anything"
    )
    args = parser.parse_args(argv)

    if args.to_stdout:
        sys.stdout.write(render_fuse(FUSE))
        return 0

    found = problems(FUSE)
    for line in found:
        print(f"{FUSE.class_name}.fuse: {line}", file=sys.stderr)
    if found:
        return 1
    if args.check:
        print(f"{FUSE.class_name}.fuse: no problems found (nothing written)")
        return 0

    destination = Path(args.output) if args.output else Path.cwd() / "dist"
    result = build(FUSE, destination)
    for line in result.describe():
        print(line)
    # build() re-checks the file it wrote, which is the one that matters; say so
    # rather than letting the pre-write check stand in for it.
    print(f"verified: {checked_with(result.fuse_file)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
