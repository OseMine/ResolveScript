# Project Templates

ResolveScript scaffolds projects from templates. Each template provides a complete starting structure with manifest, package layout, tests, and CI-ready configuration.

## Available Templates

```bash
resolvescript create --help
# --template {minimal,pydavinci,davinci-rest,lua,workflow,fuse}
```

| Template | Use Case | Language | Manifest |
|----------|----------|----------|----------|
| `minimal` | Basic Python script | Python | JSON |
| `pydavinci` | Type-safe pydavinci wrapper | Python | JSON |
| `davinci-rest` | REST client for remote Resolve | Python | JSON |
| `lua` | Native Lua script | Lua | JSON |
| `workflow` | Workspace > Workflow Integrations | Python + Electron | JSON |
| `fuse` | Fusion `.fuse` plugin | Python (generates Lua) | JSON |

## Template Comparison

```
minimal/
├── manifest.json
├── my_script/
│   ├── __init__.py
│   └── menu.py
├── my_script_main.py
├── pyproject.toml
├── tests/test_smoke.py
└── installer.lua.j2          # For --installable

pydavinci/
├── manifest.json
├── my_script/
│   ├── __init__.py
│   └── menu.py          # Uses pydavinci.resolve
├── my_script_main.py
├── pyproject.toml       # pydavinci dependency
├── tests/test_smoke.py
└── installer.lua.j2

davinci-rest/
├── manifest.json
├── my_script/
│   ├── __init__.py
│   └── menu.py          # Uses davinci_rest.client
├── my_script_main.py
├── pyproject.toml       # davinci-rest dependency
├── tests/test_smoke.py
└── installer.lua.j2

lua/
├── manifest.json
├── my_script_main.lua   # Pure Lua
├── tests/test_smoke.lua
└── README.md            # No installer (Lua doesn't consolidate)

workflow/
├── manifest.json        # kind: "workflow"
├── my_workflow/
│   ├── __init__.py
│   ├── workflow.py      # Integration class
│   └── workflow_workflow.py
├── package.json         # Electron
├── main.js
├── preload.js
├── index.html
├── pyproject.toml
├── tests/test_smoke.py
└── README.md

fuse/
├── manifest.json        # kind: "fuse"
├── my_fuse/
│   ├── __init__.py
│   ├── fuse.py          # FUSE = Fuse(...) declaration
│   └── __main__.py      # CLI: build --stdout, --check, -o
├── conftest.py
├── tests/test_smoke.py  # Validates .fuse output
├── README.md            # Full fuse docs
└── installer.lua.j2     # Not used (fuses don't consolidate)
```

## Manifest Variants

| Template | Manifest | Notes |
|----------|----------|-------|
| `minimal`, `pydavinci`, `davinci-rest` | `.json` or `.xml` | `--fmt json\|xml` |
| `lua`, `workflow`, `fuse` | `.json` only | XML not supported for these kinds |

## Customizing a Scaffolded Project

### 1. Edit the manifest

```json
// manifest.json
{
  "name": "My Script",
  "version": "1.0.0",
  "description": "Does amazing things",
  "author": "Your Name",
  "package_dir": "my_script",
  "consolidate": {
    "enabled": true,
    "output": "my_script.py",
    "entry": "my_script:run",
    "exclude": ["tests/**"]
  }
}
```

### 2. Add dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "requests>=2.31",
    "pydavinci>=0.2",     # for pydavinci template
    "davinci-rest>=0.1",  # for davinci-rest template
]
```

### 3. Customize the installer template

```bash
# For --installable builds
vim installer.lua.j2
# Edit CONFIG table: target_category, overwrite, window_title...
```

### 4. For fuse template — edit the declaration

```python
# my_fuse/fuse.py
from ResolveScript.fuse import Control, Fuse

FUSE = Fuse(
    name="My Fuse",
    category="Fuses\\MyTools",
    icon_string="MFZ",
    tool_type="CT_Tool",
    inputs=[
        Control("Amount", kind="SliderControl", minimum=0, maximum=1, default=0.5),
    ],
    process="""
        local out = InImage:GetValue(req):Copy()
        local amt = InAmount:GetValue(req).Value
        out:DoExpression([=[
            pixel = pixel * (1 - amt) + amt
        ]=])
        OutImage:Set(req, out)
    """,
)
```

## Creating Your Own Template

### 1. Directory structure

```
my_template/
├── @NAME@/                  # Package directory (renamed to project name)
│   ├── __init__.py.j2
│   └── module.py.j2
├── @NAME@_main.py.j2        # Entry point
├── manifest.json.j2         # Or manifest.xml.j2
├── pyproject.toml.j2
├── installer.lua.j2         # If Python template
├── README.md
├── tests/
│   └── test_smoke.py.j2
└── conftest.py              # Shared test config
```

### 2. Placeholders

Use `@KEY@` in any file:

```jinja
# @NAME@/__init__.py.j2
__version__ = "@VERSION@"
__author__ = "@AUTHOR@"
```

### 3. Built-in substitution keys

| Key | Source |
|-----|--------|
| `NAME` | Project name (as passed to `create`) |
| `VERSION` | Default `0.1.0` or `--version` |
| `DESCRIPTION` | `--description` or generated |
| `AUTHOR` | `--author` |
| `RESOLVESCRIPT_VERSION` | Current ResolveScript version |
| `ID` | Reverse-DNS: `com.resolvescript.<slug>` |
| `NAME_LABEL` | Title-cased label |
| `CLASS_NAME` | PascalCase (fuse template) |
| `ICON` | First 3 letters capitalized (fuse template) |

### 4. Register the template

Add to `src/ResolveScript/scaffold.py`:

```python
template_map = {
    # ... existing ...
    "my_template": "my_template",
}
```

### 5. Template directory location

```
src/ResolveScript/templates/my_template/
```

## Template Best Practices

| Practice | Reason |
|----------|--------|
| Include `tests/test_smoke.py` | Verifies scaffold works |
| Add `conftest.py` with `resolve` fixture | Enables `resolvescript test` |
| Include `installer.lua.j2` for Python templates | Enables `--installable` |
| Use `@@TOKEN@@` in Lua templates | Consistent with workflow/fuse |
| Keep `pyproject.toml` minimal | Users add deps as needed |
| Document template in `README.md` | Self-documenting |

## Example: Minimal Template Files

```jinja
# manifest.json.j2
{
  "name": "@NAME@",
  "version": "@VERSION@",
  "description": "@DESCRIPTION@",
  "author": "@AUTHOR@",
  "package_dir": "@NAME@",
  "consolidate": {
    "enabled": true,
    "output": "@NAME@.py",
    "entry": "@NAME@:main"
  }
}
```

```jinja
# @NAME@/menu.py.j2
from ResolveScript.sandbox import get_mock_resolve

def main(resolve=None):
    resolve = resolve or get_mock_resolve()
    project = resolve.GetProjectManager().GetCurrentProject()
    return f"Hello from @NAME_LABEL@ in {project.GetName()}!"
```

```jinja
# @NAME@_main.py.j2
from @NAME@.menu import main

if __name__ == "__main__":
    print(main())
```

```jinja
# tests/test_smoke.py.j2
import pytest
from @NAME@.menu import main

def test_main_returns_string():
    result = main()
    assert isinstance(result, str)
    assert "@NAME_LABEL@" in result
```

## Template Locations

- **Built-in**: `src/ResolveScript/templates/`
- **User**: Not yet supported (planned: `~/.config/resolvescript/templates/`)

## Upgrading a Project

Templates are **one-time scaffolds** — they don't track upstream changes. To update:

1. Create new project with latest template
2. Diff against your project
3. Manually apply relevant changes

Or use `resolvescript analyze` to detect outdated patterns.