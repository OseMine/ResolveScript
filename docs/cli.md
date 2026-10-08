# CLI Reference

Complete reference for `resolvescript` commands.

## Global Options

```bash
resolvescript [--version] [-v|--verbose] <command> [args...]
```

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `-v, --verbose` | Log diagnostics: `-v` info level, `-vv` debug level |
| `-h, --help` | Show help for command |

---

## Project Commands

### `create` — Scaffold a new project

```bash
resolvescript create <name> [options]
```

| Option | Description |
|--------|-------------|
| `--dir DIR` | Destination directory (default: cwd) |
| `--fmt FORMAT` | Manifest format: `json` or `xml` (default: json) |
| `--template TEMPLATE` | Scaffold flavor (default: minimal) |
| `--description TEXT` | Project description |
| `--author NAME` | Author name |
| `--include PACKAGE`| Project gets created with a Resolvescript extension or helper plugin like `pydavinci` already set up |

**Templates:**

| Template | Description |
|----------|-------------|
| `minimal` | Basic Python script project |
| `pydavinci` | pydavinci wrapper (type hints, autocomplete) |
| `davinci-rest` | davinci-rest REST client |
| `lua` | Lua script project |
| `workflow` | Workflow Integration (Workspace > Workflow Integrations) |
| `extension` | A **ResolveScript extension** (a.k.a. **plugin**) |
| `fuse` | Fusion fuse (scripted `.fuse` plugin) |

**Includes:**

Project gets created with a Resolvescript extension or helper plugin like `pydavinci` already set up

Use Resolvescript Extensions by git:https://giturlhere

multiple includes are supported


**Examples:**
```bash
resolvescript create my_tool --template pydavinci
resolvescript create my_fuse --template fuse --dir /projects
resolvescript create my_workflow --template workflow --include git:https://github.com/CoolDev/ResolveScriptExtension
```

---

### `dev` — Sandbox dev loop / REPL

```bash
resolvescript dev [options]
```

Runs the project's entry point against the mock Resolve API. Supports hot-reload on file changes.

| Option | Description |
|--------|-------------|
| `--repl` | Drop into REPL after run |
| `--no-reload` | Disable file watching |

---

### `test` — Run pytest suite

```bash
resolvescript test [pytest-args...]
```

Runs the project's tests against the mock Resolve API. Passes extra args to pytest.

```bash
resolvescript test -v -k "test_menu"
resolvescript test --tb=short
```

---

### `analyze` — Static checks

```bash
resolvescript analyze [--json]
```

Checks imports, manifest validity, API usage patterns.

| Option | Description |
|--------|-------------|
| `--json` | Machine-readable JSON output |

---

### `build` — Consolidate package

```bash
resolvescript build [--output PATH] [--installable] [--installer-template PATH]
```

Consolidates multi-file package into a single `.py` file (or Lua installer).

| Option | Description |
|--------|-------------|
| `--output PATH` | Output file (default: `dist/<manifest output>`) |
| `--installable` | Generate Lua installer instead of Python |
| `--installer-template PATH` | Custom installer template (default: project's `installer.lua.j2`) |

**Output:**
```
Consolidated 5 module(s) into dist/my_script.py (12345 bytes)
# or with --installable:
Created Lua installer: dist/my_script_installer.lua
```

---

### `package` — Release artifacts

```bash
resolvescript package [--dist DIR]
```

Creates zip archive with SHA-256 checksum.

| Option | Description |
|--------|-------------|
| `--dist DIR` | Output directory (default: `dist/`) |

**Output:**
```
Created my_script-1.0.0.zip (45678 bytes)
SHA-256: abc123...
Wrote SHA256SUMS.txt
```

---

### `consolidate` — Merge directory (no manifest)

```bash
resolvescript consolidate <package_dir> --output <file.py>
```

Merges a package directory into a single `.py` without requiring a manifest.

| Argument | Description |
|----------|-------------|
| `package_dir` | Directory to consolidate |
| `--output PATH` | Required output file |

---

### `clean` — Clean project caches and artifacts

```bash
resolvescript clean [--dir DIR] [-v]
```

Removes project caches, build artifacts, and registry files:

| Target | Description |
|--------|-------------|
| `.resolvescript/cache` | Resolver/download cache |
| `dist/` | Build output directory |
| `.resolvescript/install.json` | Install registry |
| `.resolvescript-fuses.json` / `.resolvescript-plugins.json` | Fuse/plugin registries |
| `__pycache__/` | Python bytecode directories |

| Option | Description |
|--------|-------------|
| `--dir DIR` | Project directory (default: current directory) |
| `-v, --verbose` | List cleaned paths |

---

## Dependency Management

### `add` — Install and record

```bash
resolvescript add <spec> [options]
```

| Specifier | Example |
|-----------|---------|
| Name | `my_script` |
| GitHub | `owner/repo` |
| GitHub (explicit) | `github:owner/repo` |
| URL | `https://example.com/script.zip` |
| Local file | `file:./script.py` |
| Local dir | `./my_script/` |

| Option | Description |
|--------|-------------|
| `--scripts-root PATH` | Override Scripts root |
| `--target CATEGORY` | Install target (Comp, Utility, Tool, Render) |
| `--no-save` | Install without recording in `resolvescript.json` |

---

### `install` — Materialize dependencies

```bash
resolvescript install [spec] [options]
```

Without `spec`, installs all recorded deps from `resolvescript.json`.

| Option | Description |
|--------|-------------|
| `--scripts-root PATH` | Override Scripts root |
| `--locked` | Fail if recorded artifacts don't satisfy ranges |
| `--dry-run` | Show changes without writing |

---

### `update` — Re-resolve dependencies

```bash
resolvescript update [name] [options]
```

| Option | Description |
|--------|-------------|
| `--scripts-root PATH` | Override Scripts root |
| `--precise VERSION` | Pin exact version |
| `--fix` | Realign to manifest compat |

---

### `remove` — Uninstall and unrecord

```bash
resolvescript remove <name> [--scripts-root PATH] [--no-save]
```

| Option | Description |
|--------|-------------|
| `--scripts-root PATH` | Override Scripts root |
| `--no-save` | Uninstall but keep recorded specifier |

---

### `search` — Discover scripts

```bash
resolvescript search <query>
```

Searches known table + conventions.

---

## Diagnostics

### `doctor` — Self-diagnosis

```bash
resolvescript doctor [--scripts-root DIR] [--json]
```

Checks the interpreter and package install, template package-data, Scripts
root discovery (override > `RESOLVESCRIPT_SCRIPTS_ROOT` > OS default),
`RESOLVESCRIPT_*`/`RESOLVE_*` env overrides, the project manifest,
`resolvescript.json` and the install registry. Every check reports
`ok` / `warn` / `fail`; the command exits `1` when any check fails.

| Option | Description |
|--------|-------------|
| `--scripts-root DIR` | Check against this Scripts root instead of the discovered one |
| `--json` | Machine-readable output (`checks`, `warnings`, `failures`) |

```console
$ resolvescript doctor
[ ok ] interpreter   CPython 3.12.10 (resolvescript 1.0.2, installed package)
[ ok ] templates     6 template(s) in .../ResolveScript/templates
[warn] scripts-root  .../Fusion/Scripts (OS default) - missing; launch DaVinci Resolve once or pass --scripts-root
[ ok ] environment   no RESOLVESCRIPT_*/RESOLVE_* overrides set
[ ok ] manifest      my-tool 1.0.2 - targets: Comp
[ ok ] workspace     no resolvescript.json in /path
[ ok ] registry      no registry at .../install.json (nothing installed yet)
1 warning(s), 0 failure(s)
```

---

## Install Registry

### `manage` — Low-level registry ops

```bash
resolvescript manage <subcommand> [args...]
```

| Subcommand | Description |
|------------|-------------|
| `list` | List registry entries |
| `show <name>` | Show entry details |
| `add <name> <path>` | Add entry manually |
| `remove <name>` | Remove entry |
| `clear` | Clear registry |
| `migrate` | Migrate old registry format |

---

## Framework Extensions

### `extensions` — Manage framework extensions (plugins)

Framework extensions extend the `resolvescript` CLI itself; they install
into the CLI config directory and **never** into DaVinci Resolve (see the
Resolve script vs framework extension distinction below).

```bash
resolvescript extensions add <spec> [--force]
resolvescript extensions remove <name>
resolvescript extensions list [--json]
```

| Subcommand | Description |
|------------|-------------|
| `add <spec>` | Resolve a specifier, check its `requires` gate and install it into the CLI config dir (`--force` reinstalls) |
| `remove <name>` | Uninstall a plugin and unregister it |
| `list` | List installed plugins (`--json` for machine-readable output) |

A plugin is an ordinary package whose `manifest.json` declares
`"kind": "extension"` and `"install": { "to": "framework" }` — the same
specifier grammar, SHA-256 integrity and packaging pipeline as Resolve
scripts, only the install target differs. A standalone `plugin.json` in a
local directory is also accepted by `extensions add`.

The plugin's entry module (manifest `entrypoint`) must expose
`register_commands(parser)`, which receives the top-level subparser action
and adds the contributed commands — they appear in `resolvescript --help`.
Plugins whose `extension.requires` gate fails (resolvescript or Python
version) or that cannot be loaded are skipped with a warning at CLI
startup; a broken plugin never crashes the CLI.

**Config directory:** `%APPDATA%\ResolveScript` (Windows) or
`~/.config/ResolveScript` (macOS/Linux); set `RESOLVESCRIPT_CONFIG_DIR` to
override. Installed plugins are tracked in `plugins.json` next to it.

```bash
resolvescript extensions add ./examples/resolvescript-lint
analyze-extra                              # contributed by the plugin
resolvescript extensions list
resolvescript extensions remove resolvescript-lint
```

---

## Workflow Integrations

### `workflow` — Build/install Workflow Integrations

```bash
resolvescript workflow <subcommand> [options]
```

| Subcommand | Description |
|------------|-------------|
| `build` | Generate launcher + Electron shell into `dist/` |
| `install` | Install into Workflow Integration Plugins directory |
| `install-script` | Install only Python launcher |
| `install-plugin` | Install only Electron shell |
| `list` | List installed integrations |
| `uninstall <id>` | Remove integration |
| `root` | Print Workflow Integration Plugins directory |
| `describe` | Print integration metadata |

**Common options:**
| Option | Description |
|--------|-------------|
| `--entrypoint PKG:INTEGRATION` | Integration entrypoint |
| `--project-root DIR` | Project root for imports |
| `--root DIR` | Override plugins directory |
| `--out DIR` | Build output directory (default: `./dist`) |
| `--script-only` | Skip Electron shell |
| `--dry-run` | Report without writing |

---

## Fusion Fuses (`.fuse`)

### `fuse` — Build/install/package fuses

```bash
resolvescript fuse <subcommand> [options]
```

| Subcommand | Description |
|------------|-------------|
| `build` | Generate `.fuse` into `dist/` |
| `install` | Install into Fuses directory |
| `package` | Bundle fuse (+ optional plugin) into zip |
| `list` | List installed fuses |
| `uninstall <name>` | Remove fuse |
| `root` | Print Fuses directory |
| `describe` | Print fuse metadata |

**Build options:**
| Option | Description |
|--------|-------------|
| `--entrypoint PKG:FUSE` | Fuse entrypoint |
| `--project-root DIR` | Project root for imports |
| `--out DIR` | Output directory (default: `./dist`) |
| `--stdout` | Print `.fuse` source to stdout |
| `--no-check` | Skip validation |

**Install options:**
| Option | Description |
|--------|-------------|
| `--root DIR` | Override Fuses directory |
| `--dry-run` | Report without writing |
| `--no-check` | Skip validation |

**Package options:**
| Option | Description |
|--------|-------------|
| `--dist DIR` | Output directory (default: `./dist`) |
| `--plugin PATH` | Prebuilt `.plugin` to include |
| `--no-check` | Skip validation |

**Root options:**
| Option | Description |
|--------|-------------|
| `--which {Fuses,Plugins}` | Which directory (default: Fuses) |
| `--list` | Print all candidates |

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `RESOLVESCRIPT_SCRIPTS_ROOT` | Override Scripts root |
| `RESOLVESCRIPT_WORKFLOWS_ROOT` | Override Workflow Integration Plugins root |
| `RESOLVESCRIPT_FUSES_ROOT` | Override Fuses root |
| `RESOLVESCRIPT_FUSION_PLUGINS_ROOT` | Override Plugins root |
| `RESOLVESCRIPT_ALLOW_REMOTE` | Allow remote fetches (default: false) |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error (invalid args, missing manifest, build failed) |
| `2` | Usage error (invalid command, missing required arg) |

---

## Shell Completion

```bash
# Bash
eval "$(register-python-argcomplete resolvescript)"

# Fish
register-python-argcomplete --shell fish resolvescript | source

# Zsh
eval "$(register-python-argcomplete resolvescript)"
```

Requires `pip install argcomplete`.