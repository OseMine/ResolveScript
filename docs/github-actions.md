# GitHub Actions for ResolveScript Projects

ResolveScript provides **composite GitHub Actions** you can reuse in your project's workflows.

## Quick Setup

Copy the workflow files you need to your project's `.github/workflows/`:

```bash
# In your project repo
cp -r /path/to/ResolveScript/.github/workflows/ci.yml .github/workflows/
cp -r /path/to/ResolveScript/.github/workflows/fuse.yml .github/workflows/
```

Or reference them directly from the ResolveScript repo:

```yaml
uses: resolvescript/resolvescript/.github/actions/build@main
```

## Available Actions

| Action | Path | Description |
|--------|------|-------------|
| `setup-resolvescript` | `.github/actions/setup-resolvescript` | Install ResolveScript + deps |
| `build` | `.github/actions/build` | Consolidate package |
| `test` | `.github/actions/test` | Run pytest against mock API |
| `analyze` | `.github/actions/analyze` | Static checks |
| `package` | `.github/actions/package` | Create release zip + SHA256 |
| `consolidate` | `.github/actions/consolidate` | Ad-hoc directory merge |
| `install` | `.github/actions/install` | Install into Scripts dir |
| `update` | `.github/actions/update` | Re-resolve dependencies |
| `manage` | `.github/actions/manage` | Registry operations |
| `extensions` | `.github/actions/extensions` | Framework extensions |
| `fuse` | `.github/actions/fuse` | Build/install/package `.fuse` |
| `plugin` | `.github/actions/plugin` | Deploy `.plugin` bundles |
| `workflow` | `.github/actions/workflow` | Build/install Workflow Integrations |
| `ci` | `.github/actions/ci` | **Composite pipeline** (all of above) |

## Using the Composite `ci` Action

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  ci:
    name: ResolveScript CI (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4

      - name: Run ResolveScript CI
        uses: resolvescript/resolvescript/.github/actions/ci@main
        with:
          project-dir: "."
          python-version: ${{ matrix.python-version }}
          resolvescript-version: "latest"
          run-build: true
          run-test: true
          run-analyze: true
          run-package: false
          test-args: "-q --tb=short"
```

### `ci` Action Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `project-dir` | No | `.` | Project directory |
| `python-version` | No | `3.9` | Python version |
| `resolvescript-version` | No | `latest` | ResolveScript version (`latest`, `dev`, or `x.y.z`) |
| `run-build` | No | `true` | Run build step |
| `run-test` | No | `true` | Run test step |
| `run-analyze` | No | `true` | Run analyze step |
| `run-package` | No | `false` | Run package step |
| `test-args` | No | `-q` | Pytest arguments |
| `installable` | No | `false` | Generate Lua installer |

## Using Individual Actions

### Build Only

```yaml
- uses: resolvescript/resolvescript/.github/actions/build@main
  with:
    project-dir: "."
    installable: false
```

### Test with Coverage

```yaml
- uses: resolvescript/resolvescript/.github/actions/test@main
  with:
    project-dir: "."
    test-args: "-q --tb=short"
    coverage: "true"

- uses: actions/upload-artifact@v4
  with:
    name: coverage
    path: coverage.xml
```

### Fuse-Specific CI

```yaml
# .github/workflows/fuse.yml
name: Fuse CI

on: [push, pull_request]

jobs:
  fuse:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - uses: resolvescript/resolvescript/.github/actions/setup-resolvescript@main
        with:
          python-version: ${{ matrix.python-version }}

      - uses: resolvescript/resolvescript/.github/actions/fuse@main
        with:
          subcommand: "build"
          project-dir: "."
          no-check: false

      - uses: resolvescript/resolvescript/.github/actions/fuse@main
        with:
          subcommand: "package"
          project-dir: "."
          dist: "dist"

      - uses: actions/upload-artifact@v4
        with:
          name: fuse-${{ matrix.python-version }}
          path: dist/*
```

### Workflow Integration CI

```yaml
# .github/workflows/workflow.yml
name: Workflow Integration CI

on: [push, pull_request]

jobs:
  workflow:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - uses: resolvescript/resolvescript/.github/actions/setup-resolvescript@main
        with:
          python-version: ${{ matrix.python-version }}

      - uses: resolvescript/resolvescript/.github/actions/workflow@main
        with:
          subcommand: "build"
          project-dir: "."
          script-only: true

      - uses: resolvescript/resolvescript/.github/actions/test@main
        with:
          project-dir: "."
```

### Release Workflow

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags: ["v*"]
  workflow_dispatch:
    inputs:
      version:
        required: true

permissions:
  contents: write
  packages: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: resolvescript/resolvescript/.github/actions/setup-resolvescript@main

      - uses: resolvescript/resolvescript/.github/actions/analyze@main

      - uses: resolvescript/resolvescript/.github/actions/build@main

      - uses: resolvescript/resolvescript/.github/actions/test@main
        with:
          test-args: "-q --tb=short"

      - uses: resolvescript/resolvescript/.github/actions/package@main

      - uses: softprops/action-gh-release@v1
        with:
          files: dist/*
          generate_release_notes: true
```

## Action Reference

### `setup-resolvescript`

```yaml
uses: resolvescript/resolvescript/.github/actions/setup-resolvescript@main
with:
  python-version: "3.9"
  resolvescript-version: "latest"  # or "dev", "1.2.3"
  cache-key-suffix: "v1"
```

### `build`

```yaml
uses: resolvescript/resolvescript/.github/actions/build@main
with:
  project-dir: "."
  output: "dist/my_script.py"
  installable: "false"
  installer-template: "custom_installer.lua.j2"
```

### `test`

```yaml
uses: resolvescript/resolvescript/.github/actions/test@main
with:
  project-dir: "."
  test-args: "-q --tb=short"
  coverage: "false"
```

### `analyze`

```yaml
uses: resolvescript/resolvescript/.github/actions/analyze@main
with:
  project-dir: "."
  json-output: "false"
```

### `package`

```yaml
uses: resolvescript/resolvescript/.github/actions/package@main
with:
  project-dir: "."
  dist-dir: "dist"
```

### `fuse`

```yaml
uses: resolvescript/resolvescript/.github/actions/fuse@main
with:
  subcommand: "build"        # build, install, package, list, uninstall, root, describe
  project-dir: "."
  entrypoint: "my_fuse.fuse:FUSE"
  root: "/custom/fuses"
  dist: "dist"
  plugin: "vendor/Krokodove.plugin"
  dry-run: "false"
  no-check: "false"
```

### `plugin`

```yaml
uses: resolvescript/resolvescript/.github/actions/plugin@main
with:
  subcommand: "install"      # install, describe, list, uninstall, root
  path: "./Krokodove.plugin"
  root: "/custom/plugins"
  name: "Krokodove"
  dry-run: "false"
  no-force: "false"
```

### `workflow`

```yaml
uses: resolvescript/resolvescript/.github/actions/workflow@main
with:
  subcommand: "build"        # build, install, install-script, install-plugin, list, uninstall, root, describe
  project-dir: "."
  entrypoint: "my_wf.workflow:INTEGRATION"
  root: "/custom/workflows"
  dist: "dist"
  script-only: "false"
  dry-run: "false"
```

## Dependabot

Add `.github/dependabot.yml` to your project:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
    labels: ["dependencies", "python"]
    groups:
      dev-dependencies:
        patterns: ["pytest*", "ruff*", "mypy*"]
      resolve-deps:
        patterns: ["pydavinci*", "ResolveScript*"]

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    labels: ["dependencies", "github-actions"]
```

## Self-Hosted Runners (Windows/macOS)

For install tests that need real Resolve/Fusion:

```yaml
jobs:
  fuse-install-test:
    runs-on: windows-latest  # or macos-latest
    needs: fuse
    steps:
      - uses: actions/checkout@v4
      - uses: resolvescript/resolvescript/.github/actions/setup-resolvescript@main
      - uses: resolvescript/resolvescript/.github/actions/fuse@main
        with:
          subcommand: "install"
          project-dir: "."
          dry-run: true  # Safe test
```

## Caching

All actions use `actions/setup-python@v5` with `cache: 'pip'` keyed on:
- `requirements*.txt`
- `pyproject.toml`
- `setup.py`
- `setup.cfg`

Invalidate with `cache-key-suffix` input.

## Version Pinning

Pin to specific SHA for supply chain security:

```yaml
uses: resolvescript/resolvescript/.github/actions/build@abc123def456
```

Or use tags:

```yaml
uses: resolvescript/resolvescript/.github/actions/build@v1.2.3
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `resolve` not found in tests | Ensure `resolvescript test` runs in project dir with manifest |
| Electron build fails | Install system deps: `libnss3 libatk1.0-0 ...` (see workflow.yml) |
| Install needs real Resolve | Use `dry-run: true` or self-hosted runner with Resolve installed |
| Cache not working | Check `pyproject.toml` exists, try `cache-key-suffix: v2` |