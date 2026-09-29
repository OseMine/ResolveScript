"""Smoke tests — the real declaration, built and checked.

A fuse is Lua, so there is nothing to mock: the meaningful test is that what
gets written compiles. The checks below run in layers, and each one says which
layer it is, so a green run never implies a stronger guarantee than the machine
it ran on could give.
"""

from __future__ import annotations

import pytest

import @NAME@
from ResolveScript.fuse import (
    Control,
    Fuse,
    FuseError,
    build,
    checked_with,
    install,
    list_installed,
    package_fuse,
    problems,
    render_fuse,
    uninstall,
)

FUSE = @NAME@.FUSE


def test_metadata() -> None:
    assert FUSE.name == "@NAME_LABEL@"
    assert FUSE.class_name == "@CLASS_NAME@"
    assert FUSE.version == "@VERSION@"
    assert FUSE.filename == "@CLASS_NAME@.fuse"


def test_the_image_ports_are_added_for_you() -> None:
    """A tool filters what is upstream, so it takes an image in and hands one on."""
    assert FUSE.inputs[0].variable == "InImage"
    assert FUSE.outputs[0].variable == "OutImage"
    assert FUSE.is_source is False


def test_the_registered_name_is_what_fusion_shows() -> None:
    source = render_fuse(FUSE)
    assert 'FuRegisterClass("@CLASS_NAME@", CT_Tool, {' in source
    assert 'REGS_Name = "@NAME_LABEL@"' in source
    # A letter search in the registry finds a tool by its three-letter code; a
    # fuse with no code is invisible to one.
    assert 'REGS_OpIconString = "@ICON@"' in source


def test_the_category_is_a_backslash_path() -> None:
    """Dots would make the tool sit at the registry root, not under Fuses."""
    assert "REGS_Category = \"Fuses\\\\ResolveScript\"" in render_fuse(FUSE)


def test_no_structural_problems() -> None:
    assert problems(FUSE) == []


def test_the_generated_file_compiles(tmp_path) -> None:
    """The check that actually matters: Lua has to parse it."""
    result = build(FUSE, tmp_path)
    path = tmp_path / FUSE.filename
    assert path.is_file()
    report = checked_with(path)
    if "no Lua interpreter" in report:
        pytest.skip(f"structural checks only: {report}")
    # build() raises rather than returning, so reaching here means luac agreed.
    assert "parse" in report


def test_a_syntax_error_is_caught_not_shipped(tmp_path) -> None:
    """Fusion reports a broken fuse by not listing it, so this is the only guard."""
    broken = Fuse(name="Broken", process="OutImage:Set(req, ")
    with pytest.raises(FuseError, match="not a loadable fuse"):
        build(broken, tmp_path)
    # The file is left on disk: it is usually one small fix from working, and
    # the message names the line.
    assert (tmp_path / "Broken.fuse").is_file()


def test_a_typo_in_a_port_name_is_caught() -> None:
    """``InAmunt`` is nil at runtime, and nil has no method."""
    typo = Fuse(name="Typo", process="local v = InAmunt:GetValue(req).Value\n")
    found = problems(typo)
    assert found and "InAmunt" in found[0]


def test_a_source_tool_declares_no_image_input() -> None:
    """A source replaces the chain, so it has nothing to filter."""
    source = Fuse(
        name="Solid",
        tool_type="CT_SourceTool",
        inputs=[Control("Width", datatype="Number", default=64)],
        process="OutImage:Set(req, InWidth:GetValue(req))",
    )
    assert source.is_source is True
    assert "REG_OpNoMask" not in render_fuse(source)
    assert "InImage" not in source.variables


def test_install_then_uninstall(tmp_path) -> None:
    install(FUSE, tmp_path)
    assert FUSE.class_name in list_installed(tmp_path)
    assert (tmp_path / FUSE.filename).is_file()

    removed = uninstall(FUSE.class_name, tmp_path)
    assert removed
    assert FUSE.class_name not in list_installed(tmp_path)
    assert not (tmp_path / FUSE.filename).exists()


def test_package_bundles_the_fuse_with_a_checksum(tmp_path) -> None:
    result = package_fuse(FUSE, tmp_path)
    assert result.archive.is_file()
    assert result.sha256
    assert FUSE.filename in result.files
    assert "resolvescript.json" in result.files
    assert result.checksum_file is not None
    assert result.sha256 in result.checksum_file.read_text(encoding="utf-8")
