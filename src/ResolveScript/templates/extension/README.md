# @NAME@

@DESCRIPTION@

Built with [ResolveScript](https://pypi.org/project/resolvescript/).

## Development

```
resolvescript dev       # sandboxed REPL against the mock Resolve API
resolvescript test      # run tests against the mock API
resolvescript analyze   # static checks on the project
resolvescript build     # consolidate the package into dist/@NAME@.py
resolvescript install   # install into DaVinci Resolve (author mode)
```

## Usage in Resolve

After `resolvescript install`, restart DaVinci Resolve and run the script from
**Workspace → Scripts → Comp → @NAME@**.