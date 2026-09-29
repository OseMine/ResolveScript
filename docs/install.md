# Installation System

ResolveScript's installation system handles **three distinct installation targets**, each with its own directory and semantics.

## Installation Targets

| Target | Command | Directory | Use Case |
|--------|---------|-----------|----------|
| **Scripts** | `resolvescript install` | `Scripts/` | Python/Lua scripts for menu |
| **Workflow** | `resolvescript workflow install` | `Workflow Integration Plugins/` | Workspace > Workflow Integrations |
| **Fuses** | `resolvescript fuse install` | `Fuses/` | `.fuse` scripted plugins |
| **Plugins** | `resolvescript plugin install` | `Plugins/` | Compiled `.plugin` bundles |

## Scripts Installation (`resolvescript install`)

### From Registry (recorded deps)

```bash
# Install all recorded deps from resolvescript.json
resolvescript install

# Install with locked versions (fail if range unsatisfied)
resolvescript install --locked

# Dry run
resolvescript install --dry-run
```

### One-off Install

```bash
# By name (from known table)
resolvescript install my_script

# GitHub repo
resolvescript install owner/repo

# URL
resolvescript install https://example.com/script.zip

# Local file
resolvescript install file:./my_script.py

# Local directory
resolvescript install ./my_script/
```

### Options

| Option | Description |
|--------|-------------|
| `--scripts-root PATH` | Override Scripts root |
| `--target CATEGORY` | Menu category (Comp, Utility, Tool, Render) |
| `--no-save` | Install without recording |
| `--dry-run` | Show changes without writing |
| `--locked` | Fail if recorded artifacts don't satisfy ranges |

### Registry

Installed scripts tracked in `~/.resolvescript/registry.json` (or project `resolvescript.json`):

```json
{
  "version": 1,
  "entries": {
    "my_script": {
      "spec": "owner/repo",
      "version": "1.2.3",
      "target": "Scripts/Utility",
      "installed": "2024-01-15T10:30:00Z",
      "files": ["my_script.py", "README.md"]
    }
  }
}
```

### Registry Commands

```bash
# List recorded
resolvescript manage list

# Show entry
resolvescript manage show my_script

# Remove (uninstall + unrecord)
resolvescript remove my_script

# Remove but keep spec
resolvescript remove my_script --no-save
```

## Workflow Integration Installation

```bash
# Full (launcher + Electron)
resolvescript workflow install

# Script-only
resolvescript workflow install-script

# Electron-only
resolvescript workflow install-plugin
```

**Directory:** Workflow Integration Plugins (separate from Scripts)

| Platform | Directory |
|----------|-----------|
| Windows | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins\` |
| macOS | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Workflow Integration Plugins/` |
| Linux | Undocumented (set `RESOLVESCRIPT_WORKFLOWS_ROOT`) |

**Requirements:** Resolve Studio only.

## Fuse Installation (`.fuse`)

```bash
# Build + install
resolvescript fuse install

# Dry run
resolvescript fuse install --dry-run

# Skip validation
resolvescript fuse install --no-check
```

**Directory:** Fuses (shared with all vendors)

| Platform | Directory |
|----------|-----------|
| Windows (Resolve) | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Fuses` |
| Windows (Fusion) | `%PROGRAMDATA%\Blackmagic Design\Fusion\Fuses` |
| macOS (Resolve) | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Fuses` |
| macOS (Fusion) | `~/Library/Application Support/Blackmagic Design/Fusion/Fuses` |
| Linux | `~/.local/share/DaVinciResolve/Fusion/Fuses` |

**Registry:** `.resolvescript-fuses.json` in each Fuses directory.

## Plugin Installation (`.plugin`)

```bash
# Deploy prebuilt plugin
resolvescript plugin install ./Krokodove.plugin

# With options
resolvescript plugin install ./Krokodove.plugin \
  --name "Krokodove Pro" \
  --target "Krokodove_v2.plugin" \
  --notes "from vendor" \
  --no-force
```

**Directory:** Plugins (one level deep)

| Platform | Directory |
|----------|-----------|
| Windows (Resolve) | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Plugins` |
| Windows (Fusion) | `%PROGRAMDATA%\Blackmagic Design\Fusion\Plugins` |
| macOS (Resolve) | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Plugins` |
| macOS (Fusion) | `~/Library/Application Support/Blackmagic Design/Fusion/Plugins` |
| Linux | `~/.local/share/DaVinciResolve/Fusion/Plugins` |

**Validation:** Only accepts known binary suffixes (`.plugin`, `.bundle`, `.ofx`, `.dll`, `.so`, `.dylib`). Rejects `.fuse` files.

## Environment Variables

| Variable | Overrides |
|----------|-----------|
| `RESOLVESCRIPT_SCRIPTS_ROOT` | Scripts directory |
| `RESOLVESCRIPT_WORKFLOWS_ROOT` | Workflow Integration Plugins |
| `RESOLVESCRIPT_FUSES_ROOT` | Fuses directory |
| `RESOLVESCRIPT_FUSION_PLUGINS_ROOT` | Plugins directory |

## Restart Required

**All installations require Resolve/Fusion restart** — registries are built at startup.

```
Restart Fusion or Resolve to load it
```

## Cross-Platform Notes

| Platform | Notes |
|----------|-------|
| Windows | Uses `%PROGRAMDATA%` (all users) or `%APPDATA%` (current user) |
| macOS | Uses `~/Library/Application Support/` |
| Linux | Uses `~/.local/share/` (XDG) |
| Permissions | May need admin/sudo for system directories |

## Uninstall

```bash
# Scripts
resolvescript remove my_script

# Workflow
resolvescript workflow uninstall MyWorkflow

# Fuse
resolvescript fuse uninstall MyFuse
resolvescript fuse uninstall MyFuse.fuse

# Plugin
resolvescript plugin uninstall Krokodove
```

## List Installed

```bash
# Scripts
resolvescript manage list

# Workflow
resolvescript workflow list

# Fuses
resolvescript fuse list

# Plugins
resolvescript plugin list
```

## Installing from Package

```bash
# Consolidated .py file
resolvescript install file:./dist/my_script.py --target Scripts/Comp

# Package zip
resolvescript install https://github.com/user/repo/releases/download/v1.0/my_script-1.0.0.zip
```

## CI/CD Installation

```bash
# In CI (dry-run to verify)
resolvescript install --dry-run --locked

# Deploy to shared location
resolvescript install --scripts-root /shared/resolve/scripts
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "No manifest found" | Run from project root or use `consolidate` |
| "Permission denied" | Use `--scripts-root` to user-writable dir, or run as admin |
| "Already exists" | Use `--no-force` to fail, or default overwrites |
| "Not in menu after install" | Restart Resolve/Fusion |
| "Wrong category" | Check `--target` / manifest `install.target` |
| "Workflow not in menu" | Requires Resolve Studio, restart |
| "Fuse not in registry" | Check `.fuse` in Fuses dir, restart Fusion |