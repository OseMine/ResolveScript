"""Environment injection: build a mock Resolve session and install it.

``install_fake_resolve`` registers a fake ``DaVinciResolveScript`` module in
``sys.modules`` so any extension that does ``import DaVinciResolveScript`` runs
headless. It is idempotent — calling it again just replaces the module.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from .api import (
    FakeClip,
    FakeComp,
    FakeFolder,
    FakeFusion,
    FakeMediaPool,
    FakeMediaPoolItem,
    FakeProject,
    FakeProjectManager,
    FakeResolve,
    FakeTimeline,
)

FUSION_SCRIPT_MODULE = "DaVinciResolveScript"

DEFAULT_PROJECT = "Demo Project"


def build_default_env() -> tuple[FakeResolve, FakeFusion]:
    """Create a realistic mock session with clips, timelines and a Fusion comp."""
    items = {f"Shot {i}": FakeMediaPoolItem(f"Shot {i}") for i in range(1, 7)}

    def _clip(name: str, start: int, end: int) -> FakeClip:
        return FakeClip(name, start, end, items[name])

    video_1 = [
        _clip("Shot 1", 1001, 1040),
        None,
        _clip("Shot 3", 1061, 1100),
    ]
    video_2 = [
        _clip("Shot 2", 1001, 1040),
        _clip("Shot 4", 1120, 1180),
    ]
    audio_1 = [
        _clip("Shot 5", 1001, 1080),
        _clip("Shot 6", 1081, 1180),
    ]

    timeline_1 = FakeTimeline("Main Timeline", 1001, 1200, 24.0, [video_1, video_2], [audio_1])
    timeline_2 = FakeTimeline("Alt Timeline", 2001, 3000, 24.0, [video_2], [audio_1])

    root = FakeFolder("Master", list(items.values()))
    media_pool = FakeMediaPool(root)
    project = FakeProject(DEFAULT_PROJECT, [timeline_1, timeline_2], media_pool)
    pm = FakeProjectManager({DEFAULT_PROJECT: project}, DEFAULT_PROJECT)

    resolve = FakeResolve(pm)
    fusion = FakeFusion(FakeComp("Comp 1", start=1001, end=1200))
    return resolve, fusion


def fake_resolve_module() -> ModuleType:
    """Build (but do not install) a fake DaVinciResolveScript module."""
    resolve, fusion = build_default_env()
    module = ModuleType(FUSION_SCRIPT_MODULE)

    def _scriptapp(kind: str) -> Any:
        return resolve if kind == "Resolve" else fusion

    module.scriptapp = _scriptapp  # type: ignore[attr-defined]
    return module


def install_fake_resolve() -> ModuleType:
    """Register the fake DaVinciResolveScript module (idempotent)."""
    module = fake_resolve_module()
    sys.modules[FUSION_SCRIPT_MODULE] = module
    return module
