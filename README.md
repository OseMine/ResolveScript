# ResolveScript

A Python CLI framework for **building, coding, testing, packaging and installing
DaVinci Resolve scripts**, distributed as `pip install resolvescript`.

```
pip install resolvescript

resolvescript create my_extension        # scaffold a new Resolve script project
resolvescript dev                        # sandboxed REPL against the mock Resolve API
resolvescript test                       # run tests against the mock Resolve API
resolvescript analyze                    # static checks on the project
resolvescript build                      # consolidate multi-file package → single .py
resolvescript package                    # produce release artifacts (single-file + assets)

resolvescript add <spec>                 # install + record a Resolve script (pnpm-add style)
resolvescript install                    # materialize everything recorded in resolvescript.json
resolvescript update [<name>]            # re-resolve within recorded ranges; --fix realigns compat
resolvescript remove <name>              # uninstall + unrecord
resolvescript search <query>             # discover Resolve scripts

resolvescript manage list                # list installed extensions
resolvescript extensions add <spec>      # install a framework extension (plugin, not Resolve)
```

---

Status: **M0 skeleton** — CLI dispatch wired, milestone work in progress. See
[`TODO.md`](TODO.md) for the full plan.