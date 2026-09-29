"""ResolveScript Fuse — building Fusion fuses and deploying compiled plugins.

Two plugin formats, and the difference decides what each one can do
-------------------------------------------------------------------

**``.fuse``** — a *fuse*: one Lua file, named ``ToolName.fuse``, that Fusion
compiles on the fly. This is the one third-party Fusion plugin format you can
actually author, and this package turns a Python declaration into the file::

    from ResolveScript.fuse import Control, Fuse

    FUSE = Fuse(
        name="Posterize",
        description="Reduce an image to a fixed number of levels.",
        inputs=[Control("Levels", kind="SliderControl", minimum=2, maximum=64, default="6")],
        process='''
    local levels = InLevels:GetValue(req).Value
    local out = InImage:GetValue(req):Copy()
    out:DoExpression([=[
        level = max(1, int(level))
        r, g, b, a = map(r, g, b, function(c)
            return min(255, int(c * 255 / level + 0.5) * level / 255)
        end)
    ]=])
    OutImage:Set(req, out)
    ''',
    )

**``.plugin``** — a compiled native plugin: ``Krokodove.plugin`` and its peers.
A platform binary or bundle, produced by Blackmagic's or a vendor's toolchain.
There is no source form this package can turn into one, so every operation on
it is deploy / package / remove. :class:`BinaryPlugin` exists so a project can
ship one next to its fuses without pretending it was built here.

Where they go
-------------

Neither lives in Resolve's Scripts root. Both come from Fusion's PathMap — see
:mod:`ResolveScript.fuse.paths`, where the published locations differ per
application and per platform. Resolve has to be restarted either way: the
registry is built once, at startup.

Checking, because a broken fuse is invisible
--------------------------------------------

A fuse that does not load produces no dialog, no console and no stack trace.
The tool simply is not in the registry menu. So a build checks what it can:
the file's structure always, and a real Lua parse whenever a ``luac`` is on
``PATH``. :func:`checked_with` reports which of the two actually ran, so a
green build never implies more than was verified.
"""

from __future__ import annotations

from .build import (
    REGISTRY_NAME,
    REGISTRY_VERSION,
    BinaryBuildResult,
    FuseBuildResult,
    PackageResult,
    build,
    describe_installed,
    install,
    install_binary,
    list_installed,
    package_fuse,
    render,
    uninstall,
)
from .model import (
    BINARY_SUFFIXES,
    DEFAULT_CATEGORY,
    TOOL_TYPES,
    BinaryPlugin,
    Control,
    Fuse,
    FuseError,
    Output,
)
from .paths import (
    FUSES_DIR_NAME,
    PLUGINS_DIR_NAME,
    FusionPathError,
    candidates,
    default_plugins_root,
    default_root,
    exists,
    list_roots,
    root,
)
from .render import FUSE_EXTENSION, REGISTER_FLAGS, render_fuse
from .validate import (
    REQUIRED_FUNCTIONS,
    check_process_references,
    check_source,
    checked_with,
    lua_compiler,
    parse_file,
    problems,
    validate,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # -- declaring -------------------------------------------------------
    "Fuse",
    "Control",
    "Output",
    "BinaryPlugin",
    "FuseError",
    "DEFAULT_CATEGORY",
    "TOOL_TYPES",
    "BINARY_SUFFIXES",
    # -- rendering -------------------------------------------------------
    "FUSE_EXTENSION",
    "REGISTER_FLAGS",
    "render_fuse",
    # -- writing ---------------------------------------------------------
    "render",
    "build",
    "install",
    "install_binary",
    "package_fuse",
    "FuseBuildResult",
    "BinaryBuildResult",
    "PackageResult",
    # -- installed state -------------------------------------------------
    "list_installed",
    "uninstall",
    "describe_installed",
    "REGISTRY_NAME",
    "REGISTRY_VERSION",
    # -- paths -----------------------------------------------------------
    "FUSES_DIR_NAME",
    "PLUGINS_DIR_NAME",
    "candidates",
    "default_root",
    "default_plugins_root",
    "exists",
    "list_roots",
    "root",
    "FusionPathError",
    # -- checking --------------------------------------------------------
    "REQUIRED_FUNCTIONS",
    "check_source",
    "check_process_references",
    "parse_file",
    "problems",
    "validate",
    "checked_with",
    "lua_compiler",
]
