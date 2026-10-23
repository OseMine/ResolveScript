# ResolveScript — Plan & Todos

> A Python **CLI and library framework** for **building, coding, testing,
> packaging and installing DaVinci Resolve extensions** — distributed as
> `pip install resolvescript`.
>
> Generalizes the workflow proven in `X:\coding\Rotoscope`:
> multi-file package → consolidated single-file → installed into Resolve's
> Fusion Scripts folder. Projects are **manifest-driven**: a `manifest.json`
> (or `manifest.xml`) tells the CLI what to build, where to install, and what
> tests/dev tooling apply.
>
> **Consuming** extensions works like a package manager (the npm / pnpm /
> `tauri add` / `expo install` model): declare them in a committed
> `resolvescript.json`, and the CLI resolves the exact artifact, verifies its
> SHA-256, installs it, and tracks every install in a lockfile so `update` /
> `remove` / `list` are deterministic.
>
> **Library API**: every CLI feature is also available as a Python API:
> `import ResolveScript as rs` gives you scaffold, analyze, consolidate,
> package, install, sandbox, UI, fuse, workflow, manifest loaders, spec
> resolution, and more — usable in scripts, REPLs, and build automation
> without invoking the CLI.

**Last synced:** 2026-10-23 · **Version:** 1.1.0 (`v1.1.0`) · **Python:** 3.9+

**Status:** M0–M16 shipped. All P0 items complete. Work is now optional P1/P2 backlog in §9.

---

## 0. Terminology — the artifact classes

ResolveScript handles four artifact classes. They share manifests, packaging
and (for scripts/plugins) the resolver and SHA-256 pipeline, but they install
to different places and are managed by different command groups.

| | **Resolve script** | **ResolveScript extension** (plugin) | **Workflow integration** | **Fusion fuse** |
|---|---|---|---|---|
| What it is | A user-facing tool that runs **inside DaVinci Resolve** (Fusion): roto helper, comp utility, LUT tool… | An add-on that **extends the `resolvescript` CLI itself**: commands, sources, hooks, templates, mocks | A module Resolve scans for and launches under **Workspace > Workflow Integrations** | A scripted Lua `.fuse` plugin Fusion compiles on the fly; `.plugin` binaries are deploy-only |
| Manifest `kind` | `"script"` (default) | `"extension"` | `"workflow"` | `"fuse"` |
| Lives in | Resolve's Fusion Scripts root (`Scripts/Comp`, `Scripts/Utility`, …) | CLI config dir (`~/.config/ResolveScript/plugins/`, `%APPDATA%\ResolveScript\plugins\`) | Resolve's Workflow Integration Plugins dir | Fusion's `Fuses/` or `Plugins/` directory |
| Managed by | `create` · `dev` · `test` · `build` · `package` · `add` · `install` · `update` · `remove` · `search` | `extensions add/remove/list` | `workflow build/install/…` | `fuse build/install/package/…` |
| Executed with | Resolve's bundled Python in-app | `resolvescript` itself (pip-installed Python) | Resolve launches the launcher / Electron shell | Fusion's Lua runtime |
| Example | `rotoscope` — media/timeframe/polyline tool | `resolvescript-lint` — adds `analyze-extra` | a delivery/render panel | `Posterize.fuse` |

**Conventions used below:**

- Bare **"extension"** means a **Resolve script** installed into DaVinci Resolve.
- A **framework extension** / **plugin** installs into the CLI, never Resolve.
- A **workflow** is not a script in the Scripts tree; it has its own plugins root.
- A **fuse** is not a Python script; the framework generates and validates Lua.
- Shipped plugins use `manifest.json` with `kind: "extension"`; a standalone
  `plugin.json` is also accepted for plugin-only projects.
- Scripts and plugins share one specifier grammar, integrity and lockfile
  pipeline (§4.4, §5). Fuses/workflows are project-built and installed through
  their own command groups; they are not `add`-able registry artifacts today
  (see §9).

---

## 1. Goal

Replace the hand-rolled, project-specific scripts in Rotoscope
(`scripts/build.py`, `scripts/install.py`, `scripts/install.lua`,
`dev/sandbox.py`, tests, release workflow) with a **generic, pip-installable
CLI and library framework** that any Resolve extension project can use — now
also covering Fusion fuses, workflow integrations, declarative UI and CLI
plugins.

### CLI surface (v1.1.0)

```console
pip install resolvescript

resolvescript create my_extension        # scaffold (minimal, pydavinci, davinci-rest,
                                         #   lua, workflow, fuse, ui, extension)
resolvescript dev                        # sandboxed dev loop in-project
resolvescript test                       # tests against the mock Resolve API
resolvescript analyze                    # static checks
resolvescript build                      # consolidate multi-file -> single-file
                                         #   --installable emits a Lua installer
resolvescript package                    # release artifacts (tar.gz + SHA256SUMS)

# install — package-manager style (npm/pnpm, `tauri add`, `expo install`)
resolvescript add <spec>                 # install + record in resolvescript.json
resolvescript install                    # materialize everything recorded
resolvescript install <spec>             # one-off install, no recording
resolvescript update [<name>]            # re-resolve; --fix realigns compat
resolvescript upgrade                    # alias for update
resolvescript remove <name>              # uninstall + unrecord
resolvescript search <query>             # discover scripts (known table)
resolvescript doctor                     # diagnose setup (--json)
resolvescript clean                      # caches, dist/, registries, __pycache__

resolvescript manage list                # installed extensions (install.json)
resolvescript manage remove [--all]      # low-level registry removal
resolvescript consolidate <package>      # merge any package dir into one .py
resolvescript extensions add/remove/list # framework extensions (CLI plugins)

resolvescript workflow build|install|install-script|install-plugin|list|uninstall|root|describe
resolvescript fuse build|install|package|list|uninstall|root|describe
```

### Library surface

```python
import ResolveScript as rs

root, written = rs.scaffold_project("my_tool", destination=".")
issues = rs.analyze_project(root)
manifest = rs.load_manifest(root / "manifest.json")
rs.validate_manifest_or_throw(manifest)
cfg = rs.config_from_manifest(root, manifest)
result = rs.consolidate(cfg)
pkg = rs.package_project(root)

from ResolveScript.sandbox import build_default_env, fake_resolve_module, run_smoke
from ResolveScript.install import install_project

# specialised frameworks
from ResolveScript.ui import Window, Column, Button, Value, run
from ResolveScript.fuse import Fuse, Control, BinaryPlugin
from ResolveScript.workflow import Integration, Context
```

`add/install/update/remove/search` operate on **Resolve scripts**. Manage
**ResolveScript extensions** (plugins) via the `extensions` subgroup. Both
share the same specifier grammar (§4.4, §5).

Where `<spec>` is one of (reused by `add` / `install` / `update`):

```
name                          # known-extension table (latest)
name@1.2.3                    # index version, semver range, or dist-tag
owner/repo                    # implies github:owner/repo
github:owner/repo[#ref]       # git source; #semver:^1.0 → range over tags
git+https://host/repo.git#ref
https://host/ext-0.2.0.tgz    # archive (tar.gz / .zip), manifest at root
https://host/manifest.json    # manifest URL → points at the artifact
file:./tools/comp -or- ./dir  # local path / workspace link
```

The PyPI name `resolvescript` is in use (v1.1.0 tagged; see M15).

---

## 3. Project layout (actual, v1.1.0)

```text
ResolveScript/
├── TODO.md                       # this plan
├── pyproject.toml                # package resolvescript, version 1.1.0
├── README.md
├── CHANGELOG.md
├── LICENSE
├── docs/
│   ├── cli.md  manifest.md  templates.md  install.md  installer.md
│   ├── testing.md  consolidate.md  fuse.md  ui.md  workflow.md
│   └── github-actions.md
├── examples/resolvescript-lint/  # first-party CLI plugin
├── scripts/dryrun_release.py
├── src/ResolveScript/
│   ├── __init__.py               # 140+ public names, __version__
│   ├── _version.py
│   ├── cli.py                    # single argparse entry point
│   ├── config.py  errors.py  doctor.py
│   ├── scaffold.py  analyze.py  consolidate.py  package.py
│   ├── resolver.py  spec.py  semver.py  fetch.py
│   ├── workspace.py  installer_lua.py
│   ├── extensions/               # framework extension (CLI plugin) management
│   │   ├── config.py  errors.py  hooks.py  loader.py
│   │   ├── manager.py  manifest.py  registry.py
│   ├── manifest/                 # model, json_reader, xml_reader, validation
│   ├── sources/                  # known, archive, git, release
│   ├── install/                  # discovery, installer, registry
│   ├── sandbox/                  # api, env, loader, repl, smoke
│   ├── fuse/                     # model, render, validate, build, paths
│   ├── ui/                       # node, spec, dsl, components, state, events,
│   │                             #   render, rows, theme, app, jsonio, errors
│   │   └── backends/             # base, fusion (UIManager), mock
│   ├── workflow/                 # model, script, plugin, bridge, runtime,
│   │                             #   build, paths, testing
│   ├── testing/fixtures.py       # pytest fixtures
│   ├── templates/
│   │   ├── extension/            # minimal Resolve script (JSON/XML)
│   │   ├── external/             # pydavinci, davinci_rest
│   │   ├── lua/                  # pure Lua script
│   │   ├── workflow/             # Integration + Electron shell
│   │   ├── fuse/                 # Fuse declaration
│   │   ├── ui/                   # structured UI project
│   │   ├── plugin/               # framework extension (CLI plugin)
│   │   └── inapp/register.py     # in-app registration helper
│   └── py.typed
├── tests/                        # 518 test functions across 18 files
│   ├── test_ui.py (141)          test_fuse.py (130)
│   ├── test_sandbox.py (32)      test_consolidate.py (30)
│   ├── test_runtime.py (29)      test_install.py (23)
│   ├── test_manifest.py (20)     test_plugins.py (19)
│   ├── test_scaffold.py (15)     test_installer_lua.py (13)
│   ├── test_doctor.py (13)       test_security.py (12)
│   ├── test_library.py (12)      test_analyze.py (10)
│   ├── test_package.py (6)       test_cli.py (6)
│   ├── test_errors.py (5)        test_manage.py (2)
│   └── conftest.py               # hermetic plugin-registry isolation
└── .github/
    ├── actions/                  # setup, ci, test, analyze, build, package,
    │                             #   install, manage, update, extensions, fuse,
    │                             #   plugin, workflow, release, security-scan,
    │                             #   dependency-check, consolidate, build-installable
    └── workflows/                # ci, nightly, release, build, dependencies,
                                  #   fuse, security, workflow
```

Note: `poetry.lock` is currently untracked and not referenced by
`pyproject.toml` tooling; decide whether to commit, ignore, or delete it (§9).

---

## 4. Manifest schema (v1.1)

JSON is primary. XML mirrors it for script + `<extension>` manifests; the
workflow/fuse blocks are JSON-only today (§4.2). `docs/manifest.md` is the
detailed reference; this section records the shape the plan depends on.

### 4.1 `manifest.json` — script

```jsonc
{
  "name": "my_extension",
  "version": "1.1.0",                       // strict semver
  "author": "You",
  "description": "Rotoscoping helper",
  "python": "my_extension",                 // import name (optional)
  "id": "io.github.ose.my_extension",       // stable identity for `manage`
  "kind": "script",                         // script | extension | workflow | fuse
  "compat": {
    "resolve": ">=18.5",                    // consumed by `update --fix`
    "python": ">=3.10"                      // min bundled Python
  },
  "package_dir": "src/my_extension",        // default: extension root
  "entrypoint": "my_extension.py",          // optional in-app script entry
  "targets": ["Comp", "Utility"],           // Fusion/Scripts subfolders
  "scripts_root": "",                       // parsed today, not yet consumed — §9
  "release": {
    "owner": "OseMine",
    "repo": "my_extension",                 // → github:OseMine/my_extension
    "url": ""                               // exact artifact, overrides owner/repo
  },
  "consolidate": {
    "enabled": true,
    "output": "my_extension.py",            // in dist/ and install
    "entry": "my_extension/__init__.py",
    "exclude": ["tests", "other_module"],
    "no_comment": ["sys", "os"]
  },
  "dependencies": [                          // parsed metadata today; not consumed
    "github:someone/helper#semver:^1.2"      //   by add/install yet — see §9
  ],
  "install": {
    "as_directory": true,                   // copy package dir vs single file
    "include": ["my_extension/**", "manifest.json"],
    "exclude": ["**/__pycache__/**"],
    "to": "resolve"                         // resolve | framework
  }
}
```

### 4.2 `manifest.xml`

Equivalent subset, read by `xml.etree.ElementTree` into the same model. The
XML reader currently models script fields plus the `<extension>` block; the
`<workflow>` and `<fusion>` blocks are **JSON-only** today (both in the reader
and in the scaffold templates). The `lua`, `workflow` and `fuse` scaffold
flavors therefore emit JSON only, and `create --fmt xml` is ignored for them.

### 4.3 Target folder mapping (per OS)

| `target` | Windows (`%APPDATA%`) | macOS |
|---|---|---|
| `Comp` | `Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Comp` | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Comp` |
| `Utility` | `…/Scripts/Utility` | same |
| `Tool` / `Render` / `Deliver` / `Edit` / `WorkflowIntegrations` | similar subtrees | similar subtrees |
| `Fusion` | `…/Scripts/Fusion` | same |
| `root` | `…/Scripts` | same |

Linux fallback: `~/.local/share/DaVinciResolve/Fusion/Scripts/…`.

Fuses and workflow integrations do **not** use the Scripts root; they use the
Fusion `Fuses/`/`Plugins/` and Workflow Integration Plugins directories.

### 4.4 Workspace config — `resolvescript.json`

The consumer side, committed next to the project:

```json
{
  "name": "my-studio-resolve",
  "dependencies": {
    "rotoscope": "github:OseMine/Rotoscope#v0.4.0",
    "lut_helpers": "https://example.com/lut_helpers-0.2.0.tgz",
    "comp_tools": "^2.1.0",
    "local-tools": "file:./tools/comp"
  },
  "install": {
    "targets": ["Comp", "Utility"],
    "allow_remote": true,
    "scripts_root": ""
  }
}
```

Resolution rule (npm parity): recorded specifiers are the *declared* target;
the resolved exact artifact lives in `.resolvescript/install.json` and wins
while it still satisfies the recorded range.

**Implementation status:** Fully wired. `workspace.py` reads/writes the complete
`install` block (`targets`, `allow_remote`, `scripts_root`) with CLI/env
precedence (see §5 `install` command).

### 4.5 Plugin manifest — `kind: "extension"`

A plugin extends the CLI and installs into the CLI config dir, never Resolve.
Shipped form (also used by `create --template extension`):

```jsonc
{
  "name": "resolvescript-lint",
  "version": "1.2.0",
  "kind": "extension",
  "entrypoint": "resolvescript_lint.py",     // imported by the CLI at startup
  "description": "Extra static checks",
  "release": { "owner": "OseMine", "repo": "resolvescript-lint" },
  "consolidate": { "enabled": false },
  "install": { "to": "framework" },
  "extension": {
    "extension_kind": "commands",            // commands | sources | hooks | templates | provides
    "commands": ["analyze-extra"],
    "sources": ["registry:"],
    "hooks": {
      "pre_build": "hooks.on_pre_build",
      "post_install": "hooks.on_post_install"
    },
    "templates": ["toolkit"],
    "provides": ["mocks:resolve19"],
    "requires": {
      "resolvescript": ">=1.0.2",
      "python": ">=3.9"
    }
  }
}
```

A standalone `plugin.json` with the same fields is accepted for plugin-only
projects. The entry module must expose `register_commands(parser)`.
**`commands` and lifecycle hooks (`pre_build`, `post_install`) are wired;**
`sources`, `templates` and `provides` are stored and round-tripped but
have no dispatch table yet (see §9). Version gates skip a plugin with a
warning rather than crashing the CLI.

### 4.6 Workflow and fuse blocks

Workflow (`kind: "workflow"`):

```json
"workflow": {
  "id": "com.acme.deliver",
  "name": "Deliver",
  "version": "1.0.0",
  "description": "Kick off a delivery render.",
  "entrypoint": "my_pkg.workflow:INTEGRATION",
  "callbacks": ["RenderStart", "RenderStop"],
  "electron": true
}
```

Fuse (`kind: "fuse"`):

```json
"fusion": {
  "entrypoint": "my_pkg.fuse:FUSE",
  "class_name": "Posterize",
  "display_name": "Posterize",
  "category": "Fuses\\Vendor\\Tool",
  "icon_string": "PST",
  "description": "Reduce an image to N levels.",
  "tool_type": "CT_Tool",
  "binary": "vendor/Krokodove.plugin"
}
```

`binary` is a prebuilt `.plugin` carried/deployed, never compiled by this
framework. A wrong `class_name` is a silent no-show in Fusion, so builds run a
structural check always and `luac -p` when available.

### 4.7 Environment overrides

| Variable | Purpose |
|---|---|
| `RESOLVESCRIPT_SCRIPTS_ROOT` | Resolve Fusion Scripts root |
| `RESOLVESCRIPT_FUSES_ROOT` | Fusion `Fuses/` directory |
| `RESOLVESCRIPT_FUSION_PLUGINS_ROOT` | Fusion compiled `Plugins/` directory |
| `RESOLVESCRIPT_WORKFLOWS_ROOT` | Workflow Integration Plugins directory |
| `RESOLVESCRIPT_CONFIG_DIR` | CLI config dir / plugin registry |
| `RESOLVESCRIPT_ALLOW_REMOTE` / `..._ALLOW_NETWORK` | supply-chain gate |
| `RESOLVESCRIPT_MODULE`, `..._BUILT_PATH`, `..._TARGET`, `..._PYTHON`, `..._COMPAT`, `..._USER`, `..._VERSION` | test/scaffold substitution hooks |

Other overrides: `--scripts-root`, `--root` on `fuse`/`workflow`. The
`install.scripts_root` / `install.allow_remote` keys in `resolvescript.json`
are documented but **not wired yet**; use the environment/CLI overrides above
(§9). The manifest `scripts_root` field is likewise parsed but not consumed.

---

## 5. Command reference (as implemented)

### Project commands

- **`create <name> [--json|--xml] [--dir DIR] [--template T]`**
  Scaffolds `minimal`, `pydavinci`, `davinci-rest`, `lua`, `workflow`, `fuse`,
  `ui`, `extension` (CLI plugin). Fails if the destination is non-empty.
- **`dev [--built] [--repl] [--editor]`** — mock Resolve environment; `--built`
  loads the consolidated file; `--editor` prints an in-app script.
- **`test [--built] [-k PATTERN] [--api-coverage]`** — runs the project's
  pytest suite with the mock injected; coverage reports used-vs-mocked methods.
- **`analyze [--json]`** — syntax-compiles files, reports unused imports,
  manifest issues, unmocked API calls, `GetAttrs()` keys and target typos.
- **`build [--output PATH] [--installable] [--installer-template PATH]`** —
  consolidates to `dist/`; `--installable` emits a Lua installer instead of
  Python.
- **`package [--dist DIR]`** — single file, manifest, `SHA256SUMS.txt`, and
  `dist/<name>-<version>.tar.gz` in the shape `add` consumes.
- **`consolidate <package-dir> --output PATH`** — manifest-free consolidation.
- **`clean [--dir DIR] [-v]`** — caches, `dist/`, registries, `__pycache__`.

### Dependency commands (scripts/plugins)

- **`add <spec> [--target NAME] [--no-save] [--scripts-root DIR]`** — resolve →
  download → SHA-256 verify → stage → `py_compile` → install → record.
  Idempotent; conflict detection.
- **`install [<spec>] [--scripts-root DIR] [--locked] [--dry-run]`** — with no
  spec, materialize `resolvescript.json` or install the current project; with a
  spec, one-off install.
- **`update [<name>] [--precise VERSION] [--fix]`** — advance within ranges;
  `--fix` realigns installed artifacts to `compat`.
- **`upgrade`** — alias for `update`.
- **`remove <name> [--no-save]`** — uninstall tracked files and unrecord.
- **`search <query>`** — known table + naming conventions.
- **`manage list [--json]` / `manage remove <name> [--all]`** — low-level
  registry operations against `.resolvescript/install.json`.

### Diagnostics

- **`doctor [--scripts-root DIR] [--json]`** — 7 checks: interpreter, template
  package-data, Scripts root, env overrides, project manifest, workspace,
  install registry. Exit 1 on failure; library form `doctor.run_checks()`.
- **`--version`, `--help`, `<cmd> --help`**; `-v` (info) / `-vv` (debug).
- Exit codes: `0` ok, `1` error, `2` usage.

### Framework extensions (CLI plugins)

- **`extensions add <spec> [--force]`** — same resolve/verify/stage pipeline,
  then version-gate, write to the plugin dir and register in `plugins.json`.
- **`extensions remove <name>`**, **`extensions list [--json]`**.
- Plugin commands appear in `resolvescript --help`; unloadable plugins are
  skipped with a warning.

### Workflow integrations

- **`workflow build [--entrypoint PKG:ATTR] [--project-root DIR]`** — launcher
  + optional Electron shell into `dist/`.
- **`workflow install|install-script|install-plugin [--root DIR]`**,
  **`list`**, **`uninstall`**, **`root`**, **`describe`**.

### Fusion fuses

- **`fuse build [--out DIR] [--stdout] [--no-check]`** — render/validate Lua.
- **`fuse install [--root DIR] [--dry-run] [--no-check]`**.
- **`fuse package [--dist DIR] [--plugin PATH] [--name NAME] [--no-check]`** —
  zip with checksum; can carry a prebuilt `.plugin`.
- **`fuse list|uninstall|root [--which Fuses|Plugins] [--list]|describe`**.

> **`resolvescript plugin install|list|uninstall`** is now implemented
> (`--name`, `--target`, `--notes`, `--no-force`, `--dry-run`, `--root`, `--json`).
> See `docs/plugin.md`.

---

## 6. Design decisions / open questions

1. **CLI library** — `argparse`, zero dependencies. Revisit only if the command
   surface grows beyond comfortable single-parser size; so far it has not.
2. **Mock fidelity** — the sandbox mirrors the Resolve API the toolkit uses, not
   the full API. Unmocked calls raise `NotImplementedError`; `analyze` and
   `--api-coverage` surface them. Auto-generation is backlog (§9).
3. **Repo-local install** — `--scripts-root` (and, once wired,
   `install.scripts_root`) targets a project-local copy. Installing into a
   Resolve *database* project is only possible via the Resolve API at runtime,
   so the in-app registration helper is shipped as a script, not a CLI
   operation.
4. **XML reader** — stdlib `xml.etree.ElementTree`; same model as JSON for
   script/extension fields; no XSD.
5. **Python target** — framework runs on ≥3.9; generated extensions target the
   Resolve-bundled interpreter (≥3.10 for Resolve 18.5+) and stay stdlib-only at
   runtime. Manifest `dependencies` are metadata only today (not resolved by
   the installer — §9).
6. **Release/nightly CI** — `.github/workflows/` plus reusable composite actions
   in `.github/actions/`; `release.yml` builds, type-checks, generates notes and
   publishes (PyPI behind the repo variable / OIDC trusted publishing).
7. **Extension install is a package manager** — author side: `build` +
   `package`; consumer side: `add` / `install <spec>` / `update` / `remove` /
   `search`.
8. **Two-layer state** — declared specs/ranges in `resolvescript.json`; exact
   pins (`resolved` URL, git ref, `integrity` SHA-256) in
   `.resolvescript/install.json`. Lockfile wins while it satisfies the range.
9. **No central registry in v1** — hardcoded known table + `owner/repo` +
   arbitrary URLs. A static JSON index with dist-tags and per-version `compat`
   remains the v2 path.
10. **Archive over git** — public repos fetch via codeload/tar.gz with pure
    `urllib`; `git` CLI only as fallback. `#semver:` resolves release tags.
11. **Mandatory integrity** — every installed `.py` can be executed on demand, so
    SHA-256 verification is non-negotiable. Provenance is recorded alongside.
12. **Idempotent install-time codegen** — menu entry / Lua installer wiring is
    rendered during `add`/`install` and skipped when already present.
13. **Scripts and plugins are one pipeline, two targets** — same specifier,
    fetch, verify, stage and registry shape; different destination and gate.
14. **UI is declarative and retained** — one node tree, three authoring modes
    (functions, dicts/JSON, `Component` classes), rendered through
    `FusionBackend` (real UIManager) or `MockBackend` (headless tests). Keyed
    reconciliation patches only changed native props, preserving focus, caret,
    scroll, selection and tree expansion.
15. **Fuses are rendered, not copied** — a Python `Fuse` declaration emits
    ASCII-only Lua. Validation is two-layer: structure always, `luac -p` when
    available. `.plugin` binaries are deploy/package/remove only.
16. **Workflows are script-first** — the portable Python launcher works on
    Linux and uses `ResolveScript.ui`; the Electron shell is optional and
    Windows/macOS Studio-only. The script is the brain; the shell is a bridge.
17. **Templates are file trees** — `@NAME@`/`@VERSION@` placeholders are copied,
    not rendered by Jinja; `.j2` files are optional installer/manifest
    templates. `minimal` maps to the `extension/` directory (script) while
    `extension` maps to `plugin/` (CLI plugin) to avoid the §0 name collision.
18. **Plugins are isolated** — a broken plugin, missing hook, bad version gate
    or corrupt registry is a warning, never a CLI crash. Tests isolate the
    host's plugin registry via `tests/conftest.py`.
19. **Docs are part of the contract** — command surfaces and version strings
    must match the implementation; `doctor` checks templates/env/registry, and
    the release workflow type-checks.

---

## 7. Milestones

### Shipped: M0–M10 (v0.1.0 → v1.0.2; M5c completed in v1.1.0)

| Milestone | Outcome | Evidence |
|---|---|---|
| **M0** Repo bootstrap | package, CLI skeleton, CI/release workflows | `pyproject.toml`, `.github/` |
| **M1** Manifest | dataclass model, JSON + XML readers, validation | `test_manifest.py` |
| **M2** Scaffolder | `create`, JSON/XML manifests, template copy engine | `test_scaffold.py` |
| **M3** Consolidator | generic import rewriting, dependency order, `py_compile` | `test_consolidate.py` |
| **M4** Sandbox | fake Resolve API, env injection, smoke, REPL, fixtures | `test_sandbox.py` |
| **M5** Installer core | per-OS roots, atomic install, registry, conflicts | `test_install.py` |
| **M5b** Sources/lockfile | spec grammar, semver, known/archive/git/path/release, SHA-256, `resolvescript.json` | `test_runtime.py` |
| **M5c** Framework extensions | plugin manifest/gate/loader/registry, `extensions add/remove/list` | `test_plugins.py` |
| **M6** Analyzer | syntax/import/manifest/API checks, `--json`, `--api-coverage` | `test_analyze.py` |
| **M7** Packager | tar.gz single-root artifact + `SHA256SUMS.txt` | `test_package.py` |
| **M8** Manager/polish | `manage`, cross-platform paths, help/exit codes, e2e author+consumer | `test_manage.py`, `test_cli.py` |
| **M9** Publish/docs | 1.0.2 wheel/tag/release, README/manifest/specifier docs | tag `v1.0.2` |
| **M10** Hardening | `ResolveScriptError` taxonomy, `py.typed` + mypy, `doctor`, logging | `test_errors.py`, `test_doctor.py` |

### M11 — Fusion fuses and `.plugin` deployment — shipped
Tag `v0.6.0`; documented in 1.0.0.
- [x] `Fuse`/`Control` declaration model + ASCII Lua renderer
- [x] Structural validation always, `luac -p` when available
- [x] `fuse build|install|package|list|uninstall|root|describe`
- [x] Per-OS Fuses/Plugins roots with env + `--root` overrides
- [x] Checksummed `.zip` packaging; optional prebuilt `.plugin` carried along
- [x] `BinaryPlugin` deploy/package model (no source build)
- [x] `create --template fuse` scaffold + smoke test
- [x] `test_fuse.py` (130 test functions)

### M12 — Declarative UI framework — shipped
Tag `v1.0.0`.
- [x] Node tree + widget specs for Fusion UIManager
- [x] Three authoring modes: functions, dicts/JSON, `Component` classes
- [x] Retained, keyed rendering with targeted prop patches
- [x] Two-way binding, `Value`/state, events, `rows()` table helpers
- [x] Theming (light/dark, Qt stylesheets), native escape hatch
- [x] `FusionBackend` + headless `MockBackend` with UI test helpers
- [x] `create --template ui` scaffold
- [x] `docs/ui.md` + `test_ui.py` (141 test functions)

### M13 — Workflow Integrations — shipped
Tag `v1.0.0`.
- [x] `Integration`/`Context` declaration and `Harness`
- [x] Portable Python launcher (Linux) + optional Electron shell
- [x] JSON line protocol between shell and Python
- [x] `RenderStart`/`RenderStop` callbacks
- [x] Separate Workflow Integration Plugins root + discovery
- [x] `workflow build|install|install-script|install-plugin|list|uninstall|root|describe`
- [x] `create --template workflow`; `docs/workflow.md`

### M14 — Templates, Lua installer, GitHub Actions — shipped
- [x] Templates: `minimal`, `pydavinci`, `davinci-rest`, `lua`, `workflow`, `fuse`, `ui`, `extension`
- [x] `build --installable` Lua installer + custom `installer.lua.j2`
- [x] In-app registration helper template
- [x] Composite actions for setup/test/analyze/build/package/install/manage/update/extensions/fuse/plugin/workflow/release/security/deps
- [x] Consumer example workflows in `.github/workflows/`
- [x] `docs/templates.md`, `docs/installer.md`, `docs/github-actions.md`
- [x] `test_installer_lua.py` (13 test functions)

### M15 — v1.1.0 release and plugin hardening — shipped
Tag `v1.1.0` (2026-10-08).
- [x] Unified `ResolveScriptError` taxonomy + contract test
- [x] `py.typed`, mypy config, 71 source files clean, type-check step in release
- [x] `doctor` (7 checks) + `-v`/`-vv` namespaced logging
- [x] M5c plugin management: `extensions add/remove/list`, version gate, isolation
- [x] XML `<extension>` block parity
- [x] `clean` command and `upgrade` alias
- [x] `create --template extension` plugin scaffold
- [x] `examples/resolvescript-lint` acceptance artifact
- [x] Version/doc drift fixes from the 1.0.2 audit

### M16 — Current truth pass — **completed (2026-10-23)**
- [x] Refresh this plan against the actual v1.1.0 tree (2026-10-23)
- [x] Record post-plan milestones M11–M15 and the real CLI/library surface
- [x] Deduplicate the backlog and re-rank known gaps
- [x] Fix the documentation/code mismatches listed in §9:
  - [x] `resolvescript plugin install|list|uninstall` CLI group implemented
  - [x] `docs/plugin.md` created
  - [x] README version table updated (`v1.0.2` → `v1.1.0`)
  - [x] `create --help` template choices synced with `scaffold.py` (`extension` added)
  - [x] `docs/templates.md` updated (`ui`, `extension`, JSON-only note)
- [x] `poetry.lock` removed (CI uses `pip`/`pyproject.toml`)
- [x] Full suite recorded in `CHANGELOG.md` (557 passed, 3 skipped; ruff/mypy clean)
- [x] Refactored `plugins.py` → `src/ResolveScript/extensions/` package (config, errors, hooks, loader, manager, manifest, registry)

### M17 — Ready for next release
- [ ] Cut v1.1.1 patch release (P0 maintenance complete)
- [ ] Begin P1 backlog: wire `sources`/`hooks`/`templates`/`provides` plugin contribution points

---

## 8. User workflows (acceptance scenarios)

**As a Resolve script author**
1. `pip install resolvescript`
2. `resolvescript create my_roto_tools && cd my_roto_tools`
3. Write code in `my_roto_tools/`, edit `manifest.json`
4. `resolvescript dev` — iterate against the mock, no Resolve needed
5. `resolvescript test` — green; `analyze` — clean
6. `resolvescript build` → `dist/my_roto_tools.py`
7. `resolvescript install` → Fusion Scripts/Comp; restart Resolve
8. `resolvescript manage list` — confirm entry

**As a consumer (package-manager style)**
1. `resolvescript add github:OseMine/rotoscope` — resolve, verify SHA-256,
   install, record in `resolvescript.json`
2. `resolvescript update rotoscope` — newer release within the range
3. `resolvescript search comp` — discover
4. `resolvescript remove rotoscope` — uninstall + unrecord

**Reproducible studio setups**
1. Commit `resolvescript.json`
2. Fresh machine: `resolvescript install` — fetch, verify, install
3. CI-safe: `resolvescript install --locked`

**As a framework-extension author/user**
1. `resolvescript create my-lint --template extension`
2. Implement `register_commands(parser)`, `package`/release it
3. `resolvescript extensions add github:you/my-lint` — version-gated, into the
   CLI config dir (never Resolve)
4. New command appears in `resolvescript --help`
5. `extensions remove my-lint`

**As a Fusion fuse author**
1. `resolvescript create Posterize --template fuse`
2. Edit `FUSE = Fuse(...)`
3. `resolvescript fuse build` — structural check (+ `luac -p` when available)
4. `resolvescript fuse install` — restart Resolve
5. `resolvescript fuse package` — checksummed zip, optional `.plugin` alongside

**As a workflow-integration author**
1. `resolvescript create Deliver --template workflow`
2. Declare `INTEGRATION = Integration(...)` and a `build_ui(context)` screen
3. `resolvescript workflow build` → launcher + Electron shell
4. `resolvescript workflow install` → `Workspace > Workflow Integrations`

**As a UI author**
1. `resolvescript create Panel --template ui`
2. Compose `Window`/`Column`/`Row`/`Button`/`Value`
3. Test headlessly with `MockBackend` (`require`, `fire`, `type_into`, `rows`)
4. `resolvescript package` and ship; the same tree renders in Resolve

---

## 9. Backlog / known gaps

**Policy:** core stays lean — optional features are candidates for a framework
extension (M5c plugin), not core commands, unless demand justifies promotion.

### P0 — truth and correctness (M16) — **all complete**

- [x] Implement the documented `resolvescript plugin` group for prebuilt
      `.plugin` deployment (`install|list|uninstall`, plus `--name`, `--target`,
      `--notes`, `--no-force`, `--dry-run`, `--root`, `--json`)
- [x] Add `docs/plugin.md` (README link now valid)
- [x] Update README version table (`v1.0.2` → `v1.1.0`) and template list
      (added `ui`, `extension`; removed nonexistent `plugin` claim)
- [x] Sync `create --help` template choices with `scaffold.py` and `docs/templates.md`
- [x] `poetry.lock` removed (CI uses `pip`/`pyproject.toml`)
- [x] Manifest `dependencies` documented as metadata only (README claim corrected)
- [x] Wire `scripts_root` manifest field and `resolvescript.json` `install` block
      (`targets`, `allow_remote`, `scripts_root`) — all honored with proper precedence
- [x] Clean full-suite run recorded in `CHANGELOG.md` (557 passed, ruff/mypy clean)

### P1 — next features

- [ ] Wire the plugin contribution points beyond `commands` and `hooks` (`sources`,
      `templates`, `provides`) or mark them explicitly as reserved in
      the manifest docs/validation. Today only `register_commands` and
      lifecycle hooks (`pre_build`, `post_install`) are called.
- [ ] Auto-generate mock methods from the real `DaVinciResolveScript.py` so
      `dev`/`test` never hit `NotImplementedError`; candidate plugin
      (`provides: mocks:*`).
- [ ] Static registry index (`registry.resolvescript.dev/extensions.json`) with
      dist-tags, per-version `compat` and archive URL patterns — upgrades
      `search`/`update` beyond the hardcoded known table.
- [ ] `resolvescript validate <dir>` — one-shot manifest + code check for first
      timers (candidate plugin; library validation already exists).
- [ ] `resolvescript publish <ext>` — push a built artifact to a release or
      registry without hand-written CI.
- [ ] `resolvescript watch` — rebuild + reinstall on change (hot dev loop;
      candidate plugin).
- [ ] Make fuses/workflows consumable through the specifier pipeline
      (`add`/`install <spec>` with kind-aware destinations and registry entries).

### P2 — conveniences

- [ ] Lua command mirror (`resolvescript lua-script manifest.xml`) bundling a
      Lua installer into the extension (candidate plugin).
- [ ] Windows context-menu integration (`Add to Resolve Scripts`).
- [ ] TOML manifest support if demand appears (candidate plugin).
- [ ] Richer per-kind `compat` checks beyond `update --fix` (Resolve/Python
      version matrix, dist-tag selection).
- [ ] Shell-completion generation (docs currently promise/describe it; verify
      it exists or implement it).

### Explicitly superseded / fixed

- Removed the duplicate "auto-generate mocks" backlog entry (appeared twice).
- The old `M5c` implementation gap is closed in v1.1.0.
- The old "7 checks" count for `doctor` remains accurate; re-verify if checks
  are added.

---

## 10. Definition of done (current)

- `pip install resolvescript` works from PyPI; `resolvescript --version` reports
  the tagged version (`1.1.0` at this sync).
- All project, dependency, diagnostics, plugin, workflow and fuse commands
  documented in §5 function end-to-end on Windows + macOS (primary) and Linux
  (best effort), once the M16 doc/code mismatches are resolved.
- Author and consumer acceptance flows (§8) are green in CI, including the
  package → serve → `add` → `update` → `install --locked` → `remove` loop.
- Every artifact-based install into the Resolve Scripts tree or the CLI plugin
  dir is SHA-256-verified before the destination is touched; builds are atomic
  and leave no partial installs. Local workspace-link installs are the explicit
  exception.
- Fuses validate structurally before install; `luac` validation is reported
  honestly when available. Workflows install only to their own plugins root.
- Docs cover every command, the specifier grammar, the manifest kinds and the
  §0 artifact-class split — **and match the actual CLI** (M16).
- `pytest`, `ruff` and `mypy` are clean in the release workflow; no stale
  version strings or dead documentation links remain.
- Framework-extension failures (version gate, import, missing hook, corrupt
  registry) are warnings, never CLI crashes.
