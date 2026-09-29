# Manifest Format

The manifest is the single source of truth for a ResolveScript project. It can be **JSON** (`manifest.json`) or **XML** (`manifest.xml`).

## JSON Manifest

```json
{
  "name": "My Script",
  "version": "1.2.3",
  "description": "A useful Resolve script",
  "author": "Jane Developer",
  "license": "MIT",
  "repository": "https://github.com/user/my-script",
  "package_dir": "my_script",
  "kind": "script",
  "consolidate": {
    "enabled": true,
    "output": "my_script.py",
    "entry": "my_script:main",
    "exclude": ["tests/**", "*_test.py"],
    "no_comment": ["my_script.core"]
  },
  "install": {
    "target": "Scripts/Utility",
    "include": ["README.md", "LICENSE"],
    "exclude": ["tests/**", "*.pyc"]
  },
  "workflow": {
    "entrypoint": "my_workflow.workflow:INTEGRATION",
    "script_only": false
  },
  "fusion": {
    "entrypoint": "my_fuse.fuse:FUSE",
    "class_name": "MyFuse",
    "display_name": "My Fuse",
    "category": "Fuses\\MyTools",
    "icon_string": "MFZ",
    "description": "Fuse tooltip",
    "tool_type": "CT_Tool",
    "binary": false
  }
}
```

## XML Manifest

```xml
<?xml version="1.0" encoding="UTF-8"?>
<BlackmagicDesign>
  <Plugin>
    <Id>com.example.my-script</Id>
    <Name>My Script</Name>
    <Version>1.2.3</Version>
    <Description>A useful Resolve script</Description>
    <Author>Jane Developer</Author>
    <License>MIT</License>
    <Repository>https://github.com/user/my-script</Repository>
    <PackageDir>my_script</PackageDir>
    <Kind>script</Kind>
    <Consolidate>
      <Enabled>true</Enabled>
      <Output>my_script.py</Output>
      <Entry>my_script:main</Entry>
      <Exclude>tests/**</Exclude>
      <Exclude>*_test.py</Exclude>
      <NoComment>my_script.core</NoComment>
    </Consolidate>
    <Install>
      <Target>Scripts/Utility</Target>
      <Include>README.md</Include>
      <Include>LICENSE</Include>
      <Exclude>tests/**</Exclude>
      <Exclude>*.pyc</Exclude>
    </Install>
    <Workflow>
      <Entrypoint>my_workflow.workflow:INTEGRATION</Entrypoint>
      <ScriptOnly>false</ScriptOnly>
    </Workflow>
    <Fusion>
      <Entrypoint>my_fuse.fuse:FUSE</Entrypoint>
      <ClassName>MyFuse</ClassName>
      <DisplayName>My Fuse</DisplayName>
      <Category>Fuses\MyTools</Category>
      <IconString>MFZ</IconString>
      <Description>Fuse tooltip</Description>
      <ToolType>CT_Tool</ToolType>
      <Binary>false</Binary>
    </Fusion>
  </Plugin>
</BlackmagicDesign>
```

## Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name (menu label) |
| `version` | string | Yes | SemVer (`1.2.3`) |
| `description` | string | No | Tooltip / marketplace description |
| `author` | string | No | Author name |
| `license` | string | No | SPDX identifier (`MIT`, `Apache-2.0`, etc.) |
| `repository` | string | No | Source code URL |
| `package_dir` | string | Yes | Package directory under project root |
| `kind` | enum | Yes | `script`, `extension`, `workflow`, `fuse` |

## Kind-Specific Sections

### `script` / `extension`

```json
"consolidate": { ... },
"install": { ... }
```

### `workflow`

```json
"workflow": {
  "entrypoint": "pkg.module:INTEGRATION",
  "script_only": false
}
```

| Field | Description |
|-------|-------------|
| `entrypoint` | Dotted path to `Integration` instance |
| `script_only` | Skip Electron, Python-only |

### `fuse`

```json
"fusion": {
  "entrypoint": "pkg.fuse:FUSE",
  "class_name": "MyFuse",
  "display_name": "My Fuse",
  "category": "Fuses\\Vendor\\Tool",
  "icon_string": "MFZ",
  "description": "Registry tooltip",
  "tool_type": "CT_Tool",
  "binary": false
}
```

| Field | Description |
|-------|-------------|
| `entrypoint` | Dotted path to `Fuse` instance |
| `class_name` | `FuRegisterClass` ID (stable!) |
| `display_name` | Menu name (REGS_Name) |
| `category` | Registry path with backslashes |
| `icon_string` | 3-letter search code |
| `tool_type` | `CT_Tool`, `CT_SourceTool`, `CT_Operator` |
| `binary` | Reserved for future compiled fuses |

## Consolidate Section

```json
"consolidate": {
  "enabled": true,
  "output": "my_script.py",
  "entry": "my_script:main",
  "exclude": ["tests/**", "*_test.py"],
  "no_comment": ["my_script.core"]
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Master switch |
| `output` | string | `<name>.py` | Output filename |
| `entry` | string | auto | Dotted entry module |
| `exclude` | string[] | `[]` | Glob patterns to skip |
| `no_comment` | string[] | `[]` | Preserve internal imports |

## Install Section

```json
"install": {
  "target": "Scripts/Utility",
  "include": ["README.md", "LICENSE"],
  "exclude": ["tests/**", "*.pyc"]
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `target` | string | `Scripts/Utility` | Menu category |
| `include` | string[] | `[]` | Extra files to copy |
| `exclude` | string[] | `[]` | Patterns to skip |

**Targets:** `Scripts/Comp`, `Scripts/Utility`, `Scripts/Tool`, `Scripts/Render`, or custom `Scripts/MyTools`.

## Auto-Detection

ResolveScript detects manifest kind from content:

| Indicator | Kind |
|-----------|------|
| `workflow` section present | `workflow` |
| `fusion` section present | `fuse` |
| Neither | `script` |

Explicit `kind` overrides auto-detection.

## Validation

```bash
# Check manifest
resolvescript analyze

# JSON output
resolvescript analyze --json
```

## Environment Overrides

| Variable | Manifest Field |
|----------|----------------|
| `RESOLVESCRIPT_SCRIPTS_ROOT` | `install.target` root |
| `RESOLVESCRIPT_WORKFLOWS_ROOT` | `workflow` plugins root |
| `RESOLVESCRIPT_FUSES_ROOT` | `fusion` fuses root |
| `RESOLVESCRIPT_FUSION_PLUGINS_ROOT` | `fusion` plugins root |

## Schema

JSON Schema available at: `schemas/manifest.json` (generated)

```bash
# Validate with jsonschema
python -c "import json, jsonschema; jsonschema.validate(json.load(open('manifest.json')), json.load(open('schemas/manifest.json')))"
```

## Migration

| From | To | Notes |
|------|-----|-------|
| `manifest.xml` (legacy) | `manifest.json` | Use `resolvescript analyze --json` to convert |
| `package.js` (docs typo) | `package.json` | Workflow Electron metadata |

## Best Practices

1. **Keep `class_name` stable** — Changing it breaks saved compositions
2. **Use backslashes in category** — `Fuses\\Vendor\\Tool` not dots
3. **Pin `tool_type`** — `CT_Tool` for filters, `CT_SourceTool` for generators
4. **Version with SemVer** — `1.0.0`, `1.0.1`, `1.1.0`, `2.0.0`
5. **Set `package_dir`** — Enables `resolvescript consolidate` without manifest