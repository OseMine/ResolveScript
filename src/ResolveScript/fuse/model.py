"""Declaring a Fusion fuse.

A *fuse* is Fusion's scripted plugin: one Lua file with a ``.fuse`` extension
that Fusion compiles on the fly, so there is nothing to compile here. It is the
one third-party plugin format Resolve and Fusion actually load from source.

The file has exactly three obligations, and Fusion rejects it if any is missing:

``FuRegisterClass(InternalName, CT_Tool, { ... })``
    The tool's identity: menu name, category, icon, description. Read when the
    registry is built, which is why it has to be at the top level and cannot
    depend on anything defined below it.

``function Create()``
    Declares inputs and outputs. Every ``AddInput``/``AddOutput`` result is
    assigned to a **global** (``InImage``, not ``local InImage``) — that binding
    is how ``Process`` reaches them.

``function Process(req)``
    Pulls values in with ``GetValue(req)`` and pushes results out with
    ``Set(req, ...)``. Called once per frame while the tool is in use.

This module is the part you write; :mod:`ResolveScript.fuse.render` turns it
into the file, and :mod:`ResolveScript.fuse.build` writes and installs it::

    from ResolveScript.fuse import Control, Fuse

    FUSE = Fuse(
        name="Posterize",
        description="Reduce an image to a fixed number of levels.",
        controls=[Control("Levels", min=2, max=64, default="6")],
        process='''
    levels = Levels:GetValue(req).Value
    local img = InImage:GetValue(req)
    local out = img:Copy()
    out:DoExpression([=[
        level = max(1, int(level))
        r, g, b, a = map(r, g, b, function(c)
            return min(255, int(c * 255 / level + 0.5) * level / 255)
        end)
    ]=])
    OutImage:Set(req, out)
    ''',
    )

The ``process`` body is Lua, not Python: it runs inside Fusion, against Fusion's
image API, on every frame. :attr:`Fuse.inputs` and :attr:`Fuse.outputs` name the
variables that body can see.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import ResolveScriptError

__all__ = [
    "DEFAULT_CATEGORY",
    "TOOL_TYPES",
    "BINARY_SUFFIXES",
    "BinaryPlugin",
    "Control",
    "Fuse",
    "FuseError",
    "Output",
]

#: Where a fuse shows up in the registry menu when no category is given. Fuses
#: sort under their category path, and the top level is for Blackmagic's own.
DEFAULT_CATEGORY = "Fuses\\ResolveScript"

#: The tool classes Fusion accepts in ``FuRegisterClass``. ``CT_Tool`` is a
#: filter placed after the selected node; ``CT_SourceTool`` replaces the chain
#: and therefore has no image input; ``CT_Operator`` acts on a selected tool.
TOOL_TYPES: tuple[str, ...] = ("CT_Tool", "CT_SourceTool", "CT_Operator")

#: ``INPID_InputControl`` -> the ``LINKID_DataType`` Fusion pairs it with. A
#: control with no entry here (or an empty ``kind``) is a plain data port, which
#: is how an image gets in and out.
_CONTROL_DATATYPES: dict[str, str] = {
    "LabelControl": "Text",
    "TextControl": "Text",
    "TextEditControl": "Text",
    "NumberControl": "Number",
    "SliderControl": "Number",
    "SliderCenterControl": "Number",
    "IntegerControl": "Number",
    "DialControl": "Number",
    "CheckboxControl": "Boolean",
    "ComboBoxControl": "Choice",
    "DropdownControl": "Choice",
    "ColorControl": "Color",
    "RGBAControl": "RGBA",
    "PointControl": "Point",
    "AngleControl": "Angle",
    "PathControl": "Path",
    "RegionControl": "Region",
    "InputButtonControl": "Text",
}

#: What a compiled Fusion plugin's file or bundle is called. Not a whitelist so
#: much as a set of names that are unambiguously *not* a fuse — a stray
#: ``.lua`` in the Plugins directory is a mistake worth catching.
BINARY_SUFFIXES: tuple[str, ...] = (
    ".plugin",
    ".bundle",
    ".ofx",
    ".dll",
    ".so",
    ".dylib",
)

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


class FuseError(ResolveScriptError):
    """Raised when a fuse is declared in a way Fusion will not accept."""


def _pascal(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in _SLUG_RE.split(value) if part)


def _lua_string(value: str) -> str:
    """A Lua double-quoted string literal for ``value``."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _lua_value(value: Any) -> str:
    """Render a Python value as the Lua literal Fusion should see.

    Only the shapes a ``FuRegisterClass`` flag table actually uses are accepted;
    anything else is a typo in the declaration, not something to guess at.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return _lua_string(value)
    raise FuseError(f"cannot render {value!r} as a Lua literal in a flag table")


def _has_image(ports: list[Control] | list[Output]) -> bool:
    """Whether a port list already carries an image connection."""
    return any(port.datatype == "Image" for port in ports)


@dataclass
class Control:
    """One ``AddInput`` in ``Create()`` — an inspector control or a data port.

    A **control** has a ``kind`` (``INPID_InputControl``) and shows up in the
    Inspector. A **port** has ``kind=""`` and is invisible: that is how the image
    input and output of an ordinary tool are declared.

    :param label: the text Fusion shows. Also the default ``id``.
    :param id: the input's ID. Derived from ``label`` when omitted; the global
        ``Process`` sees is ``In`` + this, so ``"Level shift"`` becomes
        ``InLevelShift``.
    :param kind: an ``INPID_InputControl`` name, or ``""`` for a data port.
    :param datatype: ``LINKID_DataType``. Derived from ``kind`` when omitted.
    :param default: the initial value, rendered as a Lua literal — ``6`` for a
        slider, ``"blur"`` for a text field, ``True`` for a checkbox.
    :param main: ``LINK_Main`` index. Fusion uses it to decide the default
        connection; every port on a tool should set it.
    :param lines: ``TEC_Lines``, for the multi-line ``TextEditControl``.
    :param items: ``CBID_DefaultItems``, the popup choices.
    :param minimum / maximum / step: slider range. Omitted when ``None``.
    :param external: ``INP_External``, whether a generator can drive this input.
    """

    label: str
    id: str = ""
    kind: str = ""
    datatype: str = ""
    default: Any = None
    main: int | None = None
    lines: int = 1
    items: list[str] = field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    external: bool = True

    def __post_init__(self) -> None:
        self.label = (self.label or "").strip()
        if not self.label:
            raise FuseError("an input needs a label")
        self.id = self.id.strip() or self.label
        if not self.kind:
            self.datatype = self.datatype.strip() or "Image"
        else:
            if self.kind not in _CONTROL_DATATYPES:
                raise FuseError(
                    f"{self.kind!r} is not a Fusion input control; use one of "
                    f"{', '.join(sorted(_CONTROL_DATATYPES))} or '' for a data port"
                )
            self.datatype = self.datatype.strip() or _CONTROL_DATATYPES[self.kind]
        if self.items and self.kind not in {"ComboBoxControl", "DropdownControl"}:
            raise FuseError(
                f"items= is only meaningful on a popup control, not {self.kind!r}"
            )
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise FuseError(
                f"input {self.id!r} has minimum {self.minimum} above maximum {self.maximum}"
            )

    @property
    def variable(self) -> str:
        """The global ``Create()`` binds this input to, and ``Process`` reads."""
        return f"In{_pascal(self.id)}"

    def is_port(self) -> bool:
        """Whether this is a data port rather than an inspector control."""
        return not self.kind

    def properties(self) -> dict[str, str]:
        """The Lua table entries for this input, in a stable order."""
        entries: dict[str, str] = {}
        if self.default is not None:
            entries["INP_DefaultValue"] = _lua_value(self.default)
        if self.external is not True:
            entries["INP_External"] = "false"
        if self.minimum is not None:
            entries["INPSlider_MinValue"] = _lua_value(self.minimum)
        if self.maximum is not None:
            entries["INPSlider_MaxValue"] = _lua_value(self.maximum)
        if self.step is not None:
            entries["INPSlider_StepSize"] = _lua_value(self.step)
        if self.kind:
            entries["INPID_InputControl"] = _lua_string(self.kind)
        if self.kind in {"TextEditControl", "TextControl"} and self.lines > 1:
            entries["TEC_Lines"] = str(self.lines)
        if self.items:
            rendered = ", ".join(_lua_string(item) for item in self.items)
            entries["CBID_DefaultItems"] = f"{{{rendered}}}"
        entries["LINKID_DataType"] = _lua_string(self.datatype)
        if self.main is not None:
            entries["LINK_Main"] = str(self.main)
        return entries


@dataclass
class Output:
    """One ``AddOutput`` in ``Create()``.

    :param label: the text Fusion shows.
    :param id: the output's ID. The global ``Process`` writes to is ``Out`` + this,
        which is why the default is ``Image`` and not ``Output`` — that is what
        makes the conventional ``OutImage`` name fall out of the default.
    :param datatype: ``LINKID_DataType``. ``Image`` unless stated.
    :param main: ``LINK_Main`` index.
    """

    label: str = "Output"
    id: str = "Image"
    datatype: str = "Image"
    main: int | None = 1

    def __post_init__(self) -> None:
        self.label = (self.label or "").strip() or "Output"
        self.id = self.id.strip() or self.label
        if not self.datatype.strip():
            self.datatype = "Image"

    @property
    def variable(self) -> str:
        """The global ``Create()`` binds this output to, and ``Process`` writes."""
        return f"Out{_pascal(self.id)}"

    def properties(self) -> dict[str, str]:
        entries = {"LINKID_DataType": _lua_string(self.datatype)}
        if self.main is not None:
            entries["LINK_Main"] = str(self.main)
        return entries


@dataclass
class Fuse:
    """A Fusion fuse, declared in Python.

    :param name: the tool's menu name (``REGS_Name``).
    :param class_name: the ``FuRegisterClass`` id. Fusion uses it to save the
        tool in a composition, so changing it invalidates saved comps — it is
        derived from ``name`` and should stay stable.
    :param description: shown as a tooltip (``REGS_OpDescription``).
    :param category: the ``Fuses\\Vendor\\Tool`` menu path
        (``REGS_Category``). Backslashes, not dots.
    :param icon_string: the three-letter registry search code
        (``REGS_OpIconString``). Derived from ``name`` when omitted; a
        letter search for a fuse with no code finds nothing.
    :param tool_type: one of :data:`TOOL_TYPES`.
    :param version / author / license: metadata, written into the file header.
    :param inputs: the ``AddInput`` calls. An ordinary image tool gets an image
        input and an image output for free, so the common case only lists
        controls.
    :param outputs: the ``AddOutput`` calls.
    :param process: the **body** of ``Process(req)`` — statements, not the
        ``function`` line. Fusion runs it every frame the tool is active.
    :param create: extra Lua appended inside ``Create()``, for ports this
        declaration does not model.
    :param flags: extra ``FuRegisterClass`` entries, merged over the generated
        ones. Values may be ``str``, ``int``, ``float`` or ``bool``.
    """

    name: str
    class_name: str = ""
    description: str = ""
    category: str = DEFAULT_CATEGORY
    icon_string: str = ""
    tool_type: str = "CT_Tool"
    version: str = "0.1.0"
    author: str = ""
    license: str = "MIT"
    inputs: list[Control] = field(default_factory=list)
    outputs: list[Output] = field(default_factory=list)
    process: str = ""
    create: str = ""
    flags: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = (self.name or "").strip()
        if not self.name:
            raise FuseError("a fuse needs a name")
        # Checked here rather than at render time: a flag this module cannot
        # express as Lua is a mistake in the declaration, and finding it at
        # construction gives a traceback pointing at the line that wrote it.
        for key, value in self.flags.items():
            if not re.fullmatch(r"(REGS|REG)_[A-Za-z0-9_]+", key):
                raise FuseError(
                    f"flag {key!r} is not a Fusion registration flag; they are named "
                    "REGS_OpDescription, REG_OpNoMask, and so on"
                )
            _lua_value(value)
        self.class_name = self.class_name.strip() or _pascal(self.name)
        if not self.class_name.isidentifier() or not self.class_name[0].isalpha():
            raise FuseError(
                f"fuse class name {self.class_name!r} is not a usable Lua identifier; "
                "pass class_name= explicitly (letters, digits and underscores)"
            )
        if self.tool_type not in TOOL_TYPES:
            raise FuseError(
                f"{self.tool_type!r} is not a Fusion tool class; use one of "
                f"{', '.join(TOOL_TYPES)}"
            )
        self.category = (self.category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY
        self.icon_string = (self.icon_string or self._derive_icon()).strip()[:3]
        if not self.process.strip():
            raise FuseError(
                f"{self.name!r} has no process= body — Fusion calls Process(req) "
                "every frame and does nothing without it"
            )
        if not any(port.datatype == "Image" for port in self.outputs):
            self.outputs.append(Output())
        if not self.is_source and not _has_image(self.inputs):
            # An ordinary tool filters whatever is upstream, so it needs an image
            # in. A source tool replaces the chain and has none, and a fuse that
            # declared its own image port keeps exactly that one.
            self.inputs.insert(0, Control("Input", id="Image", datatype="Image", main=1))
        ports: list[Control | Output] = [*self.inputs, *self.outputs]
        for port in ports:
            if port.main is not None and not isinstance(port.main, int):
                raise FuseError(
                    f"port {port.id!r} has main={port.main!r}; LINK_Main is an integer"
                )

    def _derive_icon(self) -> str:
        letters = re.sub(r"[^A-Za-z]", "", self.class_name)
        return (letters[:3] or "Fus").capitalize()

    # -- identity --------------------------------------------------------
    @property
    def filename(self) -> str:
        """File name inside the Fuses directory: ``Posterize.fuse``."""
        return f"{self.class_name}.fuse"

    @property
    def is_source(self) -> bool:
        """Whether this is a source tool (no image input)."""
        return self.tool_type == "CT_SourceTool"

    @property
    def variables(self) -> list[str]:
        """Every global ``Create()`` defines, in the order the body sees them.

        This is also what a ``Process`` body may reference, which is why
        :mod:`ResolveScript.fuse.validate` can check the body for typos.
        """
        ports: list[Control | Output] = [*self.inputs, *self.outputs]
        return [port.variable for port in ports]

    def as_dict(self) -> dict[str, Any]:
        """Metadata, for manifests and for the CLI."""
        return {
            "name": self.name,
            "class_name": self.class_name,
            "description": self.description,
            "category": self.category,
            "icon_string": self.icon_string,
            "tool_type": self.tool_type,
            "version": self.version,
            "filename": self.filename,
        }

    def describe(self) -> list[str]:
        """Human-readable summary lines, for the CLI."""
        return [
            f"{self.name} {self.version}  ({self.class_name})",
            f"  registry:   {self.category}",
            f"  file:       {self.filename}",
            f"  tool class: {self.tool_type}",
            f"  inputs:     {', '.join(port.id for port in self.inputs) or 'none'}",
            f"  outputs:    {', '.join(port.id for port in self.outputs) or 'none'}",
        ]


@dataclass
class BinaryPlugin:
    """A compiled Fusion plugin, carried rather than built.

    A ``.plugin`` — ``Krokodove.plugin`` and its peers — is a native binary or
    a platform bundle produced by Blackmagic's own (or a vendor's) toolchain.
    There is no source form this package could turn into one, so every
    operation here is deploy/package/remove, never compile. Declaring one
    exists so a project can ship one alongside its fuses: the manifest carries
    it, ``resolvescript plugin install`` puts it in the Plugins directory, and
    ``package`` bundles it.

    :param path: the file or bundle to deploy. Must exist — there is nothing to
        build it from otherwise.
    :param name: what ``list`` calls it. Derived from the file name when
        omitted.
    :param target: the installed file name, when it must differ from the
        source (a macOS bundle copied to Linux, say). Defaults to the source
        name.
    :param notes: free text carried through to ``list`` and ``describe``.
    """

    path: Path
    name: str = ""
    target: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        self.path = Path(self.path).expanduser()
        # The suffix is checked first: a .fuse passed here is the wrong artifact
        # kind, and saying so is more use than reporting that the file is missing
        # (which it very often also is, having never been built).
        if self.path.suffix.lower() not in BINARY_SUFFIXES:
            raise FuseError(
                f"{self.path.name} is not a compiled Fusion plugin; expected one "
                f"of {', '.join(BINARY_SUFFIXES)}. A .fuse is scripted Lua — build "
                "that with a Fuse declaration instead."
            )
        if not self.path.exists():
            raise FuseError(
                f"compiled plugin {self.path} does not exist; a .plugin is a "
                "prebuilt binary, so there is nothing to generate it from"
            )
        self.name = (self.name or self.path.stem).strip() or self.path.stem
        self.target = (self.target or self.path.name).strip() or self.path.name
        if Path(self.target).name != self.target:
            raise FuseError(
                f"target={self.target!r} must be a plain file name; the Plugins "
                "directory is scanned one level deep"
            )

    def describe(self) -> list[str]:
        """Human-readable summary lines, for the CLI."""
        size = self.path.stat().st_size if self.path.is_file() else 0
        kind = "file" if self.path.is_file() else "bundle"
        return [
            f"{self.name}  ({self.target})",
            f"  source:  {self.path}",
            f"  kind:    compiled {kind}"
            + (f", {size} bytes" if size else ""),
            f"  note:    {self.notes}" if self.notes else "  note:    -",
        ]
