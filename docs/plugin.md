# Compiled Fusion Plugin (`.plugin`) Deployment

**`.plugin` files are precompiled native binaries/bundles** — they cannot be built from source by ResolveScript. This tool only **deploys** them to the correct Plugins directory.

> **Key distinction**: A `.fuse` is a Lua script Fusion compiles at runtime. A `.plugin` is a platform-specific binary (`.plugin` bundle on macOS, `.dll` on Windows, `.so` on Linux) built with the Fusion SDK or vendor toolchain.

## Quick Start

```bash
# Deploy a prebuilt plugin
resolvescript plugin install ./vendor/Krokodove.plugin

# List deployed plugins
resolvescript plugin list

# Show info about a plugin file
resolvescript plugin describe ./vendor/Krokodove.plugin

# Remove a deployed plugin
resolvescript plugin uninstall Krokodove
```

## Supported Formats

| Extension | Platform | Notes |
|-----------|----------|-------|
| `.plugin` | macOS (bundle) | Directory bundle with `Contents/MacOS/` |
| `.bundle` | macOS (legacy) | Older bundle format |
| `.ofx` | All | OpenFX plugin |
| `.dll` | Windows | Native DLL |
| `.so` | Linux | Shared library |
| `.dylib` | macOS | Dynamic library |

The tool validates the suffix and **rejects `.fuse` files** passed to `plugin install`:

```
error: Posterize.fuse is not a compiled Fusion plugin; expected one of .plugin, .bundle, .ofx, .dll, .so, .dylib. A .fuse is scripted Lua — build that with a Fuse declaration instead.
```

## Installation

```bash
# Basic install (overwrites by default)
resolvescript plugin install ./Krokodove.plugin

# Custom install name
resolvescript plugin install ./Krokodove.plugin --name "Krokodove Pro"

# Custom target filename (when it must differ)
resolvescript plugin install ./Krokodove.plugin --target "Krokodove_v2.plugin"

# Add notes (shown in list)
resolvescript plugin install ./Krokodove.plugin --notes "from Blackmagic's installer"

# Dry run (no copy)
resolvescript plugin install ./Krokodove.plugin --dry-run

# Fail if already exists (don't overwrite)
resolvescript plugin install ./Krokodove.plugin --no-force
```

## Plugins Directory

Fusion/Resolve scans **Plugins** directories (one level deep):

| Platform | Plugins Directory |
|----------|-------------------|
| Windows (Resolve) | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Plugins` |
| Windows (Fusion) | `%PROGRAMDATA%\Blackmagic Design\Fusion\Plugins` |
| macOS (Resolve) | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Plugins` |
| macOS (Fusion) | `~/Library/Application Support/Blackmagic Design/Fusion/Plugins` |
| Linux (Resolve) | `~/.local/share/DaVinciResolve/Fusion/Plugins` |

Override with:
```bash
export RESOLVESCRIPT_FUSION_PLUGINS_ROOT=/custom/plugins/path
```

Or per-command:
```bash
resolvescript plugin install ./Krokodove.plugin --root /custom/plugins
```

## Registry & Management

ResolveScript tracks deployed plugins in `.resolvescript-fuses.json` (same file as fuses, different section):

```bash
# List with metadata
resolvescript plugin list
# Krokodove  [Krokodove.plugin]  notes: from Blackmagic's installer

# Show details
resolvescript plugin describe ./Krokodove.plugin
# Krokodove  (Krokodove.plugin)
#   source:  /path/to/Krokodove.plugin
#   kind:    compiled file, 2048512 bytes
#   note:    from Blackmagic's installer

# Uninstall (by installed name)
resolvescript plugin uninstall Krokodove
```

## Bundle Handling

macOS `.plugin` bundles are **copied whole** and **replaced whole** on update — stale files inside the old bundle cannot survive:

```bash
# First install
resolvescript plugin install ./Thing.plugin
# Copies entire Thing.plugin/Contents/

# Update
resolvescript plugin install ./Thing.plugin
# Removes old bundle entirely, copies new one
```

## Restart Required

Fusion builds its plugin registry **once at startup**. After deploying a `.plugin`:

```
Restart Fusion or Resolve to load it
```

## Fuse + Plugin Together

A vendor often ships a scripted fuse (`.fuse`) **and** a compiled plugin (`.plugin`) that work together. Package them in one archive:

```bash
resolvescript fuse package --plugin ./vendor/Krokodove.plugin
# dist/Posterize-1.0.0.zip contains:
#   Posterize.fuse
#   Krokodove.plugin
#   resolvescript.json (describes both)
```

## Limitations

- **Cannot build** `.plugin` files — they require the Fusion SDK (C++/OpenCL) and platform toolchain
- **No source form** — this tool only moves bytes
- **Platform-specific** — a Windows `.dll` won't load on macOS
- **One level deep** — Fusion scans `Plugins/PluginName.plugin`, not nested subdirectories