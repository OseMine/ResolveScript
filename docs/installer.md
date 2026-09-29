# Lua Installer (`resolvescript build --installable`)

Generate a **self-contained Lua installer** that can be dragged into Fusion's Console or Workspace. The installer shows a GUI (built with Fusion's UIManager) and installs the consolidated script to Resolve's Scripts directory.

## Quick Start

```bash
# In a ResolveScript project with manifest.json
resolvescript build --installable

# Output: dist/my_script_installer.lua
# Drag this file into Fusion Console → Installer window appears
```

## What It Does

1. **Consolidates** your multi-file package into a single Python script (same as `resolvescript build`)
2. **Base64-encodes** the script and embeds it in a Lua file
3. **Generates** a Lua installer using Fusion's `bmd.UIDispatcher` + `UIManager`
4. **User drags** the `.lua` file into Fusion Console/Workspace
5. **Installer window** appears with Install/Cancel buttons
6. **On Install**: Decodes script, writes to `Scripts:<category>/<name>.py`
7. **Result**: Script appears in Resolve's menu after restart

## Usage

```bash
# Default: dist/<name>_installer.lua, category Scripts/Utility
resolvescript build --installable

# Custom output path
resolvescript build --installable --output ./releases/my_installer.lua

# Use project's installer.lua.j2 template (scaffolded with project)
resolvescript build --installable

# Use external template
resolvescript build --installable --installer-template ./custom_installer.lua.j2
```

## The Installer Window

The default installer shows:

```
┌─────────────────────────────────────┐
│ Install My Script                   │
├─────────────────────────────────────┤
│ This will install "My Script" into  │
│ DaVinci Resolve's Scripts/Utility   │
│ menu.                               │
│                                     │
│ The script will be copied to the    │
│ appropriate Scripts directory and   │
│ will be available after restarting  │
│ Resolve.                            │
├─────────────────────────────────────┤
│ ☐ Overwrite if already installed    │
├─────────────────────────────────────┤
│ [Cancel]              [Install]     │
└─────────────────────────────────────┘
```

On success:
```
Installed to C:\Users\...\Scripts\Utility\my_script.py
Restart Resolve to see it in the menu.
```
(Auto-closes after 2 seconds)

## Project Template

When you run `resolvescript create my_script --template minimal`, an `installer.lua.j2` is scaffolded. Edit it to customize:

```lua
-- installer.lua.j2 (Jinja2-style @KEY@ placeholders)

local CONFIG = {
    script_name = "@@SCRIPT_NAME@@",           -- Menu filename
    target_category = "@@TARGET_CATEGORY@@",   -- Scripts/Comp, Utility, Tool, Render...
    overwrite = @@OVERWRITE@@,                 -- true/false default
    window_title = "Install @@SCRIPT_NAME@@",
    window_width = 480,
    window_height = 320,
}
```

### Placeholders

| Placeholder | Description |
|-------------|-------------|
| `@@INSTALLER_NAME@@` | Manifest `name` |
| `@@INSTALLER_VERSION@@` | Manifest `version` |
| `@@INSTALLER_DESCRIPTION@@` | Manifest `description` |
| `@@SCRIPT_B64@@` | Base64-encoded consolidated Python (auto-generated) |
| `@@SCRIPT_NAME@@` | Sanitized script filename (from manifest `name`) |
| `@@TARGET_CATEGORY@@` | Target Scripts category (default: `Scripts/Utility`) |
| `@@OVERWRITE@@` | Default overwrite (default: `true`) |

## Customizing the Installer

### 1. Edit the scaffolded template

```bash
# Project already has installer.lua.j2
vim installer.lua.j2
resolvescript build --installable
```

### 2. Use an external template

```bash
resolvescript build --installable --installer-template ./branding/installer.lua.j2
```

### 3. Minimal custom template example

```lua
--[[--
Custom Installer for @@INSTALLER_NAME@@
--]]--

local CONFIG = {
    script_name = "@@SCRIPT_NAME@@",
    target_category = "Scripts/Tool",
    overwrite = false,
    window_title = "Custom Install @@SCRIPT_NAME@@",
}

local ui = fu.UIManager
local dispatcher = bmd.UIDispatcher(ui)

local win = ui:VGroup{
    ID = "custom_root",
    ui:Label{ Text = CONFIG.window_title },
    ui:Button{ ID = "ok", Text = "OK", Events = { "Clicked" } },
}

dispatcher:RunLoop(win)
```

### 4. Full control — replace the window builder

The default template defines `build_window()` and `on_event(ev)`. Replace entirely:

```lua
local function build_window()
    local ui = fu.UIManager
    return ui:VGroup{
        ID = "my_installer",
        ui:Label{ Text = "My Branded Installer", Font = ui:Font{ Size = 16 } },
        ui:Button{ ID = "go", Text = "Deploy", Events = { "Clicked" } },
    }
end

local function on_event(ev)
    if ev.ID == "go" then
        -- Custom install logic
        local script = b64decode(SCRIPT_B64)
        -- ... write to custom location ...
        dispatcher:ExitLoop()
    end
end

local win = build_window()
dispatcher:RunLoop(win)
```

## Configuration via Manifest (Future)

Currently the category/overwrite defaults are hardcoded in the build command. Planned manifest support:

```json
{
  "name": "My Script",
  "installable": {
    "target_category": "Scripts/Comp",
    "overwrite_default": true,
    "window_title": "Install My Script",
    "template": "custom_installer.lua.j2"
  }
}
```

## Requirements

- **Fusion/Resolve running** with a project open (installer uses `fusion:MapPath("Scripts:...")`)
- **Lua 5.1+** (Fusion's built-in Lua)
- **`bmd.UIDispatcher`** available (standard in Fusion page)
- **Write access** to the user Scripts directory

## Distribution

The `.lua` installer is a **single file** — easy to share:

- Email/Slack to artists
- Upload to internal tool server
- Include in Reactor atom
- Bundle with `.plugin` in a fuse package

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "Cannot access Resolve API" | No project open | Open a project in Resolve first |
| "Could not resolve Scripts:..." | Fusion API limitation | Ensure project is saved |
| Script not in menu | Restart required | Restart Resolve/Fusion |
| Permission denied | Scripts dir read-only | Run Resolve as admin or fix perms |
| Installer won't run | Not in Fusion Console | Drag into Console tab, not Text Editor |

## Base64 Decoder

The installer includes a pure-Lua base64 decoder (Fusion's Lua has no built-in):

```lua
local b64chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
local function b64decode(data)
    -- ... standard decoder with padding handling ...
end
```

This runs entirely in Fusion's Lua environment — no external dependencies.