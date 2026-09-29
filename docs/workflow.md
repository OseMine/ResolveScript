# Workflow Integrations

**Workflow Integrations** appear in Resolve's **Workspace > Workflow Integrations** menu. They are Electron-based (or script-only) plugins that run in a separate process and communicate with Resolve via a JSON line protocol.

## Quick Start

```bash
# Scaffold a workflow integration
resolvescript create my_workflow --template workflow

# Enter project
cd my_workflow

# Check declaration
resolvescript workflow describe

# Build (launcher + Electron shell)
resolvescript workflow build

# Install into Workspace > Workflow Integrations
resolvescript workflow install

# Or script-only (no Electron)
resolvescript workflow build --script-only
resolvescript workflow install-script
```

## Architecture

```
┌─────────────────┐     JSON lines      ┌──────────────────┐
│  Resolve        │ ◄─────────────────► │  Workflow        │
│  (UI thread)    │   stdin/stdout      │  Integration     │
└─────────────────┘                     │  (Node/Python)   │
                                        └──────────────────┘
```

**Protocol** (one JSON object per line):

| Action | Direction | Payload |
|--------|-----------|---------|
| `ping` | Resolve → Plugin | `{}` |
| `describe` | Resolve → Plugin | `{}` |
| `launch` | Resolve → Plugin | `{context: {...}}` |
| `callback` | Plugin → Resolve | `{id, result}` |
| `context` | Plugin → Resolve | `{key, value}` |
| `quit` | Resolve → Plugin | `{}` |

**Reply format:**
```json
{"ok": true, "result": {...}}
{"ok": false, "error": "ErrorType: message"}
```

## Project Structure

```
my_workflow/
├── manifest.json              # kind: "workflow"
├── my_workflow/
│   ├── __init__.py
│   ├── workflow.py            # Integration class (Python side)
│   └── workflow_workflow.py   # Entry point
├── package.json               # Electron metadata
├── main.js                    # Electron main process
├── preload.js                 # Secure bridge
├── index.html                 # UI (if any)
└── tests/
```

## The Integration Class

```python
# workflow.py
from ResolveScript.workflow import Integration, ScriptOptions

INTEGRATION = Integration(
    name="My Workflow",
    version="1.0.0",
    description="Custom workflow tool",
    category="Custom",
    # Python-side handler
    options=ScriptOptions(
        entrypoint="my_workflow.workflow:INTEGRATION",
        script_only=False,  # True = no Electron
    ),
)
```

## Electron vs Script-Only

| Mode | Use Case | Files |
|------|----------|-------|
| **Electron** (default) | Complex UI, web tech | `package.json`, `main.js`, `preload.js`, `index.html` |
| **Script-only** | Simple Python UI, no web deps | Only Python files |

```bash
# Build with Electron (default)
resolvescript workflow build

# Build script-only
resolvescript workflow build --script-only

# Install script-only
resolvescript workflow install-script
```

## Installation Directories

Workflow Integrations load from a **separate plugins root** (not Scripts):

| Platform | Directory |
|----------|-----------|
| Windows | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins\` |
| macOS | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Workflow Integration Plugins/` |
| Linux | Undocumented (set `RESOLVESCRIPT_WORKFLOWS_ROOT`) |

**Studio only** — Free Resolve doesn't load Workflow Integrations.

## Manifest

```json
{
  "name": "My Workflow",
  "version": "1.0.0",
  "kind": "workflow",
  "workflow": {
    "entrypoint": "my_workflow.workflow:INTEGRATION",
    "script_only": false
  }
}
```

## Native Bridge (`WorkflowIntegration.node`)

The Electron shell loads a native Node addon shipped with Resolve:
```
%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Workflow Integrations\Examples\
  SamplePlugin\
  SamplePromisePlugin\
  ScriptTestPlugin\
```

ResolveScript copies the appropriate `WorkflowIntegration.node` for the platform.

## Testing

```bash
# Run against mock Resolve API
resolvescript test

# The test harness simulates the JSON protocol
from ResolveScript.workflow.testing import Harness

harness = Harness(INTEGRATION)
result = har.launch({"project": "test"})
```

## Environment Variable

```bash
export RESOLVESCRIPT_WORKFLOWS_ROOT=/custom/workflow/plugins
```

## Limitations

- **Windows/macOS only** for Electron (Linux: script-only)
- **Resolve Studio required**
- **Restart Resolve** after install/uninstall
- **One level deep** plugin directory scanning