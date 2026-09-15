# resolvescript

Build, test, package and install [DaVinci Resolve](https://www.blackmagicdesign.com/products/davinciresolve) Python scripts and plugins: a small CLI with an npm-style workflow for the Resolve `Scripts/` tree.

- `create` scaffolds a project with a `manifest.json` and smoke tests
- `dev` / `test` run against a mock `DaVinciResolveScript` API - no Resolve needed
- `build` consolidates the multi-file package into a single `.py` for distribution
- `add` / `install` / `update` resolve dependencies from GitHub, URLs, archives or local folders and record them in `resolvescript.json`
- `package` emits `dist/<name>-<version>.tar.gz` plus `SHA256SUMS.txt`

Install with pip: `pip install resolvescript` (Python 3.12+).

## Quickstart

```console
$ resolvescript create my-cool-tool
$ cd my-cool-tool
$ resolvescript dev        # sandboxed dev loop against the mock API
$ resolvescript test       # run the smoke tests
$ resolvescript build      # single-file build -> dist/my_cool_tool.py
$ resolvescript analyze    # static checks (imports, manifest, API usage)
$ resolvescript package    # dist/my-cool-tool-0.1.0.tar.gz + SHA256SUMS.txt

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
| `create <name>` | Scaffold a new project (`--json`/`--xml`, `--template minimal\|toolkit`, `--dir`) |
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
| `manage list\|remove` | Low-level registry operations (`--json`, `--all`) |

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
  "version": "0.1.0",              // required, semver
  "author": "You",
  "description": "...",
  "python": "my_cool_tool",        // package/module name (defaults to "name")
  "entrypoint": "export.py",       // recommended CLI/bootstrap module
  "kind": "script",                 // "script" (default) | "extension" (plugin)
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

## Frameworks

`resolvescript` ships a mock `DaVinciResolveScript` module with a faithful-enough Resolve color/editing/page object model for testing, plus `resolvescript test --api-coverage` to report which mock methods your tests actually exercise.

## Development

```console
python -m venv .venv
.\.venv\Scripts\activate        # Windows; source .venv/bin/activate elsewhere
pip install -e ".[dev]"
pytest
ruff check .
```

Milestones and the full plan live in [`TODO.md`](TODO.md). CI runs the shared `OseMine/workflows` action; cutting a `vX.Y.Z` tag runs the release pipeline (sdist+wheel, checksums, GitHub release, optional PyPI publishing).