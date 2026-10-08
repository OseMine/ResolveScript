# resolvescript-lint

The first-party example of a **ResolveScript framework extension** (plugin):
a package that extends the `resolvescript` CLI itself and installs into the
CLI config directory — never into DaVinci Resolve.

## Try it

```bash
resolvescript extensions add ./examples/resolvescript-lint
analyze-extra            # the new command appears in `resolvescript --help`
resolvescript extensions list
resolvescript extensions remove resolvescript-lint
```

## How it works

- `manifest.json` declares `"kind": "extension"` and
  `"install": { "to": "framework" }` — one pipeline with Resolve scripts,
  two different install targets.
- `entrypoint` names the module the CLI imports at startup.
- The entry module exposes `register_commands(parser)`, which receives the
  top-level subparser action and adds the contributed commands.
- `extension.requires` gates the plugin: if `resolvescript` or `python`
  versions do not match, the plugin is skipped with a warning at CLI
  startup (it never crashes the CLI).

A standalone `plugin.json` (same fields, `entry` instead of `entrypoint`)
is also accepted when installing directly from a directory.
