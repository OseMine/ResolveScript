# @NAME@

@DESCRIPTION@

A **ResolveScript framework extension** (a.k.a. plugin) that extends the
`resolvescript` CLI itself. It installs into the CLI config directory —
**never** into DaVinci Resolve.

Built with [ResolveScript](https://pypi.org/project/resolvescript/).

## Install & Try

```bash
# Install from this directory (dev)
resolvescript extensions add .

# The plugin registers a new command:
analyze-extra          # contributed by this plugin

# List installed plugins
resolvescript extensions list

# Remove
resolvescript extensions remove @NAME@
```

## How It Works

- `manifest.json` declares `"kind": "extension"` and
  `"install": { "to": "framework" }` — same packaging pipeline as Resolve
  scripts, different install target.
- `entrypoint` names the module the CLI imports at startup.
- The entry module exposes `register_commands(parser)`, which receives the
  top-level subparser action and adds the contributed commands.
- `extension.requires` gates the plugin: if `resolvescript` or `python`
  versions don't match, the plugin is skipped with a warning at CLI startup
  (it never crashes the CLI).

## Development

```bash
# Run tests against the mock sandbox
resolvescript test

# Static checks
resolvescript analyze
```

## Publishing

1. Set the `release.owner` and `release.repo` in `manifest.json` to your
   GitHub account.
2. Tag a release: `git tag v1.0.0 && git push --tags`
3. Users can then install with:
   ```bash
   resolvescript extensions add github:@GITHUB_OWNER@/@NAME_KEBAB@
   ```

## Template Options

The scaffold accepts these additional variables via `--include` or by editing
the manifest after creation:

| Variable | Description |
|----------|-------------|
| `GITHUB_OWNER` | Your GitHub username/org (for release URLs) |
| `NAME_KEBAB` | Kebab-case command name (auto-derived from project name) |

Override on create:
```bash
resolvescript create my_plugin --template extension --author "Jane Doe" --description "My plugin"
```