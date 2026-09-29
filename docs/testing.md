# Testing with Mock Resolve API

ResolveScript provides a **complete mock Resolve API** for unit testing without a running DaVinci Resolve instance.

## Quick Start

```bash
# Scaffolded projects include tests/
resolvescript create my_script --template minimal
cd my_script
resolvescript test
```

## The Mock API

The mock (`ResolveScript.sandbox.api`) implements:

| Module | Mocked |
|--------|--------|
| `resolve` | `GetProjectManager()`, `GetAppVersion()`, `GetAppUUID()` |
| `fusion` | `GetCurrentComp()`, `UIManager`, `UIDispatcher` |
| `bmd` | Constants, `UIDispatcher` |
| `ProjectManager` | `GetCurrentProject()`, `CreateProject()` |
| `Project` | `GetName()`, `GetRenderJobList()`, `AddRenderJob()` |
| `Composition` | `GetToolList()`, `AddTool()`, `CurrentFrame` |
| `Tool` | `GetInput()`, `SetInput()`, `GetOutput()`, `FindMainInput()` |
| `Clip` | `GetClipProperty()`, `GetDuration()` |
| `MediaPool` | `GetRootFolder()`, `AddFolder()`, `ImportMedia()` |

## Writing Tests

```python
# tests/test_my_feature.py
import pytest
from ResolveScript.sandbox import get_mock_resolve

def test_project_creation():
    resolve = get_mock_resolve()
    pm = resolve.GetProjectManager()
    project = pm.CreateProject("Test Project")
    
    assert project.GetName() == "Test Project"
    assert pm.GetCurrentProject() is project

def test_composition_tools():
    resolve = get_mock_resolve()
    pm = resolve.GetProjectManager()
    project = pm.CreateProject("Test")
    comp = project.GetCurrentComposition()
    
    # AddTool returns a mock tool
    tool = comp.AddTool("Text", -32768, -32768)
    tool.SetInput("Text", "Hello")
    assert tool.GetInput("Text") == "Hello"

def test_media_pool():
    resolve = get_mock_resolve()
    pm = resolve.GetProjectManager()
    project = pm.CreateProject("Test")
    pool = project.GetMediaPool()
    root = pool.GetRootFolder()
    
    folder = pool.AddFolder(root, "Footage")
    assert folder.GetName() == "Footage"
```

## Test Helpers

### `resolve` fixture (built-in)

```python
# conftest.py (scaffolded)
@pytest.fixture
def resolve():
    from ResolveScript.sandbox import get_mock_resolve
    return get_mock_resolve()
```

```python
def test_with_fixture(resolve):
    project = resolve.GetProjectManager().CreateProject("X")
    assert project.GetName() == "X"
```

### `clip` / `bin` / `pool` helpers

```python
from ResolveScript.sandbox.api import Clip, Bin

def test_clip_properties():
    clip = Clip("shot_001", duration=120, fps=24)
    assert clip.GetClipProperty("Duration") == "120"
    assert clip.GetClipProperty("FPS") == "24"
```

### `rows()` for tree assertions

```python
from ResolveScript.ui.rows import rows, call, maybe

def test_tool_tree():
    from ResolveScript.sandbox.api import Clip
    clip = Clip("test", metadata={"scene": "01", "take": "02"})
    
    # Extract specific fields
    data = rows(clip, ["GetName", "GetDuration", maybe("GetClipProperty")])
    assert data[0]["GetName"] == "test"
```

## Running Tests

```bash
# All tests
resolvescript test

# Verbose
resolvescript test -v

# Specific test
resolvescript test -k "test_menu"

# With coverage
resolvescript test --cov=my_script --cov-report=term-missing

# In CI
resolvescript test -q --tb=short
```

## Mock Behavior

| Feature | Behavior |
|---------|----------|
| **Tool inputs** | Stored in dict, `SetInput`/`GetInput` round-trip |
| **Compositions** | Each project gets one current composition |
| **Render jobs** | In-memory list, `AddRenderJob` appends |
| **MediaPool** | Tree of `Bin`/`Clip` objects |
| **UIManager** | `MockBackend` for headless testing |
| **UIDispatcher** | Simulated event loop |

## Extending the Mock

```python
# tests/conftest.py
from ResolveScript.sandbox.api import FakeResolve, FakeProject

class MyFakeProject(FakeProject):
    def GetCustomData(self):
        return {"custom": "value"}

class MyFakeResolve(FakeResolve):
    def GetProjectManager(self):
        pm = super().GetProjectManager()
        pm._project_class = MyFakeProject
        return pm

@pytest.fixture
def resolve():
    return MyFakeResolve()
```

## Limitations

| Not Mocked | Workaround |
|------------|------------|
| GPU/OpenCL | Use CPU fallbacks in code |
| File I/O (renders) | Mock `AddRenderJob` return |
| Network | Mock at application layer |
| Real UI events | Use `MockBackend` for UI tests |

## Best Practices

1. **Test logic, not the mock** — Verify your code calls the right APIs
2. **Use `rows()` for complex objects** — Readable assertions on Clip/Tool/Bin
3. **Isolate tests** — Each test gets fresh mock state
4. **Don't mock the mock** — Extend `FakeResolve` instead of patching
5. **Run in CI** — `resolvescript test` needs no Resolve install

## UI Testing

```python
from ResolveScript.ui import MockBackend, run, Window, Button, Value

def test_button_click():
    backend = MockBackend()
    clicked = Value(False)
    
    def on_click(ev):
        clicked.set(True)
    
    run(Window("Test", children=[Button("Click", on_click=on_click)]), backend=backend)
    
    btn = backend.require("Button")
    backend.fire(btn, "Clicked")
    assert clicked.get() is True
```