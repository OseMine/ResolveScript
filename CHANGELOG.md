# Changelog

All notable changes to this project are documented here.

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

## 0.1.0 - unreleased

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