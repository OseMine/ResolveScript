"""@NAME_LABEL@ — a Fusion fuse.

A *fuse* is one Lua file with a ``.fuse`` extension that Fusion compiles on the
fly. This module is not the fuse; it is the declaration the fuse is generated
from::

    resolvescript fuse build       # writes dist/Posterize.fuse
    resolvescript fuse install     # writes it into the Fuses directory
    resolvescript fuse package     # zips it, for handing to somebody else

Everything that matters about the tool is in :data:`FUSE` below. The one part
that is genuinely Lua is ``process=``: it runs inside Fusion, against Fusion's
image API, once per frame while the tool is in use. A bracket-free operation
is a couple of lines; pixel work goes through ``DoExpression`` with a
``[=[ ... ]=]`` block, whose contents Fusion compiles as its own expression
language rather than Lua.

The image input and output are added for you — a tool filters whatever is
upstream, so it takes an image in and hands one on. Only controls need
declaring.
"""

from __future__ import annotations

from ResolveScript.fuse import Control, Fuse

#: The tool. ``class_name`` is the id Fusion stores the tool under, so changing
#: it invalidates any composition that already uses this tool.
FUSE = Fuse(
    name="@NAME_LABEL@",
    class_name="@CLASS_NAME@",
    description="@DESCRIPTION@",
    author="@AUTHOR@",
    inputs=[
        Control(
            "Amount",
            kind="SliderControl",
            datatype="Number",
            default=0.5,
            minimum=0.0,
            maximum=1.0,
            step=0.01,
        ),
    ],
    process='''
-- Fusion calls this once per frame. Get the image in, work on a copy, and set
-- the result on the output; GetValue returns a reference the tool owns, so
-- mutate the copy rather than the input.
local amount = InAmount:GetValue(req).Value
local out = InImage:GetValue(req):Copy()

out:DoExpression([=[
    amount = clamp(amount, 0, 1)
    a = a * amount
]=])

OutImage:Set(req, out)
''',
)
