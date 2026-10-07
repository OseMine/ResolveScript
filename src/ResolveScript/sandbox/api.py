"""Mock DaVinci Resolve / Fusion API objects for headless development.

The classes here mirror the surface area a Resolve script actually touches:
Resolve connection, project management, timelines, clips, the media pool,
and a Fusion comp (tools, splines, strokes). They are intentionally small —
enough to be useful, not a full emulation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_SPLINE_TYPES = ("BSpline", "Polyline")


class FakeResolve:
    def __init__(self, project_manager: Any):
        self._pm = project_manager

    def GetProjectManager(self) -> Any:
        return self._pm

    def __repr__(self) -> str:
        return "<FakeResolve>"


class FakeFusion:
    def __init__(self, comp: Any):
        self._comp = comp

    def GetCurrentComp(self) -> Any:
        return self._comp

    def __repr__(self) -> str:
        return "<FakeFusion>"


class FakeProjectManager:
    def __init__(self, projects: dict[str, Any], current: str):
        self._projects = projects
        self._current = current

    def GetCurrentProject(self) -> Any:
        return self._projects.get(self._current)

    def GetProject(self, name: str) -> Any | None:
        return self._projects.get(name)

    def GetProjectList(self) -> list[str]:
        return list(self._projects)

    def __repr__(self) -> str:
        return f"<FakeProjectManager projects={list(self._projects)}>"


class FakeProject:
    def __init__(self, name: str, timelines: list[Any], media_pool: Any):
        self._name = name
        self._timelines = timelines
        self._media_pool = media_pool
        self._current = 0

    def GetName(self) -> str:
        return self._name

    def GetTimelineCount(self) -> int:
        return len(self._timelines)

    def GetTimelineByIndex(self, index: int) -> Any:
        return self._timelines[index - 1]

    def GetTimelineByName(self, name: str) -> Any | None:
        for timeline in self._timelines:
            if timeline.GetName() == name:
                return timeline
        return None

    def GetCurrentTimeline(self) -> Any:
        return self._timelines[self._current]

    def GetMediaPool(self) -> Any:
        return self._media_pool

    def GetRenderJobList(self) -> list[Any]:
        return []

    def __repr__(self) -> str:
        return f"<FakeProject {self._name!r}>"


class FakeTimeline:
    def __init__(
        self,
        name: str,
        start_frame: int,
        end_frame: int,
        fps: float,
        video_tracks: list[list[Any]],
        audio_tracks: list[list[Any]],
    ):
        self._name = name
        self._start = start_frame
        self._end = end_frame
        self._fps = fps
        self._video = video_tracks
        self._audio = audio_tracks
        self._tc = "01:00:00:00"

    def GetName(self) -> str:
        return self._name

    def GetStartFrame(self) -> int:
        return self._start

    def GetEndFrame(self) -> int:
        return self._end

    def GetSetting(self, key: str) -> Any:
        if key == "timelineFrameRate":
            return self._fps
        return None

    def GetTrackCount(self, track_type: str) -> int:
        return len(self._video if track_type == "video" else self._audio)

    def GetItemListInTrack(self, track_type: str, track_index: int) -> list[Any]:
        tracks = self._video if track_type == "video" else self._audio
        if track_index < 1 or track_index > len(tracks):
            return []
        return list(tracks[track_index - 1])

    def GetTrackName(self, track_type: str, track_index: int) -> str:
        return f"{track_type.capitalize()} Track {track_index}"

    def SetCurrentTimecode(self, timecode: str) -> bool:
        self._tc = timecode
        return True

    def GetCurrentTimecode(self) -> str:
        return self._tc

    def __repr__(self) -> str:
        return f"<FakeTimeline {self._name!r}>"


class FakeClip:
    def __init__(self, name: str, start: int, end: int, media_item: Any):
        self._name = name
        self._start = start
        self._end = end
        self._item = media_item
        self._comps: list[Any] = []

    def GetName(self) -> str:
        return self._name

    def GetStart(self) -> int:
        return self._start

    def GetEnd(self) -> int:
        return self._end

    def GetDuration(self) -> int:
        return self._end - self._start + 1

    def GetMediaPoolItem(self) -> Any:
        return self._item

    def GetFusionCompCount(self) -> int:
        return len(self._comps)

    def GetFusionCompByIndex(self, index: int) -> Any | None:
        if 1 <= index <= len(self._comps):
            return self._comps[index - 1]
        return None

    def AddFusionComp(self) -> Any:
        comp = FakeComp(f"{self._name} Comp {len(self._comps) + 1}")
        self._comps.append(comp)
        return comp

    def __repr__(self) -> str:
        return f"<FakeClip {self._name!r}>"


class FakeMediaPoolItem:
    def __init__(self, name: str, props: dict[str, str] | None = None):
        self._name = name
        self._props = props or {"FPS": "24", "Duration": "100", "Width": "1920", "Height": "1080"}

    def GetName(self) -> str:
        return self._name

    def GetClipProperty(self, key: str) -> str | None:
        return self._props.get(key)

    def SetClipProperty(self, key: str, value: str) -> bool:
        self._props[key] = value
        return True

    def __repr__(self) -> str:
        return f"<FakeMediaPoolItem {self._name!r}>"


class FakeFolder:
    def __init__(self, name: str, clips: list[Any], subfolders: list[Any] | None = None):
        self._name = name
        self._clips = clips
        self._subfolders = subfolders or []

    def GetName(self) -> str:
        return self._name

    def GetClipList(self) -> list[Any]:
        return list(self._clips)

    def GetSubFolderList(self) -> list[Any]:
        return list(self._subfolders)


class FakeMediaPool:
    def __init__(self, root: Any):
        self._root = root

    def GetRootFolder(self) -> Any:
        return self._root

    def ImportMedia(self, file_paths: list[str]) -> list[Any]:
        return [FakeMediaPoolItem(Path(p).stem) for p in file_paths]


class FakeKey:
    def __init__(self, frame: int, x: float, y: float):
        self.Frame = frame
        self.X = x
        self.Y = y


class FakeSpline:
    def __init__(self) -> None:
        self._keys: dict[int, FakeKey] = {}

    def AddKey(self, frame: int, value: dict[str, float]) -> None:
        self._keys[frame] = FakeKey(frame, value.get("X", 0.0), value.get("Y", 0.0))

    def DeleteKey(self, frame: int) -> None:
        self._keys.pop(frame, None)

    def DeleteAllKeys(self) -> None:
        self._keys.clear()

    def GetKeyCount(self) -> int:
        return len(self._keys)

    def GetKey(self, index: int) -> FakeKey:
        ordered = sorted(self._keys.values(), key=lambda k: k.Frame)
        return ordered[index]


class FakeStroke:
    def __init__(self, number: int):
        self._attrs = {
            "TOOLS_Name": f"Stroke_{number}",
            "BrushType": "Stroke",
            "BrushColor": (1.0, 1.0, 1.0, 1.0),
            "BrushSize": 10.0,
            "TOOLB_StartFrame": 0,
            "TOOLB_EndFrame": 0,
        }
        self._points: list[tuple[float, float, float]] = []

    def SetAttrs(self, attrs: dict[str, Any]) -> None:
        self._attrs.update(attrs)

    def GetAttrs(self) -> dict[str, Any]:
        return dict(self._attrs)

    def AddPoint(self, x: float, y: float, frame: float) -> None:
        self._points.append((x, y, frame))
        int_frame = int(frame)
        prev_start = self._attrs.get("TOOLB_StartFrame") or int_frame
        prev_end = self._attrs.get("TOOLB_EndFrame") or int_frame
        self._attrs["TOOLB_StartFrame"] = min(prev_start, int_frame)
        self._attrs["TOOLB_EndFrame"] = max(prev_end, int_frame)


class FakeTool:
    def __init__(self, regid: str, name: str, x: float, y: float):
        self._attrs = {
            "TOOLS_Name": name,
            "TOOLS_RegID": regid,
            "TOOLS_PosX": x,
            "TOOLS_PosY": y,
        }
        self._spline = FakeSpline() if regid in _SPLINE_TYPES else None
        self._strokes: dict[str, Any] = {}

    def GetAttrs(self) -> dict[str, Any]:
        return dict(self._attrs)

    def SetAttrs(self, attrs: dict[str, Any]) -> None:
        self._attrs.update(attrs)

    def GetInput(self, name: str) -> Any:
        return self._spline if name == "Spline" else None

    def GetInputList(self) -> dict[str, Any]:
        return {}

    def GetOutputList(self) -> dict[str, Any]:
        return {}

    def SetInput(self, index: int | str, value: Any) -> bool:
        return True

    def ConnectInput(self, index: int | str, source: Any) -> bool:
        self._attrs.setdefault("_connected", {})[index] = source
        return True

    def AddStroke(self) -> Any:
        stroke = FakeStroke(len(self._strokes) + 1)
        self._strokes[f"Stroke{len(self._strokes) + 1}"] = stroke
        return stroke

    def GetStrokeList(self) -> dict[str, Any]:
        return dict(self._strokes)

    def DeleteStroke(self, stroke: Any) -> None:
        for key, value in list(self._strokes.items()):
            if value is stroke:
                del self._strokes[key]

    def __repr__(self) -> str:
        return f"<FakeTool {self._attrs['TOOLS_Name']!r} {self._attrs['TOOLS_RegID']}>"


class FakeComp:
    def __init__(
        self,
        name: str,
        width: int = 1920,
        height: int = 1080,
        fps: float = 24.0,
        start: int = 0,
        end: int = 100,
    ):
        self._attrs = {
            "COMPS_Name": name,
            "COMPS_Width": width,
            "COMPS_Height": height,
            "COMPS_FrameRate": fps,
            "COMPS_RenderStart": start,
            "COMPS_RenderEnd": end,
        }
        self._tools: dict[str, Any] = {}
        self._counters: dict[str, int] = {}

    def GetAttrs(self) -> dict[str, Any]:
        return dict(self._attrs)

    def SetAttrs(self, attrs: dict[str, Any]) -> None:
        self._attrs.update(attrs)

    def GetToolList(self, tool_type: str | None = None) -> dict[str, Any]:
        if tool_type is None:
            return dict(self._tools)
        return {
            name: tool
            for name, tool in self._tools.items()
            if tool.GetAttrs()["TOOLS_RegID"] == tool_type
        }

    def AddTool(self, tool_type: str, x: float = 0, y: float = 0) -> Any:
        self._counters[tool_type] = self._counters.get(tool_type, 0) + 1
        name = f"{tool_type}{self._counters[tool_type]}"
        tool = FakeTool(tool_type, name, x, y)
        self._tools[name] = tool
        return tool

    def DeleteTool(self, tool: Any) -> None:
        for key, value in list(self._tools.items()):
            if value is tool:
                del self._tools[key]

    def Save(self, path: str | None = None) -> bool:
        return True

    def Close(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"<FakeComp {self._attrs['COMPS_Name']!r}>"


# ============================================================================
# Lua / Workflow Integration / UI Framework Mock Support
# ============================================================================

class FakeUIManager:
    """Mock Fusion UI Manager for building UIs in scripts."""

    def __init__(self):
        self._windows = {}
        self._widgets = {}
        self._counters = {}

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}{self._counters[prefix]}"

    def Window(self, **kwargs) -> FakeUIWindow:
        win = FakeUIWindow(kwargs.get("WindowTitle", "Window"), **kwargs)
        self._windows[win.ID] = win
        return win

    def VGroup(self, **kwargs) -> FakeUIVGroup:
        return FakeUIVGroup(**kwargs)

    def HGroup(self, **kwargs) -> FakeUIHGroup:
        return FakeUIHGroup(**kwargs)

    def Label(self, **kwargs) -> FakeUILabel:
        return FakeUILabel(kwargs.get("Text", ""), **kwargs)

    def Button(self, **kwargs) -> FakeUIButton:
        return FakeUIButton(kwargs.get("Text", ""), **kwargs)

    def LineEdit(self, **kwargs) -> FakeUILineEdit:
        return FakeUILineEdit(kwargs.get("Text", ""), **kwargs)

    def ComboBox(self, **kwargs) -> FakeUIComboBox:
        return FakeUIComboBox(**kwargs)

    def CheckBox(self, **kwargs) -> FakeUICheckBox:
        return FakeUICheckBox(kwargs.get("Text", ""), **kwargs)

    def Slider(self, **kwargs) -> FakeUISlider:
        return FakeUISlider(**kwargs)

    def ColorPicker(self, **kwargs) -> FakeUIColorPicker:
        return FakeUIColorPicker(**kwargs)

    def VGap(self, **kwargs) -> FakeUIVGap:
        return FakeUIVGap(**kwargs)

    def HGap(self, **kwargs) -> FakeUIHGap:
        return FakeUIHGap(**kwargs)


class FakeUIWidget:
    """Base class for all mock UI widgets."""

    def __init__(self, **kwargs):
        self._attrs = kwargs
        self.ID = self._generate_id()
        self._children = []
        self._event_handlers = {}
        self._visible = True

    def _generate_id(self) -> str:
        import uuid
        return str(uuid.uuid4())[:8]

    def SetAttrs(self, attrs: dict) -> None:
        self._attrs.update(attrs)

    def GetAttrs(self) -> dict:
        return dict(self._attrs)

    def AddChild(self, child: FakeUIWidget) -> None:
        self._children.append(child)
        child._parent = self

    def Show(self) -> None:
        self._visible = True

    def Hide(self) -> None:
        self._visible = False

    def Close(self) -> None:
        self._visible = False

    def on(self, event: str, handler) -> None:
        self._event_handlers[event] = handler

    def emit(self, event: str, *args) -> None:
        if event in self._event_handlers:
            self._event_handlers[event](*args)


class FakeUIWindow(FakeUIWidget):
    def __init__(self, title: str, **kwargs):
        kwargs["WindowTitle"] = title
        super().__init__(**kwargs)
        self._layout = None

    def SetLayout(self, layout) -> None:
        self._layout = layout
        if hasattr(layout, "Show"):
            layout.Show()


class FakeUILayout(FakeUIWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._items = []

    def Add(self, widget, **kwargs) -> None:
        self._items.append((widget, kwargs))
        widget.AddChild(self)


class FakeUIVGroup(FakeUILayout):
    pass


class FakeUIHGroup(FakeUILayout):
    pass


class FakeUILabel(FakeUIWidget):
    def __init__(self, text: str = "", **kwargs):
        kwargs["Text"] = text
        super().__init__(**kwargs)


class FakeUIButton(FakeUIWidget):
    def __init__(self, text: str = "", **kwargs):
        kwargs["Text"] = text
        super().__init__(**kwargs)
        self._clicked = False

    def Click(self) -> None:
        self._clicked = True
        self.emit("clicked")


class FakeUILineEdit(FakeUIWidget):
    def __init__(self, text: str = "", **kwargs):
        kwargs["Text"] = text
        super().__init__(**kwargs)


class FakeUIComboBox(FakeUIWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._items = kwargs.get("Items", [])

    def AddItem(self, item: str) -> None:
        self._items.append(item)

    def GetCurrentIndex(self) -> int:
        return self._attrs.get("CurrentIndex", 0)


class FakeUICheckBox(FakeUIWidget):
    def __init__(self, text: str = "", **kwargs):
        kwargs["Text"] = text
        super().__init__(**kwargs)

    def IsChecked(self) -> bool:
        return self._attrs.get("Checked", False)

    def SetChecked(self, checked: bool) -> None:
        self._attrs["Checked"] = checked


class FakeUISlider(FakeUIWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def GetValue(self) -> float:
        return self._attrs.get("Value", 0.0)


class FakeUIColorPicker(FakeUIWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class FakeUIVGap(FakeUIWidget):
    def __init__(self, size: int = 10, **kwargs):
        kwargs["Size"] = size
        super().__init__(**kwargs)


class FakeUIHGap(FakeUIWidget):
    def __init__(self, size: int = 10, **kwargs):
        kwargs["Size"] = size
        super().__init__(**kwargs)


class FakeWorkflowIntegration:
    """Mock workflow integration for testing workflow scripts."""

    def __init__(self, name: str):
        self.name = name
        self.menu_name = name
        self.type = "timeline"
        self.hotkey = ""
        self.toolbar = True
        self._visible = False
        self._callbacks = {}

    def Show(self) -> None:
        self._visible = True

    def Hide(self) -> None:
        self._visible = False

    def IsVisible(self) -> bool:
        return self._visible

    def RegisterCallback(self, event: str, callback) -> None:
        self._callbacks[event] = callback

    def TriggerCallback(self, event: str, *args) -> Any:
        if event in self._callbacks:
            return self._callbacks[event](*args)
        return None


class FakeResolveWithWorkflow(FakeResolve):
    """Extended FakeResolve with workflow integration support."""

    def __init__(self, project_manager: Any):
        super().__init__(project_manager)
        self._workflows = {}

    def GetWorkflowIntegration(self, name: str) -> FakeWorkflowIntegration:
        if name not in self._workflows:
            self._workflows[name] = FakeWorkflowIntegration(name)
        return self._workflows[name]

    def RegisterWorkflowIntegration(self, workflow: FakeWorkflowIntegration) -> None:
        self._workflows[workflow.name] = workflow


# Mock Lua-style bmd module (DaVinci Resolve's Lua API)
class MockBMD:
    """Mock bmd module for Lua scripts."""

    def __init__(self):
        self.scriptapp = lambda name: _mock_scriptapp(name)

    def Version(self):
        return "18.6.4"


def _mock_scriptapp(name: str):
    """Mock scriptapp function for bmd module."""
    if name == "Resolve":
        from ResolveScript.sandbox.env import build_default_env
        return build_default_env()[0]  # Returns (resolve, fusion)
    if name == "Fusion":
        from ResolveScript.sandbox.env import build_default_env
        return build_default_env()[1]  # Returns (resolve, fusion)
    return None


# Lua globals that Resolve injects
LUA_GLOBALS = {
    "bmd": MockBMD(),
    "dvr_script": None,  # Will be set by install_fake_resolve
    "fusion": None,
    "resolve": None,
    "comp": None,
    "tool": None,
    "clipr": None,
    "timeline": None,
    "project": None,
}
