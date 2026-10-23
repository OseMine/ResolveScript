# Plugin Installation (`.plugin`)

This document covers the `resolvescript plugin` command group for deploying
**prebuilt compiled Fusion plugins** (`.plugin`, `.bundle`, `.dylib`, `.so`,
`.dll`, `.ofx`). These are native binaries produced by Blackmagic's toolchain
or a vendor's build process — there is no source form this tool could compile,
so every operation is **deploy/package/remove**, never build.

> **Note:** This is distinct from **framework extensions** (CLI plugins),
> managed by `resolvescript extensions add/remove/list`. A `.plugin` is a
> Fusion plugin that Resolve/Fusion loads at startup; a framework extension
> extends the `resolvescript` CLI itself.

---

## Quick Reference

```bash
# Deploy a prebuilt plugin
resolvescript plugin install ./Krokodove.plugin

# With options
resolvescript plugin install ./Krokodove.plugin \
  --name "Krokodove Pro" \
  --target "Krokodove_v2.plugin" \
  --notes "from vendor" \
  --no-force

# List installed plugins
resolvescript plugin list
resolvescript plugin list --json

# Uninstall
resolvescript plugin uninstall Krokodove
```

---

## Commands

### `plugin install <path>`

Copy a compiled plugin into Fusion's Plugins directory.

| Argument | Description |
|----------|-------------|
| `path` | Path to the `.plugin` / `.bundle` / `.dll` / `.so` / `.dylib` / `.ofx` file or macOS bundle directory |

| Option | Description |
|--------|-------------|
| `--name NAME` | Name recorded in the registry (default: file stem) |
| `--target TARGET` | Installed file name (default: source name) |
| `--notes NOTES` | Free text recorded with the install |
| `--no-force` | Fail if the target already exists |
| `--dry-run` | Report what would be written without writing |
| `--root DIR` | Override the Plugins directory (`RESOLVESCRIPT_FUSION_PLUGINS_ROOT`) |

**Validation:** Only accepts known binary suffixes. Rejects `.fuse` files (use `fuse install`).

---

### `plugin list`

List compiled plugins installed by ResolveScript.

| Option | Description |
|--------|-------------|
| `--root DIR` | Override the Plugins directory |
| `--json` | Machine-readable output |

---

### `plugin uninstall <name>`

Remove an installed compiled plugin.

| Argument | Description |
|----------|-------------|
| `name` | The name or target file recorded by `plugin install` |

| Option | Description |
|--------|-------------|
| `--root DIR` | Override the Plugins directory |

---

## Plugin Directory (per OS)

| Platform | Directory |
|----------|-----------|
| Windows (Resolve) | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Plugins` |
| Windows (Fusion) | `%PROGRAMDATA%\Blackmagic Design\Fusion\Plugins` |
| macOS (Resolve) | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Plugins` |
| macOS (Fusion) | `~/Library/Application Support/Blackmagic Design/Fusion/Plugins` |
| Linux | `~/.local/share/DaVinciResolve/Fusion/Plugins` |

Override with `RESOLVESCRIPT_FUSION_PLUGINS_ROOT` or `--root`.

---

## Registry

Installed plugins are tracked in `.resolvescript-fuses.json` inside the Plugins
directory (shared with fuses, under the `"plugins"` section). Each entry
records:

```json
{
  "name": "Krokodove Pro",
  "target": "Krokodove.plugin",
  "notes": "from vendor",
  "source": "/path/to/original/Krokodove.plugin",
  "size": 12345,
  "installed_at": "2026-10-23T12:34:56+00:00"
}
```

---

## Carrying a `.plugin` in a Fuse Package

A fuse project can ship a prebuilt `.plugin` alongside its `.fuse`:

```bash
resolvescript fuse package --plugin ./vendor/Krokodove.plugin
```

The resulting zip includes the `.plugin` and a `resolvescript.json` with the
plugin metadata. Consumers can deploy it with:

```bash
resolvescript plugin install ./dist/MyFuse-1.0.0.zip
# (archive install extracts and deploys the carried .plugin)
```

---

## Environment Variables

| Variable | Overrides |
|----------|-----------|
| `RESOLVESCRIPT_FUSION_PLUGINS_ROOT` | Plugins directory |

---

## Restart Required

**All plugin installations require a Resolve/Fusion restart** — Fusion builds
its plugin registry once at startup.

```
Restart Fusion or Resolve to load it
```
