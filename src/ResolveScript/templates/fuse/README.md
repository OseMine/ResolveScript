# @NAME_LABEL@

A [Fusion fuse](https://docs.fusion.com) for DaVinci Resolve and Fusion: one
Lua file with a `.fuse` extension that Fusion compiles on the fly.

A fuse is the one third-party Fusion plugin format you can author from source.
(`.plugin` is the compiled alternative — see below.)

## Layout

```
@NAME@/
    fuse.py        the Fuse declaration, and the only file you edit
manifest.json     metadata, including the fusion block the CLI reads
tests/
```

The generated artifact is a single `@CLASS_NAME@.fuse` file. It is the
deliverable: Fusion loads it directly, and you can edit it by hand — just
rebuild from the declaration to pick up your changes again.

## Build

```bash
resolvescript fuse build              # dist/@CLASS_NAME@.fuse
resolvescript fuse build --stdout     # print it instead
resolvescript fuse install            # into the Fuses directory
resolvescript fuse list               # what is installed
resolvescript fuse uninstall @CLASS_NAME@
```

Or from Python, without the CLI:

```bash
python -m @NAME@.fuse --print
python -m @NAME@.fuse --check
```

**Restart Fusion or Resolve after installing.** The plugin registry is built
once, at startup, so a newly written `.fuse` file does not appear until then.
This is also why a broken fuse is invisible: there is no dialog and no console
entry, the tool just is not in the menu. `resolvescript fuse build` therefore
checks the file before it can be installed.

## Where it goes

Neither a fuse nor a `.plugin` lives in Resolve's Scripts root. Both come from
Fusion's PathMap, and the location depends on the OS, the application and the
release:

| | Fuses | Plugins |
|---|---|---|
| Windows, Resolve | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Fuses` | …\Fusion\Plugins |
| Windows, Fusion | `%PROGRAMDATA%\Blackmagic Design\Fusion\Fuses` | …\Fusion\Plugins |
| macOS | `~/Library/Application Support/Blackmagic Design/{DaVinci Resolve,Fusion}/Fuses` | …/Plugins |

Override either with `--root`, or with `RESOLVESCRIPT_FUSES_ROOT` /
`RESOLVESCRIPT_FUSION_PLUGINS_ROOT`. `resolvescript fuse root --list` prints
every candidate this tool knows about.

## Anatomy of a fuse

Three top-level obligations. Fusion silently drops a fuse that is missing any
of them.

```lua
FuRegisterClass("Posterize", CT_Tool, {
    REGS_Name = "Posterize",
    REGS_Category = "Fuses\\ResolveScript",   -- backslashes, not dots
    REGS_OpIconString = "Pos",                -- the 3-letter search code
    REGS_OpDescription = "Reduce an image to a fixed number of levels.",
    })

function Create()
    InImage = self:AddInput("Input", "Image", { LINKID_DataType = "Image", LINK_Main = 1 })
    InLevels = self:AddInput("Levels", "Levels", {
        INPID_InputControl = "SliderControl",
        INP_DefaultValue = 6,
        LINKID_DataType = "Number",
        })
    OutImage = self:AddOutput("Output", "Image", { LINKID_DataType = "Image", LINK_Main = 1 })
end

function Process(req)
    local out = InImage:GetValue(req):Copy()
    OutImage:Set(req, out)
end
```

Note the globals: `AddInput` results are assigned without `local`, and that
binding is how `Process` reaches them. `Process` runs once per frame.

## The `process` body is Lua

`process=` is a Python string holding **Lua**, spliced into the file verbatim.
It runs inside Fusion, against Fusion's image API. Pixel work goes through
`DoExpression` with a `[=[ ... ]=]` block, whose contents Fusion compiles as
its own expression language rather than Lua:

```python
process='''
local out = InImage:GetValue(req):Copy()
out:DoExpression([=[
    amount = clamp(amount, 0, 1)
    a = a * amount
]=])
OutImage:Set(req, out)
''',
```

Everything `Create()` binds is a global you can use: `InImage`, `InAmount`,
`OutImage`. A build checks that the body only touches ports the declaration
actually declares, because `InAmunt:GetValue(req)` is a nil index at runtime
and a tool that errors once per frame simply does not work.

## Checks

`resolvescript fuse build` verifies the file it wrote, in two layers:

1. **Structure** — always. Balanced brackets outside strings and comments, the
   three required top-level declarations, and every port the body uses declared.
2. **A real Lua parse** — when `luac` (or `lua`) is on `PATH`. This is the same
   parser Fusion's loader uses, and it reports the offending line.

`resolvescript fuse build` prints which of the two ran, so a green build never
implies more than the machine it ran on could check.

## Shipping it

```bash
resolvescript fuse package          # dist/@CLASS_NAME@-<version>.zip + SHA256SUMS.txt
```

The archive holds the `.fuse` and a `resolvescript.json` describing it. A
compiled plugin can be carried alongside:

```bash
resolvescript fuse package --plugin ../../vendor/Krokodove.plugin
```

## Compiled `.plugin` files

A `.plugin` — `Krokodove.plugin` and its peers — is a native binary or platform
bundle built with Blackmagic's or a vendor's toolchain. There is no source form
that can be turned into one, so ResolveScript only deploys, packages and
removes them; it never claims to have compiled one.

```bash
resolvescript plugin install ../../vendor/Krokodove.plugin
resolvescript plugin list
resolvescript plugin uninstall Krokodove
```

## Tests

```bash
pytest
```

There is nothing to mock — a fuse is Lua, and the closest thing to running it is
compiling it, which is what the tests do.
