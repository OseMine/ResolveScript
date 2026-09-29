# Fusion Fuse Development with ResolveScript

ResolveScript provides first-class support for creating **`.fuse` plugins** — scripted Fusion tools written in Lua that Fusion compiles on-the-fly. A fuse is a single `.fuse` file containing three required top-level declarations:

1. `FuRegisterClass` — registers the tool with Fusion's registry
2. `Create()` — defines inputs/outputs and binds them to globals
3. `Process(req)` — runs every frame the tool is active

## Quick Start

```bash
# Scaffold a fuse project
resolvescript create my_fuse --template fuse

# Enter the project
cd my_fuse

# Check the declaration loads
resolvescript fuse describe

# Build the .fuse file (validated with luac)
resolvescript fuse build

# Install into Fusion's Fuses directory
resolvescript fuse install

# Package for distribution (zip + SHA256)
resolvescript fuse package
```

## Project Structure

```
my_fuse/
├── manifest.json          # Project metadata (kind: "fuse")
├── my_fuse/
│   ├── __init__.py
│   ├── fuse.py            # FUSE declaration (the source of truth)
│   └── __main__.py        # CLI entry: build --stdout, --check, -o
├── tests/
│   └── test_smoke.py      # Basic validation tests
└── README.md
```

## The Fuse Declaration

The `fuse.py` file contains a single `FUSE = Fuse(...)` declaration:

```python
from ResolveScript.fuse import Control, Fuse

FUSE = Fuse(
    name="Posterize",           # Menu name (REGS_Name)
    version="1.0.0",
    category="Fuses\\MyTools",  # Registry path (REGS_Category)
    icon_string="Pst",          # 3-letter search code
    description="Posterize effect with adjustable levels",
    tool_type="CT_Tool",        # CT_Tool, CT_SourceTool, or CT_Operator
    # Controls (appear in inspector)
    inputs=[
        Control("Levels", kind="SliderControl", minimum=2, maximum=64, default=8),
        Control("Mode", kind="ComboBoxControl", items=["Luminance", "RGB", "Alpha"]),
    ],
    # Optional extra outputs
    outputs=[
        # Output("Matte", datatype="Image")  # Adds OutMatte
    ],
    # Process body (statements only, not the function line)
    process="""
        local out = InImage:GetValue(req):Copy()
        local levels = InLevels:GetValue(req).Value
        out:DoExpression([=[
            local v = pixel
            v = math.floor(v * levels + 0.5) / levels
            pixel = v
        ]=])
        OutImage:Set(req, out)
    """,
)
```

## Control Types

| Kind | Data Type | Key Properties |
|------|-----------|----------------|
| `SliderControl` | Number | `minimum`, `maximum`, `step`, `default` |
| `NumberControl` | Number | `default` |
| `TextControl` / `TextEditControl` | Text | `default`, `lines` (multiline) |
| `CheckboxControl` | Boolean | `default` |
| `ComboBoxControl` | Choice | `items` (list), `default` |
| `ColorControl` | Color | `default` (r,g,b) |
| `PointControl` | Point | `default` (x,y) |
| `AngleControl` | Angle | `default` (degrees) |
| `PathControl` | Path | `default` |
| `RegionControl` | Region | `default` |
| `InputButtonControl` | — | — |
| `LabelControl` | — | — |
| `DropdownControl` | Choice | `items` |

**Data ports** (image, number, etc.) are created by omitting `kind` and setting `datatype`:

```python
Control("Mask", datatype="Image", main=1)  # Image input port
Control("Intensity", datatype="Number", default=1.0)  # Number port
```

## Built-in Defaults

| Tool Type | Auto-added |
|-----------|------------|
| `CT_Tool` | Image input (`InImage`) + Image output (`OutImage`) |
| `CT_SourceTool` | Image output only (`OutImage`) |
| `CT_Operator` | Image input + Image output |

The variable names follow Fusion convention: `In` + PascalCase(id) for inputs, `Out` + PascalCase(id) for outputs.

## Validation

ResolveScript validates fuses in two layers:

| Layer | What it checks |
|-------|----------------|
| **Structural** (always) | Required declarations present, balanced brackets, no unsubstituted tokens, `Process` references only declared ports/locals |
| **Lua parse** (if `luac` on PATH) | Real `luac -p` compilation — same parser Fusion uses |

```bash
# Explicit validation
resolvescript fuse build --no-check   # Skip validation (for debugging)
resolvescript fuse build --stdout     # Print .fuse source to stdout
```

The CLI reports which layer ran:
```
checked: structure + luac parse
# or
checked: structure only (no Lua interpreter on PATH)
```

## Installation & Discovery

Fusion scans **Fuses** directories at startup. ResolveScript knows the standard locations:

| Platform | Fuses Directory |
|----------|-----------------|
| Windows (Resolve) | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Fuses` |
| Windows (Fusion) | `%PROGRAMDATA%\Blackmagic Design\Fusion\Fuses` |
| macOS (Resolve) | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Fuses` |
| macOS (Fusion) | `~/Library/Application Support/Blackmagic Design/Fusion/Fuses` |
| Linux (Resolve) | `~/.local/share/DaVinciResolve/Fusion/Fuses` |

Override with environment variable:
```bash
export RESOLVESCRIPT_FUSES_ROOT=/custom/fuses/path
```

## Registry & Management

ResolveScript tracks installed fuses in `.resolvescript-fuses.json` (per directory):

```bash
# List installed
resolvescript fuse list

# List with all known candidate directories
resolvescript fuse root --list

# Uninstall by class name or filename
resolvescript fuse uninstall Posterize
resolvescript fuse uninstall Posterize.fuse
```

## Packaging

```bash
resolvescript fuse package
# Creates: dist/Posterize-1.0.0.zip + SHA256SUMS.txt
# Archive contains: Posterize.fuse, resolvescript.json
```

Include a compiled plugin alongside:
```bash
resolvescript fuse package --plugin ./vendor/Krokodove.plugin
```

## Custom Templates

The scaffolded `fuse.py` is your source of truth. To customize the generated `.fuse`, edit the declaration. For advanced needs, you can provide a custom renderer (see `ResolveScript.fuse.render`).

## Tips

- **Use leveled long brackets** `[=[ ... ]=]` for `DoExpression` bodies — they nest safely
- **Globals, not locals**: `Create()` assigns to globals (`InImage = ...`), which `Process` reads
- **Three-letter icon**: `icon_string` enables registry search (e.g., type "Pst" to find Posterize)
- **Category uses backslashes**: `Fuses\\Vendor\\Category` not dots
- **Source tools** (`CT_SourceTool`) have no image input — they replace the chain