# Changelog

All notable changes to this project are documented here.

## Unreleased

## 1.1.0 - 2026-10-08

### Added

- `resolvescript doctor [--scripts-root DIR] [--json]` — self-diagnosis of
  the interpreter, template package-data, Scripts root discovery, env
  overrides, project manifest, `resolvescript.json` and the install registry.
  Every check reports `ok`/`warn`/`fail` and the command exits 1 on failure;
  the library form is `ResolveScript.doctor.run_checks()`.
- Unified error taxonomy: every domain error now derives from the new
  `ResolveScriptError` base (`rs.ResolveScriptError`), so one `except`
  catches all library failures. Historical bases are preserved (`SpecError`
  is still a `ValueError`, `FetchError` still a `RuntimeError`, …) and a
  contract test enforces the base for every exported error type.
- Library logging under the `ResolveScript.*` logger hierarchy: resolver
  dispatch, downloads, cache hits, install steps and workspace writes are
  visible on the CLI via `-v` (info) or `-vv` (debug).
- `py.typed` marker (verified present in the built wheel) and a
  `[tool.mypy]` configuration; the package type-checks clean across 71
  source files and the release pipeline gained a `Type check` step.
- `resolvescript extensions add <spec> | remove <name> | list [--json]` —
  framework-extension (plugin) management (M5c). Plugins install into the
  CLI config directory (never into Resolve) through the same specifier
  grammar, integrity and packaging pipeline as Resolve scripts, gated at
  install time by `extension.requires`. Plugin commands register at CLI
  startup via the entry module's `register_commands(parser)`; plugins that
  fail their version gate, cannot be imported or lack the hook are skipped
  with a warning — a broken plugin never crashes the CLI.
- `RESOLVESCRIPT_CONFIG_DIR` overrides the CLI config directory
  (`%APPDATA%\ResolveScript` / `~/.config/ResolveScript`) used by the
  plugin registry.
- `examples/resolvescript-lint` — the first-party example plugin adding an
  `analyze-extra` command, used as the M5c end-to-end acceptance artifact.
- `manifest.xml` now reads the `<extension>` block (`extension_kind`,
  `commands`, `provides`, `sources`, `templates`, `hooks`, `requires`),
  bringing plugin manifests to JSON/XML parity.
- `resolvescript clean [--dir DIR] [-v]` — removes project caches (`.resolvescript/cache`),
  build artifacts (`dist/`), registry files (`install.json`, `.resolvescript-fuses.json`),
  and `__pycache__` directories.
- `resolvescript upgrade` — alias for `update`, re-resolves recorded dependencies.
- `resolvescript create --template extension` — scaffolds a framework extension
  (CLI plugin) with `manifest.json` (kind=extension, install.to=framework),
  `register_commands(parser)` entry module, and plugin-ready `pyproject.toml`.

### Fixed

- README claimed "Python 3.12+" although the package requires 3.9+ and the
  CI matrix tests 3.9-3.12.
- `docs/cli.md` documented `extensions install/uninstall/enable/disable/info`
  subcommands that never existed; it now matches the real
  `add/remove/list` surface.
- The package docstring's consolidate example referenced a non-existent
  `resolve-script.manifest.json` and a wrong `config_from_manifest`
  signature.
- Latent type errors found while wiring mypy: `Fuse.variables` unpacked
  `Control`/`Output` into a join of `object`, semver range parsing reused
  `lo`/`hi` as both strings and versions, `analyze` reported a line number
  from a variable whose scope didn't guarantee it, `ReleaseSpec.from_data`
  could store `url=None` in a `str` field, and `FakeUIWidget._parent` was
  only ever set by `AddChild`.

## 1.0.2 - 2026-10-08

### Added

- `release.yml` generates **AI release notes** before publishing:
  `OseMine/workflows`' `opencode` action runs OpenCode first and falls back
  to Mistral, producing six fixed sections (Features, Fixes, Breaking,
  Other, Technical, docs) from the commit range since the previous tag.
  When AI is unavailable the body falls back to this version's CHANGELOG
  section, then `git log`, then GitHub's own generated notes — a missing
  model never blocks a release.
- `workflow_dispatch` on the release workflow gained a `dry-run` input
  (full pipeline, no publish), and its `version` input now actually selects
  the release tag instead of letting the run target the branch name.

### Fixed

- PyPI publishing is re-enabled: the `PYPI_PUBLISH` repository variable is
  set and the publish job no longer declares an `environment` (an OIDC
  subject mismatch introduced on 2026-09-29 would have failed the trusted
  publishing exchange). Verified against `pypi.org/_/oidc/mint-token`
  before this release.
- The release workflow uploads build artifacts from a single matrix leg:
  merging four same-named dist files from all legs raced during download
  and corrupted the sdist, failing the first PyPI upload attempt with
  `tarfile.ReadError: bad checksum`.

## 1.0.1 - 2026-10-08

### Added

- `tests/test_installer_lua.py` — 13 cases covering `build --installable`:
  the generated Lua installer, token substitution (`_fill` raising on a
  leftover `@@TOKEN@@`), and the rendered install window.
- README section on **Fusion fuses and plugins** documenting all four
  project kinds (`script`, `workflow`, `fuse`, `plugin`) and where
  `resolvescript create --template fuse` fits in.

### Changed

- The 1.0.0 changelog entry was expanded with the full fuse/plugin feature
  list, and `docs/fuse.md` / `docs/plugin.md` now cover the build,
  package and install flows end to end.

## 1.0.0 - 2026-10-07

One release covering the whole toolchain: scripts, workflow integrations,
Fusion `.fuse` plugins, precompiled `.plugin` binaries, and the CI that ships
them. Tested on Python 3.9–3.12 on both Windows and Linux.

### Added

- **`.fuse` and `.plugin` support** across create/build/export/package/
  consolidate ([`docs/fuse.md`](docs/fuse.md), [`docs/plugin.md`](docs/plugin.md)):
  - `resolvescript create <name> --template fuse` scaffolds a project;
    `resolvescript fuse build | package | install | list | uninstall | root |
    describe` takes it from there.
  - `.plugin` binaries are deployed, never built: `resolvescript plugin
    install | describe | list | uninstall | root`. There is no source to
    compile, so nothing in the pipeline pretends to make one.
  - Two-layer validation: structure (`FuRegisterClass` / `Create()` /
    `Process(req)`, the `InImage` / `OutImage` globals) and then a full
    `luac -p` parse when Lua is installed — a broken fuse fails here rather
    than inside Resolve. Generated output is ASCII-only.
  - Per-OS roots with `RESOLVESCRIPT_FUSES_ROOT` and
    `RESOLVESCRIPT_FUSION_PLUGINS_ROOT` overrides, both exported from
    `ResolveScript.config`, plus `--root`.
- `resolvescript build --installable` — emits one **Lua** file instead of a
  `.py`. Dragged into Fusion's Console or Workspace it opens an install window
  (Fusion's own UIManager, `bmd.UIDispatcher`) with install/cancel and an
  overwrite toggle, decodes the base64 payload, and writes the consolidated
  script through `fusion:MapPath("Scripts:…")` so the target is Resolve's own
  answer rather than a hard-coded path. A project's `installer.lua.j2`
  (or `--installer-template`) redraws the window; a template that leaves an
  `@@TOKEN@@` behind fails the build instead of shipping.
- Composite actions in `.github/actions/` for setup, test, analyze, build,
  build-installable, package, consolidate, install, update, manage,
  extensions, fuse, plugin, workflow, ci, release and security-scan, plus
  Dependabot covering both `pip` and `github_actions`.
- Guides: `docs/fuse.md`, `docs/plugin.md`, `docs/workflow.md`,
  `docs/ui.md`, `docs/github-actions.md`, `docs/installer.md`, and the rest
  of the `docs/` set.
- `tests/test_fuse.py` (137 cases) and `tests/test_installer_lua.py` (13) —
  the Lua installer had no coverage at all before this.

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

### Workflow Integrations

`ResolveScript.workflow` — declare a DaVinci Resolve Workflow Integration in
Python and let ResolveScript generate the files Resolve actually loads. The
library, the scaffold template, the CLI and [`docs/workflow.md`](docs/workflow.md)
work; the dedicated test module is still to come.

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
- Release pipeline rebuilt as a standard Python build: `release.yml` lints,
  tests and runs `python -m build` on Python 3.9–3.12 for every `v*` tag,
  creates the GitHub Release, and hands PyPI to OIDC trusted publishing once
  the `PYPI_PUBLISH` repository variable is set — green either way.
- The composite actions in `.github/actions/` are for consuming projects:
  GitHub cannot resolve a local action from this repo's own workflows, so
  these workflows inline the same commands.

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
- Four example workflows (`dependencies`, `fuse`, `security`, `workflow`)
  ended every run after 0 seconds with "workflow file issue": each declared
  `runs-on` twice and gated its job with `hashFiles(...)`, which is legal only
  in a step-level `if:`. The check now lives in a `manifest` job those jobs
  depend on, so they still skip in a repo without a manifest instead of
  failing to parse at all.
- `release-enhanced.yml` duplicated `release.yml` — same name, same `v*` tag
  trigger, but installing the *published* package rather than the code being
  released — and carried the same invalid gate. Removed; `release.yml` is the
  single tag-triggered pipeline.
- `ui.rows.Accessor` evaluated `str | Callable[...]` at import time, which
  Python 3.9 rejects: `from __future__ import annotations` defers annotations,
  not values. It is a `Union` now.
- `fuse build` and the Lua installer called `Path.write_text(newline=...)`,
  added in 3.10. Both open the file directly and keep the LF endings Fusion
  expects.
- The Windows-path tests read the live environment and Windows separators, so
  they failed on Linux runners. They set `PROGRAMDATA`/`APPDATA`/`PUBLIC`
  themselves and build the expected path part by part.
- `pyproject.toml` still said `0.1.0` while `_version.py` said `1.0.0`, and
  its extras required pytest 9, which needs Python 3.10 — the 3.9 matrix leg
  could not install the test suite at all. The versions agree and the floor is
  honest; the `fuse`/`plugin`/`workflow` subcommands were also only in the
  working tree, so CI parsed an older `cli.py` and rejected `fuse` as an
  invalid choice.

### Planned

- Reaching the Workflow Integration plugins root from a Lua installer drop —
  Resolve does not expose that directory to the Lua scripting API, so
  `build --installable` targets the Scripts root only.

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