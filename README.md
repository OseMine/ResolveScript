# resolvescript
<p align="center">
  <strong>The only resolve scripting framework out there.</strong>
  <br /><br />
  <img src="https://img.shields.io/badge/python-%233670A0.svg?style=for-the-badge&amp;logo=python&amp;logoColor=ffdd54" alt="Python" />
  <img src="https://img.shields.io/badge/davinci_resolve-%23233A51.svg?style=for-the-badge&amp;logo=davinciresolve&amp;logoColor=white" alt="DaVinci Resolve" />
  <img src="https://img.shields.io/badge/pypi-%23ececec.svg?style=for-the-badge&amp;logo=pypi&amp;logoColor=1f73b7" alt="PyPI" />
  <img src="https://img.shields.io/badge/github%20actions-%232671E5.svg?style=for-the-badge&amp;logo=githubactions&amp;logoColor=white" alt="GitHub Actions" />
</p>

---

## Overview
Build, test, package and install [DaVinci Resolve](https://www.blackmagicdesign.com/products/davinciresolve) Python scripts and plugins: a small CLI with an npm-style workflow for the Resolve `Scripts/` tree.

- `create` scaffolds a project with a `manifest.json` and smoke tests
- `dev` / `test` run against a mock `DaVinciResolveScript` API - no Resolve needed
- `build` consolidates the multi-file package into a single `.py` for distribution
- `add` / `install` / `update` resolve dependencies from GitHub, URLs, archives or local folders and record them in `resolvescript.json`
- `package` emits `dist/<name>-<version>.tar.gz` plus `SHA256SUMS.txt`
- `fuse` / `plugin` scaffold, validate, build, package and install Fusion `.fuse` plugins and precompiled `.plugin` binaries

Install with pip: `pip install resolvescript` (Python 3.9+).



| Aspect          | Specification                     |
| --------------- | --------------------------------- |
| Current version | v1.0.2                            |
| Resolve support | DaVinci Resolve Free & Studio 18+ |
| License         | MIT                               |

## Quickstart

```console
$ resolvescript create my-cool-tool
$ cd my-cool-tool
$ resolvescript dev        # sandboxed dev loop against the mock API
$ resolvescript test       # run the smoke tests
$ resolvescript build      # single-file build -> dist/my_cool_tool.py
$ resolvescript analyze    # static checks (imports, manifest, API usage)
$ resolvescript package    # dist/my-cool-tool-1.0.2.tar.gz + SHA256SUMS.txt

# elsewhere, consume it:
$ resolvescript add github:example/my-cool-tool
$ resolvescript install    # materialize all recorded deps into Resolve
```

## Authoring

### Directory

```
my-cool-tool/
  manifest.json        # project manifest (or manifest.xml)
  my_cool_tool/        # your Python package (module name from manifest.name/python)
    __init__.py
    export.py
  tests/
    test_smoke.py
```

### Commands

| Command | Purpose |
| --- | --- |
| `create <name>` | Scaffold a new project (`--json`/`--xml`, `--template minimal\|pydavinci\|davinci-rest\|lua\|workflow\|extension\|fuse`, `--dir`) |
| `dev` | Sandboxed dev loop / REPL against the mock Resolve API (`--built` for the consolidated file, `--repl`, `--editor`) |
| `test` | Run the project's pytest suite against the mock API (`--built`, `-k pattern`, `--api-coverage`) |
| `analyze` | Static checks: missing entrypoint/module, syntax, unused imports, unmocked API methods, attribute typing (`--json`) |
| `build` | Consolidate into a single file (`--output`, or the manifest `consolidate.output`) |
| `package` | Assemble `dist/<name>-<version>.tar.gz` + `SHA256SUMS.txt` (`--dist DIR`) |
| `add <spec>` | Resolve, install a dependency and record it (`--no-save`, `--target`, `--scripts-root`) |
| `install [<spec>]` | One-off install, local project, **or** materialize recorded deps (`--locked`, `--dry-run`) |
| `update [<name>]` | Re-resolve recorded deps within their ranges (`--precise X.Y.Z`, `--fix`) |
| `remove <name>` | Uninstall and unrecord (`--no-save`) |
| `search <query>` | Search the known sources table |
| `doctor` | Diagnose environment, project manifest and install registry (`--json`, `--scripts-root`) |
| `manage list\|remove` | Low-level registry operations (`--json`, `--all`) |
| `extensions add\|remove\|list` | Manage framework extensions (plugins) for the CLI itself (`--force`, `--json`) |

Exit codes: `0` ok, `1` error, `2` usage.

### Specifiers

`add` / `install <spec>` accept:

- `name` - a name from the built-in known-sources table (`resolvescript search`)
- `owner/repo` or `github:owner/repo[#ref]` - GitHub repo (ref = branch/tag/commit, or `#semver:^1.2` for a range)
- `https://...tar.gz` / `.zip` - direct archive URL
- `https://...` - a URL whose root carries a `manifest.json` (GitHub Pages-style hosting)
- `file:path`, `./dir`, an absolute path - local directory or archive
- `.tar.gz` / `.zip` files and local directories

Recorded specs live in `resolvescript.json`; use `resolvescript install --locked` for a CI/npm-ci style check that recorded artifacts still satisfy the recorded ranges.

### Manifest reference

`manifest.json` (or `manifest.xml`, same shape):

```jsonc
{
  "name": "my-cool-tool",          // required
  "version": "1.0.2",              // required, semver
  "author": "You",
  "description": "...",
  "python": "my_cool_tool",        // package/module name (defaults to "name")
  "entrypoint": "export.py",       // recommended CLI/bootstrap module
  "kind": "script",                 // "script" (default) | "extension" (plugin)
                                    //   | "workflow" (integration) | "fuse"
  "targets": ["Comp"],              // Scripts subfolders: Comp, Utility, Tool, Render,
                                    //   Deliver, Edit, WorkflowIntegrations, Fusion, root
  "compat": { "resolve": "18.6.4", "python": "3.12" },
  "release": { "owner": "you", "repo": "my-cool-tool" },  // for `add` discovery
  "scripts_root": "",               // per-OS override for the Resolve Scripts root
  "consolidate": { "enabled": true, "output": "dist/my_tool.py", "exclude": [], "no_comment": [] },
  "install": { "as_directory": true, "include": [], "exclude": [], "to": "resolve" },
  "dependencies": ["github:example/dep"]   // resolved on install
}
```

### Install model

Installs drop into each OS's Resolve Scripts root under the manifest `targets`. Directories install as a single folder; `.py`-only packages can opt into `install.as_directory: false` multi-file installs. Every install is recorded in `<ScriptsRoot>/.resolvescript/install.json` (schema v1):

- keys are `<name>:<target>` (directory) or `<name>:<target>:<relpath>` (file-based)
- each entry carries `version`, `targets`, `as_directory`, `files`, `source`, `resolved` and `integrity`
- `install --locked` verifies registry entries against recorded specs before reusing them

`--scripts-root` (or `RESOLVESCRIPT_SCRIPTS_ROOT`) overrides OS detection.

## Fusion fuses and plugins

Fuses and plugins ride the same manifest shape with `"kind": "fuse"` — one Lua
file Fusion compiles, or a precompiled binary Fusion loads:

```console
$ resolvescript create Posterize --template fuse   # scaffold the project
$ resolvescript fuse build                         # render, validate, write dist/
$ resolvescript fuse package                       # dist/Posterize-<version>.zip
$ resolvescript fuse install                       # into Fusion's Fuses root, recorded
$ resolvescript fuse list                          # and fuse uninstall to undo it
```

- **Validation is two-layer** — structure first (`FuRegisterClass` / `Create()` /
  `Process(req)`, the `InImage` / `OutImage` globals), then a full `luac -p`
  parse when Lua is installed, so a broken fuse fails here rather than inside
  Resolve. Generated files are ASCII-only.
- **`.plugin` binaries are deployed, never built** — precompiled bundles get
  `resolvescript plugin install | list | uninstall` and nothing else; there is
  no source to compile.
- **Roots are per-OS, both overridable** — `RESOLVESCRIPT_FUSES_ROOT` and
  `RESOLVESCRIPT_FUSION_PLUGINS_ROOT` (or `--root`) point at another location.
- **`resolvescript build --installable`** emits one Lua file instead of a
  `.py`: drag it into Fusion's Console or Workspace and it opens an install
  window that writes the consolidated script where Resolve looks for it.
  Projects can ship their own `installer.lua.j2` to redraw that window.

Guides: [`docs/fuse.md`](docs/fuse.md), [`docs/plugin.md`](docs/plugin.md),
[`docs/workflow.md`](docs/workflow.md).

## Frameworks

`resolvescript` ships a mock `DaVinciResolveScript` module with a faithful-enough Resolve color/editing/page object model for testing, plus `resolvescript test --api-coverage` to report which mock methods your tests actually exercise.

### `ResolveScript.ui` — a declarative UI framework

A modern, reactive UI framework for Resolve tools. Screens are described as
plain Python (or dicts/JSON, or classes) and mounted onto real `UIManager`
elements — or onto a headless mirror, so the same code runs in a test with no
Resolve installed.

```python
from ResolveScript.ui import (
    Window, Column, Row, Button, TextField, Tree, Value, rows, call, run
)

sequence = Value("Sequence 01")
clips = list(media_pool.GetRootFolder().GetClipList())

run(Window("Batch Renderer", children=[
    Column(
        Row(TextField(value=sequence), Button("Render", variant="primary"), gap="sm"),
        Tree(["Clip", "Type"], rows(clips, "GetName", call("GetClipProperty", "Type"))),
        gap="md", padding="md",
    )
]))
```

- **Three authoring modes** — composition functions, dicts/JSON, or
  class-based `Component`s. They all produce the same tree and mix freely.
- **Retained rendering** — keyed reconciliation patches individual native
  properties, so focus, caret position, scroll offset, selection and tree
  expansion survive updates. No full re-render.
- **Tables without boilerplate** — `rows()` derives `Tree`/`List` rows from the
  objects Resolve hands you, and `children=` recurses, so a full media pool
  browser is one call.
- **Two-way binding** — bind a `Value` to any control and it reads *and* writes.
  `TwoWay(read=..., write=...)` handles stored/native representation differences.
- **Real theming** — Qt stylesheets with hover, pressed, focus and disabled
  states; light and dark ship ready-made and cascade through subtrees.
- **Native escape hatch** — anything not wrapped is one `native(...)` call away
  and mixes with framework widgets in the same container.
- **Testable headlessly** — `MockBackend` mirrors the element tree; `require`,
  `fire`, `type_into`, `rows` and friends make UI tests short and precise.

Full guide: [`docs/ui.md`](docs/ui.md).

## Library API

`ResolveScript` is a first-class Python package — import it in any script:

```python
import ResolveScript as rs

# scaffold a new project
root, written = rs.scaffold_project("my_tool", destination=".")

# static analysis
issues = rs.analyze_project(root)

# load & validate manifest
manifest = rs.load_manifest(root / "manifest.json")
rs.validate_manifest_or_throw(manifest)

# consolidate to a single file
cfg = rs.config_from_manifest(root, manifest)
result = rs.consolidate(cfg)
print(rs.summarize(result, cfg))

# package a release artifact
pkg = rs.package_project(root)
print(pkg.archive)
```

Every failure the library raises derives from `rs.ResolveScriptError`, so a single `except` catches them all — while the historical types keep working for existing handlers (`SpecError` is still a `ValueError`, `FetchError` still a `RuntimeError`, …):

```python
try:
    rs.validate_manifest_or_throw(manifest)
except rs.ResolveScriptError as exc:
    print(f"resolvescript failed: {exc}")
```

Every name exported at the package root is also available from its owning submodule, e.g. `rs.consolidate` mirrors `ResolveScript.consolidate.consolidate`. The major subpackages are:

- `ResolveScript.manifest` — model, loaders, validators
- `ResolveScript.sandbox` — mock Resolve API, smoke runs, REPL
- `ResolveScript.sources` — archive/GitHub/known-source helpers
- `ResolveScript.install` — install, registry, target resolution
- `ResolveScript.ui` — declarative, reactive UI framework (see [`docs/ui.md`](docs/ui.md))

Version: `rs.get_version()` returns the installed version string.

## Development

```console
python -m venv .venv
.\.venv\Scripts\activate        # Windows; source .venv/bin/activate elsewhere
pip install -e ".[dev]"
pytest
ruff check .
```

Milestones and the full plan live in [`TODO.md`](TODO.md). CI runs the shared `OseMine/workflows` action; cutting a `vX.Y.Z` tag runs the release pipeline (sdist+wheel, checksums, GitHub release, optional PyPI publishing).