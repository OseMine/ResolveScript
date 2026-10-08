# @NAME@

@DESCRIPTION@

A **DaVinci Resolve script with a structured UI** built with ResolveScript.
The project uses a `src/` layout with separate modules for the entry point
and core UI logic.

Built with [ResolveScript](https://pypi.org/project/resolvescript/).

## Project Structure

```
@NAME@/
├── src/
│   └── @NAME@/
│       ├── __init__.py      # Package metadata
│       ├── main.py          # Entry point (main())
│       └── core.py          # Core UI logic (run_ui, build_ui)
├── tests/
│   ├── conftest.py          # Pytest fixtures
│   └── test_smoke.py        # Basic smoke tests
├── @NAME@_main.py           # In-app entry script (installed to Resolve)
├── manifest.json            # Project manifest
├── pyproject.toml           # Project config
└── README.md                # This file
```

## Development

```bash
# Run tests against the mock sandbox
resolvescript test

# Static analysis
resolvescript analyze

# Build single-file distribution
resolvescript build

# Install into DaVinci Resolve
resolvescript install
```

After `resolvescript install`, restart DaVinci Resolve and run the script from
**Workspace > Scripts > Comp > @NAME@**.

## How It Works

- `src/@NAME@/main.py` - Entry point, calls `core.run_ui()`
- `src/@NAME@/core.py` - Contains `run_ui()` and `build_ui()` for UI logic
- `@NAME@_main.py` - Installed into Resolve's script directory, imports and runs `main()`

The `src/` layout keeps the package separate from project config files and
makes it easy to add more modules as the project grows.

## Publishing

1. Set `release.owner` and `release.repo` in `manifest.json`
2. Tag a release: `git tag v1.0.0 && git push --tags`
3. Users can install with: `resolvescript add github:@GITHUB_OWNER@/@NAME@`