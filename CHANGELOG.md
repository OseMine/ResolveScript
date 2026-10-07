# Changelog

All notable changes to this project are documented here.

## unreleased

### Planned

- `resolvescript build --installable` — emit a **Lua** file instead of the
  Python one. Dragged into Fusion's Console or the Workspace, it opens an
  installer window drawn by the `ResolveScript.ui` engine and installs the
  script/plugin into the right Resolve location. This is the intended shape;
  it is not implemented yet, and this entry is here so the decision is not
  lost. Open questions when it gets built: how much of the payload a Lua
  console drop can carry, whether the installer UI is authored with the same
  framework as the tools it installs, and how the workflow plugins root is
  reached from Lua (Resolve does not expose it to the Lua scripting API).

### Added

- `ResolveScript.ui` — a declarative, reactive UI framework for DaVinci
  Resolve tools (96 public exports, documented in [`docs/ui.md`](docs/ui.md)).
  - Three interchangeable authoring modes — composition functions, dicts/JSON,
    and class-based `Component`s — all producing the same node tree.
  - Retained rendering: keyed reconciliation patches individual native
    properties instead of rebuilding, so focus, caret position, scroll offset,
    selection and tree expansion survive an update.
  - `Value`/`Computed` reactivity with two-way binding, plus `TwoWay(read=,
    write=)` for stored/native representation differences.
  - Qt-stylesheet theming with light/dark themes, tokens, and subtree cascading.
  - `MockBackend` mirrors the native element tree for headless UI tests, with
    `require` / `fire` / `type_into` / `select_index` / `rows` / `tree` helpers.
  - `FusionBackend` mounts onto a live Resolve; an escape hatch (`native`,
    `raw_element`) reaches any unwrapped native element.
  - `to_dict` / `from_dict` / `to_json` / `from_json` for data-driven screens.
  - `rows()` derives `Tree`/`List` rows from objects — columns are strings
    (called for you if they turn out to be methods, so `"GetName"` reads
    naturally) or callables, with `call()` for methods taking arguments and
    `maybe()` for ones that may legitimately be absent. `children=` recurses
    with the same columns, which makes a media pool browser one call. `None`
    becomes `placeholder` rather than the literal text `None` in a cell.
- Rich library API: `import ResolveScript` now exposes 140+ public names
  across manifest, sources, sandbox, install, config, spec, resolver,
  workspace, semver, scaffold, analyze, consolidate, package, and fetch
  — usable in scripts and REPLs without the CLI.
- Subpackage convenience imports: `ResolveScript.manifest`, `ResolveScript.sandbox`,
  `ResolveScript.sources`, `ResolveScript.install` mirror rotoscope-style
  organization.
- `ResolveScript.get_version()` convenience function.
- New test suite `tests/test_library.py` exercising the top-level surface and a
  full scripted pipeline (scaffold → analyze → consolidate → package).

### Workflow Integrations (in progress)

`ResolveScript.workflow` — declare a DaVinci Resolve Workflow Integration in
Python and let ResolveScript generate the files Resolve actually loads. The
Electron shell, the docs and the dedicated test module are still to come; the
library, the scaffold template and the CLI are working.

- `Integration` / `Context` — the declaration and the live Resolve objects
  Resolve hands a launched script (`resolve`, `project`), with lookups for
  timeline, media pool and render jobs.
- Two artifacts: a portable Python launcher (works on Linux, no npm, no
  Electron) and the Electron plugin shell (Windows/macOS Studio only, the only
  route to Resolve's JavaScript API and its callbacks).
- `manifest.xml`, `package.json`, `main.js`, `preload.js`, `index.html`,
  `js/bridge.js`, `js/app.js`, `css/app.css` — generated from the declaration,
  including copying `WorkflowIntegration.node` out of Resolve's bundled
  samples, since Resolve ships the addon but does not publish it.
- `RenderStart` / `RenderStop` are the only callbacks Resolve delivers, and the
  declaration rejects anything else rather than silently never firing.
- Plugins-root discovery, which is *not* the Scripts root: a separate
  *Workflow Integration Plugins* directory, per-OS, with
  `RESOLVESCRIPT_WORKFLOWS_ROOT` / `--root` overrides.
- A line protocol between the Electron shell and the Python integration, so
  the plugin is a shell and the script is the brain — one import per window
  rather than one per click.
- `Harness` — runs the real window on `MockBackend` against the sandbox fakes,
  so an integration is testable with no Resolve and no display.
- `resolvescript workflow build | install | install-script | install-plugin |
  list | uninstall | root | describe`.
- `resolveScript create --template workflow` scaffolds a working integration;
  the previous template imported names that never existed.

### Changed

- `manifest/__init__` adds `load_manifest(path)` auto-detecting JSON/XML by
  suffix, plus `loads(text, fmt=...)`.
- `sources/__init__` re-exports archive, git, known, and release helpers.
- `sandbox/__init__` re-exports all 14 `Fake*` API classes plus env/loader/repl/smoke.
- `ResolveScript.ui.__init__` re-exports the full state surface
  (`Subscription`, `batched`, `is_reactive`) and `PasswordField`, which were
  previously only reachable from their defining submodules.
- Ruff clean across the whole source tree.

### Fixed

- `Node` now drops a forwarded `key=` from its props even when the node already
  had an explicit key. Previously a helper that built a sub-node with a
  generated key (notably `Tabs`) passed `key=` straight through, and the
  renderer rejected the widget with an "unknown prop" error.
- `App.refresh()` carries auto-generated keys across a component rebuild.
  `Component.build()` mints a fresh key on every call, so a refresh used to see
  every node as new and replace the whole subtree instead of patching it —
  losing focus, selection and scroll position. Explicitly keyed nodes
  (`key=` / `key_id=`) are left untouched.
- `Component.build()` may return another `Component`, matching the documented
  promise that a component is usable anywhere a node is. Refreshing a parent
  now also invalidates a child it holds as an instance attribute.
- The `workflow` scaffold template imported `VGroup`, `HGap`, `Edit`,
  `ComboBox`, `CheckBox` and `run_app`, none of which exist, and its smoke test
  called a `hello()` and a `menu` module that were never defined — the
  scaffolded project could not even be imported. It now uses the real
  `ResolveScript.ui` exports and the real Workflow Integration contract, and
  its ten tests pass against the mock backend.
- `WorkflowConfig` is a typed field on `Manifest` rather than a bare dict, so a
  workflow manifest carries its id, entrypoint and callbacks as real
  attributes. `manifest.is_workflow` joins `is_plugin`.
- Installing a `kind: "workflow"` package into the Scripts root now fails with a
  pointer to `resolvescript workflow install`. Resolve does not load workflow
  integrations from there, so it would have installed a file that silently did
  nothing.

## 0.1.2

### Changed

- Workflows pinned to `OseMine/workflows` `@v2` (stable): per-purpose AI
  providers for the security gate vs release notes, AI notes sanitisation,
  `notes-mode: auto` with `CHANGELOG.md` as AI-failure fallback.
- Release notes now generated via `mistral`/`codestral`; the security gate
  keeps its `opencode` provider + fallback.

## 0.1.1

### Added

- Repo hygiene: issue templates (bug report, feature request, config),
  `FUNDING.yml`, and `dependabot.yml` (weekly `pip` + `github-actions`).
- `security.yml` - thin security gate (Trivy/pip audit + VirusTotal + optional
  AI review) on push, PR, and weekly schedule.

### Changed

- Release pipeline now publishes to PyPI via trusted publishing (OIDC) with
  the shared `pypi-publish` action; AI security gate + release notes wired
  through `release-all` (`provider: opencode`, `auto-free` model).

## 0.1.0 - 2026-09-27

### Added

- `create` - scaffold a Resolve script project from `manifest.json`/`manifest.xml`
  with an optional smoke-test suite (`--template minimal|toolkit`).
- `dev` - sandboxed dev loop, REPL and in-app script printing against a mock
  `DaVinciResolveScript` API (`--built`, `--repl`, `--editor`).
- `test` - run the extension's pytest suite against the mock API (`--built`,
  `-k`, `--api-coverage`).
- `analyze` - static checks for manifest/syntax/unused-import/unmocked-API issues
  with JSON output.
- `build` - consolidate a multi-file package into a single distributable `.py`.
- `package` - assemble `dist/<name>-<version>.tar.gz` release artifacts with
  `SHA256SUMS.txt`.
- `add` / `install` / `update` / `remove` - npm-style dependency management:
  specifier resolution (name, `owner/repo`, `github:`, archive URLs, `file:` and
  local paths), semver ranges, lockfile-style verification (`install --locked`),
  and workspace recording in `resolvescript.json`.
- `search` - discover Resolve scripts from the known-sources table.
- `manage list|remove` - low-level registry operations against the install
  registry.
- Install model: target-aware layout under the Resolve Scripts root, integrity
  tracking, and a versioned JSON registry (`<ScriptsRoot>/.resolvescript/install.json`).
- Cross-platform Scripts-root discovery (Windows/macOS/Linux) with overrides via
  `--scripts-root` and `RESOLVESCRIPT_SCRIPTS_ROOT`.
- CI (`ci.yml`) and release (`release.yml`) workflows on GitHub Actions.
- 165 automated tests; ruff-clean.

### Fixed

- `create` crashed with `UnicodeDecodeError` when the installed templates
  directory contained stale `__pycache__/*.pyc` files from a prior run.

### Notes

- `extensions add|remove|list` are still on the M0 skeleton; not yet implemented.