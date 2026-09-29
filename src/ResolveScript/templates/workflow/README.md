# @NAME@

@DESCRIPTION@

A [DaVinci Resolve Workflow Integration](https://www.blackmagicdesign.com/support)
built with [ResolveScript](https://pypi.org/project/resolvescript/).

Resolve lists Workflow Integrations under **Workspace → Workflow
Integrations** — not under Scripts. It finds them by scanning a dedicated
*Workflow Integration Plugins* directory when Resolve starts.

## Try it without Resolve

```
resolvescript test                              # the suite, against the mock API
resolvescript workflow build --out dist         # generate the files Resolve loads
resolvescript workflow install                   # copy them into Resolve's plugins root
```

Restart Resolve afterwards — it reads the directory once, on launch. The entry
now appears under **Workspace → Workflow Integrations**.

You can also run it straight from a terminal:

```
python @NAME@_workflow.py                 # launch it
python @NAME@_workflow.py --describe      # print its metadata as JSON
python @NAME@_workflow.py --no-ui         # on_launch only, no window
```

## What gets installed

| Path | What it is |
| --- | --- |
| `@ID@.py` | The Python launcher. Portable: no npm, no Electron, and it runs on Linux. |
| `@ID@/` | The Electron plugin shell — a window and the `RenderStart`/`RenderStop` callbacks. Windows/macOS Studio only. |

The shell is optional. `resolvescript workflow install-script` installs only the
launcher, and `resolvescript workflow install-plugin` refreshes only the shell
while you work on the window.

## Where the files go

Resolve looks in a different directory than it does for scripts:

- **Windows** — `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins\`
- **macOS** — `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Workflow Integration Plugins/`

Set `RESOLVESCRIPT_WORKFLOWS_ROOT` to override it, or pass `--root` to any
workflow command.

## Development

```
resolvescript dev       # sandboxed REPL against the mock Resolve API
resolvescript test      # run tests against the mock API
resolvescript analyze   # static checks on the project
```

The whole integration is exercised headlessly — the real window on a mock
backend, the real handlers, no Resolve. See `tests/test_smoke.py`; the
`Harness` is in `ResolveScript.workflow`.

## Layout

- `@NAME@/workflow.py` — **the integration**. This is the only file to edit.
- `@NAME@_workflow.py` — a terminal entry point, for debugging.
- `manifest.json` — the same metadata, for tooling that only reads the manifest.
