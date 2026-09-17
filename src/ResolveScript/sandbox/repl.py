"""Interactive REPL namespace for the sandbox."""

from __future__ import annotations

import code
from types import ModuleType
from typing import Any

from .api import FakeProject, FakeResolve


def _collect_clips(project: FakeProject) -> list[Any]:
    clips: list[Any] = []
    seen: set[int] = set()
    for index in range(1, project.GetTimelineCount() + 1):
        timeline = project.GetTimelineByIndex(index)
        for track in range(1, timeline.GetTrackCount("video") + 1):
            for clip in timeline.GetItemListInTrack("video", track):
                if clip is None or id(clip) in seen:
                    continue
                seen.add(id(clip))
                clips.append(clip)
    return clips


def default_namespace(module: ModuleType, resolve: FakeResolve | None = None) -> dict[str, Any]:
    """Build the interactive namespace: ``resolve``, ``project``, ``timeline``,
    ``clips`` and the loaded module under its own name."""
    if resolve is None:
        import sys

        from .env import FUSION_SCRIPT_MODULE

        dvr = sys.modules.get(FUSION_SCRIPT_MODULE)
        resolve = dvr.scriptapp("Resolve") if dvr is not None else None  # type: ignore[attr-defined]
    namespace: dict[str, Any] = {}
    if resolve is not None:
        namespace["resolve"] = resolve
        project = resolve.GetProjectManager().GetCurrentProject()
        if project is not None:
            namespace["project"] = project
            namespace["timeline"] = project.GetCurrentTimeline()
            namespace["clips"] = _collect_clips(project)
    namespace[module.__name__] = module
    return namespace


def start_repl(module: ModuleType, resolve: FakeResolve | None = None) -> None:
    """Drop into an interactive interpreter with a live mock session."""
    namespace = default_namespace(module, resolve)
    banner = (
        "\nInteractive sandbox. Available:\n"
        f"  {module.__name__}  - the package under test\n"
        "  resolve / project / timeline\n"
        "  clips      - list of clips across the timeline video tracks\n"
    )
    code.interact(local=namespace, banner=banner)
