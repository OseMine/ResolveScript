# ResolveScript — Plan & Todos

> A Python **CLI and library framework** for **building, coding, testing,
> packaging and installing DaVinci Resolve Python extensions** — distributed as
> `pip install resolvescript`.
>
> Generalizes the workflow proven in `X:\coding\Rotoscope`:
> multi-file package → consolidated single-file → installed into Resolve's
> Fusion Scripts folder. Extensions are **manifest-driven**: a
> `manifest.json` (or `manifest.xml`) in the extension project tells the CLI
> what to build, where to install, and what tests/dev tooling apply.
>
> **Consuming** extensions works like a package manager (the npm / pnpm /
> `tauri add` / `expo install` model): declare them in a committed
> `resolvescript.json`, and the CLI resolves the exact artifact, verifies its
> SHA-256, installs it into Resolve, and tracks every install in a lockfile
> so `update` / `remove` / `list` are deterministic.
>
> **Library API**: every CLI feature is also available as a Python API:
> `import ResolveScript as rs` gives you scaffold, analyze, consolidate,
> package, install, sandbox, manifest loaders, spec resolution, and more —
> usable in scripts, REPLs, and build automation without invoking the CLI.

---

## 0. Terminology — two different kinds of "extension"

This plan uses the word *extension* for two different artifact classes. They
share the resolver/installer machinery but are distinctly named:

| | **Resolve script** (a.k.a. **Resolve extension**) | **ResolveScript extension** (a.k.a. **plugin**) |
|---|---|---|
| What it is | A user-facing tool that runs **inside DaVinci Resolve** (Fusion): a roto helper, comp utility, LUT tool… | An add-on that **extends the `resolvescript` CLI itself**: new commands, custom specifier sources, build hooks, scaffold templates, extra mock modules, alternate registry backends |
| Lives in | DaVinci Resolve's Fusion Scripts root (`Scripts/Comp`, `Scripts/Utility`, …) | The CLI's own user config dir (`~/.config/resolvescript/` / `%APPDATA%\resolvescript\`), loaded at CLI startup |
| Declared by | `manifest.json` / `manifest.xml` (a **script manifest**) | `plugin.json` with a `kind` (a **plugin manifest**, §4.5) |
| Managed by | `create` · `dev` · `test` · `build` · `package` · `add` · `install` · `update` · `remove` · `search` | `resolvescript extensions add/remove/list` |
| Executed with | DaVinci Resolve's bundled Python when the user runs the script in-app | `resolvescript` itself (`pip install`ed Python) when a command runs |
| Example | `rotoscope` — a media/timeframe/polyline tool | `resolvescript-lint` — a plugin adding an `analyze-extra` command or a `registry:` source |

**Convention used below:** bare "extension" always means a **Resolve script**
(installed into DaVinci Resolve). Framework add-ons are spelled
**"framework extension"** or **plugin** and install into the CLI, never into
Resolve. The pipeline is one: a plugin is a script whose `kind`/`install.to`
targets the framework instead of Resolve, so specifier grammar, integrity
(SHA-256), registry and lockfile are shared (see §4.5, §5, M5c).

---

## 1. Goal

Replace the hand-rolled, project-specific scripts in Rotoscope
(`scripts/build.py`, `scripts/install.py`, `scripts/install.lua`,
`dev/sandbox.py`, tests, release workflow) with a **generic, pip-installable
CLI and library framework** that any Resolve extension project can use.

### CLI usage

```
pip install resolvescript

resolvescript create my_extension        # scaffold a new extension project
resolvescript dev                        # sandboxed REPL / dev loop in-project
resolvescript test                       # run tests against the mock Resolve API
resolvescript analyze                    # static checks on the extension
resolvescript build                      # consolidate multi-file → single-file
resolvescript package                    # produce release artifacts (single-file + assets)

# install — package-manager style (npm/pnpm, `tauri add`, `expo install`)
resolvescript add <spec>                 # install + record into resolvescript.json (pnpm add / expo install)
resolvescript install                    # materialize everything recorded in resolvescript.json (npm install)
resolvescript install <spec>             # one-off install of a single spec, no recording (cargo install)
resolvescript update [<name>]            # re-resolve within recorded ranges; --fix realigns Resolve/Python compat
resolvescript remove <name>              # uninstall + unrecord (npm uninstall)
resolvescript search <query>             # discover extensions (known list; registry index later)

resolvescript manage list                # list installed extensions (reads .resolvescript/install.json)
resolvescript consolidate <package>      # one-off: merge a package dir into one .py
resolvescript extensions add <spec>      # install a FRAMEWORK extension (plugin, into the CLI, not Resolve)
resolvescript extensions remove <name>   # uninstall a plugin
resolvescript extensions list            # list installed plugins
```

### Library usage (scripted framework)

```
import ResolveScript as rs

# scaffold a new project
root, written = rs.scaffold_project("my_tool", destination=".")

# static analysis
issues = rs.analyze_project(root)
for issue in issues:
    print(issue)

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

# sandbox for testing
from rs.sandbox import build_default_env, fake_resolve_module, run_smoke
env = build_default_env()
fake_resolve_module(env)
run_smoke(my_module)
```

`add/install/update/remove/search` operate on **Resolve scripts**. Manage
**ResolveScript extensions** (plugins that extend the CLI) via the
`extensions` subgroup; both share the same specifier grammar (§0, §4.5, M5c).

Where `<spec>` is one of (documented once, reused by `add`/`install`/`update`):

```
name                          # known-extension table / registry index (latest)
name@1.2.3                    # index version, semver range, or dist-tag
owner/repo                    # implies github:owner/repo   (pnpm shorthand)
github:owner/repo[#ref]       # git source; #semver:^1.0 → range over release tags
git+https://host/repo.git#ref
https://host/ext-0.2.0.tgz    # archive (tar.gz / .zip) with manifest.json at root
https://host/manifest.json    # direct manifest URL → points at the artifact
file:./tools/comp -or- ./dir  # local path / workspace link
```

Name **`resolvescript`** is available on PyPI (verified 2026-09-14, 404).

---

## 2. How it maps to the Rotoscope battle-tested code

| Rotoscope component | Generalizes into | Command |
|---|---|---|
| `rotoscope/` package (core/timeline/clip/fusion/roto/utils) | becomes **template source** in `create`; framework stays API-agnostic | `create` |
| `scripts/build.py` (collect → topo-sort → strip internal imports → hoist `__future__` → emit) | `ResolveScript/consolidate.py` | `build`, `consolidate` |
| `dev/sandbox.py` (mock `DaVinciResolveScript`, smoke tests, REPL) | `ResolveScript/sandbox/` (reusable mock + runner) | `dev`, `test` |
| `dev/hello_resolve.py` | template in `create` | `create` |
| `scripts/install.py` (source/built/release modes, per-OS scripts root) | `ResolveScript/install.py` (manifest-driven) | `install` |
| `tests/test_build.py`, `tests/test_sandbox.py` | template + `ResolveScript.testing` helpers | `create`, `test` |
| `.github/workflows/release.yml` (build → artifact → release) | `resolvescript package` + CI template | `package` |

Key generalization point: **nothing in the framework is Rotoscope-specific**
except the mock API objects and the scaffolder templates. The consolidator,
installer, analyzer and test runner operate on *any* manifest-defined
extension.

---

## 3. Project layout (in this repo)

```
ResolveScript/
├── TODO.md                           # this plan
├── pyproject.toml                    # package resolvescript
├── README.md
├── LICENSE
├── src/
│   └── ResolveScript/
│       ├── __init__.py               # __version__
│       ├── cli.py                    # entry point: resolvescript
│       ├── config.py                 # locate/read Config (manifest discovery, env)
│       ├── manifest/
│       │   ├── __init__.py
│       │   ├── model.py              # Manifest dataclass (name, version, targets, …)
│       │   ├── json_reader.py
│       │   ├── xml_reader.py
│       │   └── validation.py         # schema lints + error messages
│       ├── consolidate.py            # port of scripts/build.py (generic)
│       ├── resolver.py               # specifier grammar + semver ranges + source dispatch
│       ├── sources/                  # known-table, manifest-URL, archive, git, path fetchers
│       │   ├── __init__.py
│       │   ├── known.py              # hardcoded known-extension table (Tauri model)
│       │   ├── manifest_url.py       # https://…/manifest.json → artifact
│       │   ├── archive.py            # tar.gz / .zip unpack (package/-root contract)
│       │   ├── git.py                # codeload archive preferred, `git` CLI fallback
│       │   └── path.py               # file:// and ./dir local/workspace links
│       ├── fetch.py                  # urllib download + mandatory SHA-256 integrity verify
│       ├── registry.py               # read/write .resolvescript/install.json (lockfile)
│       ├── workspace.py              # read/write resolvescript.json deps config
│       ├── install.py                # author + consumer install (atomic, verified)
│       ├── plugins.py                # framework-extension loader (plugin.json, entry points)
│       ├── manage.py                 # list / update / remove from the registry
│       ├── analyze.py                # static checks + API/coverage report
│       ├── package.py                # produce dist/ artifacts (+ the tarball `add` consumes)
│       ├── sandbox/
│       │   ├── __init__.py
│       │   ├── api.py                # mock Resolve/Fusion objects (from dev/sandbox.py)
│       │   ├── env.py                # build_default_env(), inject module
│       │   ├── smoke.py              # run_smoke() checks against a module
│       │   └── repl.py               # interactive session
│       ├── testing/
│       │   ├── __init__.py
│       │   └── fixtures.py           # pytest fixtures (install mock, load built/source)
│       ├── discovery.py              # locate Fusion Scripts root per OS
│       └── templates/
│           ├── extension/            # `create` scaffold (package + manifest + tests + sandbox)
│           ├── in_app_script.py.j2   # menu-style entry script template
│           └── lua_installer.lua.j2  # optional bundled Lua installer
├── tests/
│   ├── test_manifest.py
│   ├── test_consolidate.py
│   ├── test_install.py
│   ├── test_sandbox.py
│   ├── test_analyze.py
│   └── test_cli.py
└── .github/
    └── workflows/
        ├── ci.yml                    # lint + test the CLI itself
        └── release.yml               # publish resolvescript to PyPI + GH releases
```

---

## 4. Manifest schema (v1)

JSON is primary; XML is a 1:1 equivalent reader.

### 4.1 `manifest.json`

```json
{
  "name": "my_extension",
  "version": "0.1.0",                       // strict semver (MAJOR.MINOR.PATCH, optional -prerelease)
  "author": "You",
  "description": "Rotoscoping helper",
  "python": "rotoscope",                    // import name of the package (optional)
  "compat": {                               // Expo-style compatibility axis
    "resolve": ">=18.5",                    // min DaVinci Resolve version (SemVer range)
    "python": ">=3.10"                      // min bundled Python
  },
  "package_dir": "src/my_extension",        // default: extension root
  "entrypoint": "my_extension.py",          // optional in-app script entry
  "id": "io.github.ose.my_extension",       // stable identity for `manage` (name may change)
  "release": {                              // source of `add`/`install <spec>` from a published artifact
    "owner": "OseMine",
    "repo": "my_extension",                 // → resolves to github:OseMine/my_extension
    "url": ""                               // optional exact artifact (tarball/zip) → overrides owner/repo
  },
  "targets": [
    "Comp",                                 // Fusion/Scripts/Comp
    "Utility"                               // Fusion/Scripts/Utility
  ],
  "scripts_root": "",                       // override OS detection (rare); see also RESOLVESCRIPT_SCRIPTS_ROOT
  "consolidate": {
    "enabled": true,
    "output": "my_extension.py",            // in dist/ and install
    "entry": "my_extension/__init__.py",
    "exclude": ["tests", "other_module"],
    "no_comment": ["sys", "os"]             // never strip these imports
  },
  "dependencies": [],                       // pip deps for dev/test only — never installable at runtime
  "install": {
    "as_directory": true,                   // copy package dir vs single file
    "include": ["my_extension/**", "manifest.json"],
    "exclude": ["**/__pycache__/**"]
  }
}
```

### 4.2 `manifest.xml` (equivalent subset)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <name>my_extension</name>
  <id>io.github.ose.my_extension</id>         <!-- stable identity -->
  <version>0.1.0</version>                   <!-- strict semver -->
  <author>You</author>
  <description>Rotoscoping helper</description>
  <python>rotoscope</python>                 <!-- optional import name of the package -->
  <compat>
    <resolve>&gt;=18.5</resolve>
    <python>&gt;=3.10</python>
  </compat>
  <package_dir>src/my_extension</package_dir>
  <entrypoint>my_extension.py</entrypoint>
  <targets>
    <target>Comp</target>
    <target>Utility</target>
  </targets>
  <scripts_root></scripts_root>              <!-- override OS detection (rare) -->
  <consolidate enabled="true" output="my_extension.py">
    <entry>my_extension/__init__.py</entry>
    <exclude>tests</exclude>
    <exclude>other_module</exclude>
    <no_comment>sys</no_comment>
    <no_comment>os</no_comment>
  </consolidate>
  <dependencies></dependencies>              <!-- pip deps for dev/test only; emitted code is stdlib-only -->
  <install as_directory="true">
    <include>my_extension/**</include>
    <include>manifest.json</include>
    <exclude>**/__pycache__/**</exclude>
  </install>
  <release>
    <owner>OseMine</owner>
    <repo>my_extension</repo>
    <url></url>                              <!-- optional exact artifact, overrides owner/repo -->
  </release>
</manifest>
```

### 4.3 Target folder mapping (per OS, from Rotoscope's `discovery.py`)

| `target`  | Win (`%APPDATA%`) | macOS |
|---|---|---|
| `Comp`    | `Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Comp` | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Comp` |
| `Utility` | `…/Scripts/Utility` | same |
| `Tool` / `Render` / `Deliver` / `Edit` / `WorkflowIntegrations` | similar subtrees | similar |
| `root`    | `…/Scripts` (bare) | `…/Scripts` |

Linux fallback: `~/.local/share/DaVinciResolve/Fusion/Scripts/…` (as in Rotoscope).

### 4.4 Workspace config — `resolvescript.json` (npm `package.json` analog)

The consumer side. A committed file next to your code that declares which
extensions this setup wants installed into Resolve. `install` materializes
all of it; `add` edits it; `remove` edits it; `update` re-resolves it.

```json
{
  "name": "my-studio-resolve",             // workspace name (informational)
  "dependencies": {                         // specifier → declared range/ref (package.json parity)
    "rotoscope": "github:OseMine/Rotoscope#v0.4.0",
    "lut_helpers": "https://example.com/lut_helpers-0.2.0.tgz",
    "comp_tools": "^2.1.0",                 // registry/index range (dist-tag later)
    "local-tools": "file:./tools/comp"      // local/workspace link — from this repo
  },
  "install": {
    "targets": ["Comp", "Utility"],
    "allow_remote": true,                   // supply-chain policy for URL/git sources
    "scripts_root": ""                      // overrides OS detection; also RESOLVESCRIPT_SCRIPTS_ROOT
  }
}
```

Resolution rule (npm parity): recorded specifiers are the *declared* target;
the resolved exact artifact lives in `.resolvescript/install.json` and wins
while it still satisfies the recorded range. See §7 M5b.

### 4.5 Framework-extension manifest — `plugin.json` (a plugin, NOT a Resolve script)

A **plugin extends the `resolvescript` CLI itself** and installs into the CLI
config dir, never into Resolve (§0). It ships through the *same* pipeline as a
script (same specifier grammar, tarball shape, SHA-256 integrity, registry) —
only the manifest kind and install target differ.

```json
{
  "kind": "extension",                        // "script" (default) | "extension"
  "name": "resolvescript-lint",
  "version": "1.2.0",
  "description": "Extra static checks for extensions",
  "entry": "plugin.py",                       // loaded by the CLI at startup
  "commands": ["analyze-extra"],              // registers new subcommands
  "sources": ["registry:"],                   // registers new specifier kinds
  "hooks": {                                  // lifecycle hooks in the pipeline
    "pre_build": "hooks.on_pre_build",
    "post_install": "hooks.on_post_install"
  },
  "templates": ["toolkit"],                   // new `create --template` flavors
  "provides": ["mocks:resolve19"],            // extra sandbox mock modules
  "requires": {
    "resolvescript": ">=0.1.0",
    "python": ">=3.9"
  },
  "install": {
    "to": "framework"                         // ⇒ plugin dir, NOT a Resolve target
  }
}
```

Extension points (all optional): `commands`, `sources`, `hooks`, `templates`,
`provides` (mocks). Loading is lazy — `plugins.py` imports `entry` and registers
the contributed dispatch tables at CLI startup (`resolvescript --help` lists
plugin commands). Version gate: `requires.resolvescript`/`python` must be met or
the plugin is skipped with a warning (pytest-plugin model). Core stays lean:
anything optional becomes a plugin, not a core feature (§9).

---

## 5. Command reference (detailed)

### `resolvescript create [--json|--xml] <name>`
- Scaffold a new extension project in `./<name>` (or `--dir`).
- Generates: manifest, package skeleton, empty test, `dev/` sandbox hook,
  `scripts/` dir (if any), README stub, `.gitignore`.
- `--template` picks a scaffold flavor (e.g. `minimal`, `toolkit`).
- Fails if the directory exists and is non-empty.

### `resolvescript dev [--built] [--repl] [--editor]`
- Loads manifest + package, injects mock `DaVinciResolveScript`, drops into the
  sandbox REPL with `session`, `clips`, `resolve`, etc. preloaded.
- `--built` tests the consolidated single file instead of the source package.
- `--editor` prints a recommended Resolve-side script to run in-app.

### `resolvescript test [--built] [-k pattern]`
- Runs pytest inside the extension; injects the mock environment via its
  conftest; `--built` swaps the module under test for the consolidated file.
- `--api-coverage` emits a report of used-vs-mocked Resolve API methods.

### `resolvescript analyze [--json]`
- Syntax-compiles every file, lists unused imports, checks manifest schema,
  validates target names, reports calls to unmocked methods and missing
  `GetAttrs()` keys used by the code.

### `resolvescript build [--output path]`
- Port of Rotoscope `scripts/build.py`: collect package files, dependency
  order, comment-out internal imports, hoist `from __future__ import …`,
  verify with `py_compile`. Writes `dist/<manifest>.<output>`.

### `resolvescript consolidate <package-dir> [--output path]`
- Standalone alias of `build` for arbitrary folders (no manifest needed).
- This is the "glue" users can call from any repo on any package.

### `resolvescript package [--dist dir]`
- Build step, then assemble release artifacts into `dist/`:
  single-file package, `manifest.json`, optional bundled `install.lua` /
  `install.py`, `SHA256SUMS.txt`.
- Emits a **`<name>-<version>.tgz`** in the exact shape `add`/`install <spec>`
  consume (manifest.json + files at a single root layer) — this command is the
  *publisher* side of the install model.
- Prints the exact commands a CI release job can use.

### `resolvescript add <spec> [--target <name>] [--no-save]` (pnpm add / expo install)
- Resolves `<spec>` (specifier grammar, §1) → downloads the artifact → verifies
  SHA-256 → stages → `py_compile`s → installs into the Resolve Scripts root
  per the extension's `targets` → records the specifier into `resolvescript.json`
  (creating the file if absent).
- Idempotent: re-adding an already-installed spec is a no-op or an upgrade
  (npm reinstall / `expo install` behavior).
- `--no-save` installs without touching `resolvescript.json` (cargo-install mode).

### `resolvescript install [<spec>] [--scripts-root <dir>] [--locked] [--dry-run]`
- **No args**: materialize everything recorded in the nearest `resolvescript.json`
  (npm `install` / `component install`). In an **extension project** (manifest
  present), this installs the extension itself — author mode.
- **With `<spec>`**: one-off install of that spec, no recording (cargo install).
- `--scripts-root <dir>` overrides OS-detected root / `RESOLVESCRIPT_SCRIPTS_ROOT`.
- `--locked` fails if already-resolved entries no longer satisfy the recorded
  ranges (frozen-lockfile / `npm ci` semantics).
- `--dry-run` shows the full diff (files to write + manifest edits) and exits
  before writing anything.
- Copies `manifest.json` alongside each install so the registry can track it.

### `resolvescript update [<name>] [--precise <version>] [--fix]` (cargo update / expo install --fix)
- Re-resolves recorded dependencies within their declared ranges and refreshes
  the installed artifacts + registry (nothing to do when specs are already
  satisfied — lockfile wins).
- `--precise <version>` pins one dependency to an exact version.
- `--fix` realigns installed versions to each extension's `compat`
  (min Resolve/Python), the Expo `install --fix` model.

### `resolvescript remove <name>` (npm uninstall)
- Uninstalls the extension's tracked files (from the registry file list) and
  removes its specifier from `resolvescript.json` (or `--no-save` to keep it).

### `resolvescript search <query>`
- Matches the built-in known-extension table + naming conventions
  (`resolvescript-ext-<name>`, `<owner>/<repo>`); later: registry index.

### `resolvescript manage list | remove [--all]`
- Low-level registry operations: `list` reads `.resolvescript/install.json`
  (name/version/source/integrity/files/targets); `manage remove` deletes tracked
  files without touching any config; `--all` also removes the registry.
- Prefer top-level `update` / `remove` for normal use.

### `resolvescript extensions add <spec> | remove <name> | list`
- **Framework-extension (plugin) management only** — installs into the CLI
  config dir `~/.config/resolvescript/plugins/` (or `%APPDATA%\resolvescript\`),
  never into Resolve (§0, §4.5).
- Same pipeline as `add` for scripts: resolve spec → download → SHA-256 verify →
  stage → check `requires.resolvescript`/`python` → write plugin dir → refresh
  plugin registry (`config.toml` + lockfile).
- `force`/`--force` re-installs; `remove` deletes the plugin dir + unregisters;
  `list` shows name/version/kind/commands.
- New commands appear in `resolvescript --help`; plugins whose version gate
  fails are skipped with a warning (never crash the CLI).

### `resolvescript --version`, `resolvescript --help`, `resolvescript <cmd> --help`

---

## 6. Design decisions / open questions

1. **CLI library**: `argparse` (zero deps, matches Rotoscope style) vs `Typer`
   (nicer UX). Default: **argparse** to keep `pip install resolvescript` light;
   revisit if command surface grows beyond ~10 subcommands.
2. **Mock fidelity**: sandbox `api.py` mirrors the methods the Rotoscope
   toolkit calls, NOT the full Resolve API. Extensions calling other methods
   get `NotImplementedError` which `analyze`/`test` surface. Add methods
   on demand per-extension via manifest `sandbox.mocks` initially (future:
   auto-generated mock, see Backlog).
3. **Repo-local install**: `install --scripts-root <dir>` (or a `resolvescript.json`
   with `install.scripts_root`) targets a project-local copy instead of the
   Resolve folder — the drop-in-distribution case (former `--project`).
   Installing into a Resolve *database* project is only possible via the Resolve
   API at runtime, so the CLI ships the Lua/Python "register in project" helper
   as an in-app script, not a CLI operation.
4. **XML reader**: `xml.etree.ElementTree` stdlib only; validate against the
   same model as JSON; no XSD.
5. **Python target**: framework runs on dev machines (≥3.9 to match
   Rotoscope's `py39` ruff target). Generated extensions target the
   Resolve-bundled interpreter (≥3.10, Resolve 18.5+) → keep generated code
   to **stdlib-only** at runtime; manifest `dependencies` are dev/test-only.
   CI compiles all templates/emitted files under `--target-version py310`.
6. **Release/nightly CI for this repo**: reuse the shared
   `OseMine/workflows` actions (`ci`, `release-all`) that Rotoscope already
   uses, with `language: python`. Verify these actions exist and their
   contract matches before wiring `release.yml`.
7. **Extension install is a package manager, not a copy** (npm / pnpm /
   `tauri add` / `expo install`). The CLI is symmetric: **author** side is
   `build` + `package` (publishes the tarball); **consumer** side is
   `add` / `install <spec>` / `update` / `remove` / `search`. Resolve/Python
   compatibility is handled the way Expo does SDK compatibility: `update --fix`.
8. **Two-layer state (npm parity)**: declared specifiers/ranges live in the
   committed `resolvescript.json`; exact pins — `resolved` URL, git commit/ref,
   and `integrity` SHA-256 — live in `.resolvescript/install.json`. Rule:
   the resolved entry wins while it still satisfies the recorded range, else
   the recorded range wins and a re-resolve happens.
9. **No central registry in v1** (Tauri model): a hardcoded known-extension
   table + `<owner>/<repo>` naming conventions + arbitrary URLs cover the
   "registry" case day one. A static JSON index (`registry.resolvescript.dev`)
   with dist-tags and per-version `compat` is the v0.2 upgrade path — still no
   server needed either way.
10. **Archive over git (pnpm)**: public repos are fetched via
    `codeload`/`tar.gz` with pure-`urllib` (stdlib-only, no `git` dependency);
    the `git` CLI is only a fallback (`--depth 1 --branch/--rev`). `#semver:`
    ranges resolve against release tags.
11. **Mandatory integrity**: unlike npm's optional `integrity`, Resolve
    *executes* every installed `.py` on demand, so SHA-256 verification of
    every artifact is non-negotiable; provenance (`resolved` URL + commit/ref)
    is recorded alongside. Supply-chain policy: `install.allow_remote` gates
    URL/git sources (npm 12 `allow-remote` precedent).
12. **Install-time codegen is idempotent** (Tauri pattern): menu entry / Lua
    installer wiring is rendered during `add`/`install`, and skipped when
    already present — never duplicated across re-installs.
13. **Resolve scripts vs framework extensions are one pipeline, two targets**
    (§0, §4.5): a plugin is a script whose `kind`/`install.to` points at the
    CLI config dir. Same resolver, supply chain, integrity and registry —
    `extensions add` reuses `add`'s internals with a different destination,
    version gate and entry-point loader.

---

## 7. Milestones & TODO checkboxes

### M0 — Repo bootstrap
- [ ] Create `src/ResolveScript/` package, `pyproject.toml` (name `resolvescript`, entry point `resolvescript = ResolveScript.cli:main`), README stub, LICENSE
- [ ] `__version__`, `ResolveScript/__init__.py`
- [ ] `cli.py` with argparse parent wiring: `create dev test analyze build package install manage consolidate extensions --version`
- [ ] `.gitignore` (+ `dist/`, `*.egg-info`, `__pycache__`)
- [ ] CI: `ci.yml` using shared `OseMine/workflows` `ci` action (lint `ruff check .`, `pytest`)

### M1 — Manifest model & readers
- [ ] `manifest/model.py`: dataclass `Manifest`, `ConsolidateConfig`, `InstallConfig`, enums for valid `targets`
- [ ] `manifest/json_reader.py`: load + normalize + error reporting (with file/line hints)
- [ ] `manifest/xml_reader.py`: ElementTree → same model
- [ ] `manifest/validation.py`: required fields, target-name whitelist, semver format, output-path sanity, `release`/`compat` presence when `add`/`install <spec>`/`update` used
- [ ] Tests: `test_manifest.py` (JSON round-trip, **kitchen-sink JSON↔XML parity**, malformed inputs)

### M2 — Scaffolder (`create`)
- [ ] `templates/extension/` skeleton (package dir, `__init__.py`, sample module, empty `tests/`, `.gitignore`)
- [ ] Template for `manifest.json` + `manifest.xml`
- [ ] Copy engine with `--json|--xml` and `--dir`/`--name` handling
- [ ] `resolvescript create` end-to-end: scaffold → `ls` → shows next steps; scaffolded project passes `test` and `build` immediately
- [ ] Tests: `test_cli.py::test_create_then_test_and_build`

### M3 — Consolidator (`build`, `consolidate`) ✔
- [x] Port `scripts/build.py` into `consolidate.py` as generic functions:
      `collect_python_files(root, exclude)`, `extract_imports`,
      `strip_internal_imports`, `_statement_open`, dependency-ordered emission,
      `__future__` hoisting, `py_compile` verification
- [x] Import-rewriting edge matrix (test each): `import x`, `from x import y`,
      `import x as z`, relative imports, `__init__` re-exports vs side-effect
      imports, circular deps, `if TYPE_CHECKING` guards, `__all__`-controlled
      exports
- [x] Consolidated output is an **importable library** consumed by the
      manifest `entrypoint`; standalone/`__main__` blocks are an error
- [x] Manifest-driven config: `entry`, `output`, `exclude`, `no_comment`
- [x] `build` writes `dist/<output>` from manifest; `consolidate` works manifest-free
- [x] Test parity with Rotoscope: no un-commented relative imports in output; built module imports; API parity source-vs-built
- [x] Tests: `test_consolidate.py`

### M4 — Sandbox (`dev`, `test` harness) ✔
- [x] Port mock API objects (`api.py`): FakeResolve, FakeProjectManager, FakeProject, FakeTimeline, FakeClip, FakeMediaPool*, FakeComp, FakeTool, FakeSpline, FakeStroke
- [x] `env.py`: `build_default_env()`, `install_fake_resolve()` (sys.modules injection), idempotent re-install
- [x] `smoke.py`: generic `run_smoke(module)` that walks the extension's public API (or manifest-declared exports) so it works for ANY package, not just Rotoscope
- [x] `repl.py`: interactive namespace (clips, resolve, project, timeline, module)
- [x] `dev` command wired (source + `--built`)
- [x] `testing/fixtures.py`: pytest fixtures `sandbox`, `load_source_module`, `load_built_module`
- [x] Scaffolded projects get a working `conftest.py` + smoke test out of the box
- [x] Tests: `test_sandbox.py`

### M5 — Installer core (author + local) ✔
- [x] `install.py` logic ported: per-OS scripts-root discovery into `discovery.py`
      (also reads `RESOLVESCRIPT_SCRIPTS_ROOT` env override); `install_package`
      (dir vs single-file); `install_project`
- [x] Manifest-driven: `targets`, `install.include/exclude` (glob patterns), `entrypoint`, `as_directory`
- [x] Atomic install: stage files to temp dir → `py_compile` staged entry file →
      rename into `Scripts/<target>/` (fail cleanly on any step; never leave
      partial installs; pyc written outside the stage so it never ships)
- [x] Overwrite-conflict detection: warn and abort if two extensions install
      the same relative path to the same target (`--force` overrides)
- [x] Registry: write `.resolvescript/install.json` (include `schema_version`,
      `id`, name, version, **`source`/`resolved` URL, `integrity` SHA-256**,
      `files[]`, `targets[]`, `compat`, `installed_at`) + copy `manifest.json`
- [x] `--scripts-root <dir>` install into any root (repo-local = drop-in dist)
- [x] `manifest.release.{owner,repo,url}` → GH release-asset download path (in M5b `sources`)
- [x] In-app helper script template registering a script into the open Resolve project
- [x] Tests: `test_install.py` on a fake scripts-root (tmp_path)

### M5b — Package sources, resolver & lockfile (consumer side) ✔
- [x] `resolver.py`: specifier grammar + dispatch order (registry-or-known →
      manifest-URL → archive → git → path) + SemVer range parse/match
- [x] `sources/known.py`: hardcoded known-extension table + naming conventions
      (`owner/repo` ⇒ `github:`, `resolvescript-ext-<name>`) — Tauri model
- [x] `sources/git.py`: codeload archive preferred, `git` CLI fallback
      (`--depth 1 --branch/--rev`); `#semver:<range>` resolved over release tags
- [x] `sources/archive.py` + `sources/path.py`: unpack tar.gz/zip (manifest.json
      + files at single root layer); `file:`/`./dir` workspace links
- [x] `fetch.py`: `urllib` download + **mandatory SHA-256 verify**; reject
      mismatches before anything touches the Scripts root; `allow_remote` gate
- [x] `registry.py`: read/write `.resolvescript/install.json`; lockfile-wins
      resolution rule (§6.8); `--locked` support
- [x] `workspace.py`: read/write `resolvescript.json` deps (add/remove specifiers)
- [x] `add <spec>` e2e: resolve → download → verify → stage → py_compile →
      install → record; idempotent; conflict-flagged
- [x] `install` no-args e2e: materialize all recorded deps (npm-install style)
- [x] `update [name] [--precise <version>] [--fix]`: advance within ranges;
      `--fix` realigns to `manifest.compat` (Expo `install --fix`)
- [x] `remove <name>`: uninstall via registry file list + unrecord
- [x] `search <query>`: match known table + conventions
- [x] Install-time codegen (in-app menu script / Lua installer) idempotent
      during `add`/`install` (skip if wiring already present; register.py from M4)
- [x] Tests: `test_runtime.py` (spec/semver/resolver/workspace/CLI e2e from a
      `package`-shaped tarball), `test_cli.py`, `sources.archive` round-trip

### M5c — Framework extensions (plugins) — CLI itself, not Resolve
> Deferrable: can ship in v0.2 after the §0 terminology split is enforced in
> core (script vs extension kinds). Reuses everything from M5/M5b.
- [ ] `manifest/model.py`: `kind` = `"script" | "extension"` + `extension_kind`
      (`commands`/`sources`/`hooks`/`templates`/`provides=mocks`) + `install.to`
      (`resolve` targets vs `framework`) + `requires` gate — §4.5 schema
- [ ] `plugins.py`: plugin config dir discovery (`~/.config/resolvescript/plugins/`
      / `%APPDATA%\resolvescript\plugins\`), lazy `entry` import, contribution
      registration into CLI dispatch at startup
- [ ] Plugin registry + lockfile (same shape as `.resolvescript/install.json`,
      but stored next to the CLI config)
- [ ] `extensions add` (reuses `add` internals with `to: framework`):
      resolve → verify SHA-256 → version-gate check → write plugin dir →
      register; `--force` reinstall
- [ ] `extensions remove <name>` / `extensions list`
- [ ] Failure isolation: unloadable/bad-version plugin is skipped with a warning,
      never crashes the CLI
- [ ] First-party example plugin (e.g. `resolvescript-lint` registering an
      `analyze-extra` command) used as the M8 e2e acceptance artifact
- [ ] Tests: `test_plugins.py` (gate, isolation, contribution registration) +
      e2e add/list/remove of the example plugin

### M6 — Analyzer (`analyze`) ✔
- [x] Syntax compile all files; collect unused imports; manifest validation report
- [x] Detect `GetAttrs()` key reads vs known mock keys; list unmocked API calls
- [x] Target-name validation + recommended fix (`Utility` vs `Tool` etc.)
- [x] `--json` machine-readable output
- [x] `--api-coverage` on `test` command runs the analyzer's API report
- [x] Tests: `test_analyze.py` (analyzer + `test` command e2e)

### M7 — Packager (`package`) + release pipeline ✔
- [x] `package.py`: copy `manifest.json` + entrypoint + package dir into
      `dist/<name>-<version>.tar.gz` (single root layer) + write `SHA256SUMS.txt`
- [x] Archive shape is identical to what `add`/`install <spec>` consume
- [x] Tests: `test_package.py` (artifact set + checksum round-trip)

### M8 — Manager (`manage`) + polish ✔
- [x] `manage list` (name/version/source/integrity/targets/files per installed ext), `manage remove`, `remove --no-save`
- [x] Cross-platform paths coverage: Windows/macOS/Linux discovery unit tests
- [x] Full CLI help text, exit codes (0 ok / 1 error / 2 usage), colored output guard (ASCII-safe prints)
- [x] Shared **kitchen-sink** extension fixture (superseded: the scaffold-based e2e
      flows exercise every manifest option in `tests/test_cli.py` and `test_runtime.py`)
- [x] End-to-end acceptance test — **author** flow:
      `create → dev --built → test → build → package → install (tmp fake root) →
      manage list → remove`
- [x] End-to-end acceptance test — **consumer** flow (M5b):
      package a fixture → host it on a local file/http source → `add <spec>`
      → `manage list` → `update` to a new version → `install --locked` on a
      second workspace (npm-ci path) → `remove`
- [x] `README.md` with quickstart, manifest reference, command + specifier reference
- [x] CHANGELOG

### M9 — Publish & docs ✔
- [x] `python -m build` verified: `resolvescript-0.1.0.tar.gz` + `resolvescript-0.1.0-py3-none-any.whl`
      built cleanly; wheel installs and runs `resolvescript --version` + `create` on a fresh venv.
      CI release workflow (`release.yml`) wired: `push tags: v*` runs the shared
      `release-all` action (`language: python`) which builds the wheel, generates
      checksums and a GitHub release; PyPI publishing requires a `PYPI_ENABLED`
      repo variable and OIDC trusted publishing on pypi.org.
- [ ] Tag `v0.1.0`; push the tag to trigger the release pipeline
- [x] Docs: `README.md` quickstart + manifest reference + specifier reference;
      `CHANGELOG.md` captures the full v0.1.0 feature set

---

## 8. User workflows (acceptance scenarios)

**As a Resolve script author:**
1. `pip install resolvescript`
2. `resolvescript create my_roto_tools && cd my_roto_tools`
3. Write code in `my_roto_tools/`, edit `manifest.json`
4. `resolvescript dev` — iterate against the mock, no Resolve needed
5. `resolvescript test` — green
6. `resolvescript analyze` — clean report
7. `resolvescript build` — got `dist/my_roto_tools.py`
8. `resolvescript install` — installed into Fusion Scripts/Comp; Restart Resolve → Workspace > Scripts
9. `resolvescript manage list` — confirm entry

**As a consumer of someone else's extension (package-manager style):**
1. `resolvescript add github:OseMine/rotoscope`
   — resolves the spec, downloads the artifact, verifies SHA-256, installs
   into Fusion Scripts/Comp, records `"rotoscope": "github:OseMine/rotoscope"`
   in `resolvescript.json`
2. `resolvescript update rotoscope` — fetch a newer release within the range
3. `resolvescript search comp` — find extensions
4. `resolvescript remove rotoscope` — uninstall + unrecord

**Reproducible studio setups (npm-install style):**
1. Commit `resolvescript.json` declaring your studio's extension set
2. On a fresh machine: `resolvescript install` — every recorded dependency is
   fetched, integrity-verified, and installed into the local Resolve;
   `resolvescript manage list` confirms the set
3. CI-safe reinstall: `resolvescript install --locked` reproduces the exact
   recorded artifact versions

**As a ResolveScript framework user (extending the CLI, M5c):**
1. `resolvescript extensions add github:OseMine/resolvescript-lint`
   — installs the plugin into the CLI config dir (never Resolve), version
   gate checked
2. `resolvescript analyze-extra …` — the new command exists
3. `resolvescript extensions list` → confirms the plugin
4. `resolvescript extensions remove resolvescript-lint` — uninstalls

---

## 9. Backlog / future ideas

**Policy:** core stays lean — every optional feature below is a *candidate
framework extension* (M5c plugin), not a core command, unless it grows enough
demand to be promoted.

- [ ] **Rotoscope migration**: migrate `X:\coding\Rotoscope` to consume the CLI
      (replace `scripts/build.py` + `scripts/install.py` + `dev/sandbox.py`
      with `resolvescript build/install/dev test`), keeping Rotoscope package
      code unchanged; Rotoscope becomes the framework's reference Resolve script.
- [ ] Auto-generate mock methods from real `DaVinciResolveScript.py` (parse the bundled module) so `dev`/`test` never `NotImplementedError` — could ship as a plugin (`provides: mocks:*`)
- [ ] Auto-generate mock methods from real `DaVinciResolveScript.py` (parse the bundled module) so `dev`/`test` never `NotImplementedError`
- [ ] `resolvescript publish <ext>` — push a built extension to a release / registry index without manual CI
- [ ] Static registry index (`registry.resolvescript.dev/extensions.json`):
      dist-tags, per-version `compat`, archive URL pattern — upgrades `search`
      and `update` beyond the hardcoded known table
- [ ] `resolvescript validate <dir>` — cheap one-shot manifest + code check for first-time users (candidate plugin)
- [ ] `resolvescript watch` — rebuild + re-install on file change (hot dev loop; candidate plugin)
- [ ] Lua command mirror (`resolvescript lua-script manifest.xml`) bundling a Lua installer into the extension (candidate plugin)
- [ ] Windows context-menu integration (`Add to Resolve Scripts`)
- [ ] TOML manifest support if demand appears (candidate plugin)

---

## 10. Definition of done
- `pip install resolvescript` works from PyPI.
- All 9+ commands function end-to-end on Windows + macOS (primary) and Linux (best effort).
- The automated acceptance tests — **author** and **consumer** flows (§8) — are green in CI.
- Every install is integrity-verified (SHA-256) before the Resolve Scripts folder
  (or the CLI plugin dir) is touched.
- Docs cover every command + the specifier grammar with examples, and the
  **§0 terminology split** (Resolve script vs ResolveScript extension) is
  reflected everywhere.
- Framework-extension support (M5c) is v0.2+; the v0.1 core already
  distinguishes `kind`/install targets so nothing ships that conflates the two.