"""Mock Resolve API, environment injection, smoke checks and the REPL.

Typical usage from a test or script::

    from ResolveScript.sandbox.env import install_fake_resolve
    from ResolveScript.sandbox.smoke import run_smoke

    install_fake_resolve()
    result = run_smoke(my_module)
"""

from .api import (
    FakeClip,
    FakeComp,
    FakeFolder,
    FakeFusion,
    FakeKey,
    FakeMediaPool,
    FakeMediaPoolItem,
    FakeProject,
    FakeProjectManager,
    FakeResolve,
    FakeSpline,
    FakeStroke,
    FakeTimeline,
    FakeTool,
)
from .env import (
    DEFAULT_PROJECT,
    FUSION_SCRIPT_MODULE,
    build_default_env,
    fake_resolve_module,
    install_fake_resolve,
)
from .loader import load_built_module, load_source_module, purge_module
from .repl import default_namespace, start_repl
from .smoke import SmokeCheck, SmokeResult, discover_exports, run_smoke

__all__ = [
    "DEFAULT_PROJECT",
    "FUSION_SCRIPT_MODULE",
    "FakeClip",
    "FakeComp",
    "FakeFolder",
    "FakeFusion",
    "FakeKey",
    "FakeMediaPool",
    "FakeMediaPoolItem",
    "FakeProject",
    "FakeProjectManager",
    "FakeResolve",
    "FakeSpline",
    "FakeStroke",
    "FakeTimeline",
    "FakeTool",
    "SmokeCheck",
    "SmokeResult",
    "build_default_env",
    "default_namespace",
    "discover_exports",
    "fake_resolve_module",
    "install_fake_resolve",
    "load_built_module",
    "load_source_module",
    "purge_module",
    "run_smoke",
    "start_repl",
]
