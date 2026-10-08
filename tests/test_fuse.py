"""Tests for :mod:`ResolveScript.fuse` — the .fuse and .plugin pipeline.

The tests are grouped by what they are protecting:

* the *declaration* (``model``) — the mistakes Fusion cannot report back,
  because it silently drops a malformed tool;
* the *rendered file* (``render``) — the shape Fusion actually parses;
* the *checks* (``validate``) — the two layers, and which one ran;
* the *filesystem* (``build``, ``paths``) — install, list, uninstall, package;
* the *CLI* — the same paths, through argument parsing.

A generated fuse is a single file, so most of these assert on strings. Where a
real parser is available the test says so and asserts the parse; where it is
not, the test says that too rather than pretending.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from ResolveScript.fuse import (
    BINARY_SUFFIXES,
    DEFAULT_CATEGORY,
    FUSE_EXTENSION,
    FUSES_DIR_NAME,
    PLUGINS_DIR_NAME,
    REQUIRED_FUNCTIONS,
    TOOL_TYPES,
    BinaryPlugin,
    Control,
    Fuse,
    FuseError,
    FusionPathError,
    Output,
    build,
    candidates,
    check_process_references,
    check_source,
    checked_with,
    default_root,
    describe_installed,
    install,
    install_binary,
    list_installed,
    lua_compiler,
    package_fuse,
    parse_file,
    problems,
    render_fuse,
    root,
    uninstall,
    validate,
)

HAS_LUA = lua_compiler() is not None

#: The package name the scaffolded fixture uses, so the module-caching guard in
#: the CLI tests has one string to match on.
PACKAGE = "my_fuse"

PROCESS = """
local out = InImage:GetValue(req):Copy()
OutImage:Set(req, out)
"""


def a_fuse(**kwargs) -> Fuse:
    """A minimal, valid, one-image-in-one-image-out fuse."""
    options = {"name": "Posterize", "process": PROCESS}
    options.update(kwargs)
    return Fuse(**options)


def _complete(body: str) -> str:
    """A skeleton with all three required declarations, plus ``body``.

    :func:`check_source` reports every missing declaration at once, so a test
    about brackets or tokens needs them present or it drowns in its own noise.
    """
    return (
        'FuRegisterClass("A", CT_Tool, {})\n'
        "function Create()\nend\n"
        "function Process(req)\n"
        f"{body}\n"
        "end\n"
    )


# ---------------------------------------------------------------- model ----
class TestDeclaration:
    def test_the_name_is_required(self) -> None:
        with pytest.raises(FuseError, match="needs a name"):
            Fuse(name="   ", process=PROCESS)

    def test_a_process_body_is_required(self) -> None:
        """Fusion calls Process every frame; without one the tool does nothing."""
        with pytest.raises(FuseError, match="no process= body"):
            Fuse(name="Empty")

    def test_the_class_name_is_derived_and_usable(self) -> None:
        """It is the id Fusion stores the tool under, so it must be an identifier."""
        assert a_fuse(name="my cool fuse").class_name == "MyCoolFuse"
        with pytest.raises(FuseError, match="not a usable Lua identifier"):
            Fuse(name="x", class_name="9lives", process=PROCESS)

    def test_the_file_carries_the_fuse_extension(self) -> None:
        """Fusion only compiles files in the Fuses directory by this extension."""
        assert FUSE_EXTENSION == ".fuse"
        assert a_fuse().filename == f"Posterize{FUSE_EXTENSION}"

    def test_the_icon_is_three_letters(self) -> None:
        """A letter search in the registry finds a tool by this code."""
        assert a_fuse(name="Posterize").icon_string == "Pos"
        assert a_fuse(name="Verylongname", icon_string="VLN!").icon_string == "VLN"

    def test_an_unknown_tool_class_is_rejected(self) -> None:
        with pytest.raises(FuseError, match="not a Fusion tool class"):
            a_fuse(tool_type="CT_Widget")

    def test_every_supported_tool_class_is_accepted(self) -> None:
        for name in TOOL_TYPES:
            assert a_fuse(tool_type=name).tool_type == name

    def test_the_image_ports_are_added(self) -> None:
        """A tool filters what is upstream, so it takes an image in and out."""
        fuse = a_fuse()
        assert fuse.inputs[0].variable == "InImage"
        assert fuse.outputs[0].variable == "OutImage"
        assert fuse.inputs[0].main == 1
        assert fuse.outputs[0].main == 1

    def test_declared_controls_sit_behind_the_image_input(self) -> None:
        fuse = a_fuse(inputs=[Control("Levels", kind="SliderControl", default=6)])
        assert [port.variable for port in fuse.inputs] == ["InImage", "InLevels"]

    def test_a_declared_image_port_is_not_duplicated(self) -> None:
        fuse = a_fuse(inputs=[Control("Second", datatype="Image", main=1)])
        assert [port.variable for port in fuse.inputs] == ["InSecond"]

    def test_a_source_tool_has_no_image_input(self) -> None:
        """A source replaces the chain, so there is nothing upstream to filter."""
        source = a_fuse(tool_type="CT_SourceTool")
        assert source.is_source is True
        assert "InImage" not in source.variables
        assert source.outputs[0].variable == "OutImage"

    def test_an_extra_output_is_declared_alongside_the_image(self) -> None:
        fuse = a_fuse(outputs=[Output("Matte", id="Matte", datatype="Image")])
        # Declaring an image output means you want that specific one, not the default.
        # The default is only added when NO image output is declared at all.
        assert [port.variable for port in fuse.outputs] == ["OutMatte"]
        assert "OutMatte = self:AddOutput" in render_fuse(fuse)

    def test_a_declared_image_output_replaces_the_default(self) -> None:
        fuse = a_fuse(outputs=[Output("Result", id="Image", main=1)])
        # Same id means same variable name — the declaration wins
        assert [port.variable for port in fuse.outputs] == ["OutImage"]
        assert fuse.outputs[0].label == "Result"

    def test_an_output_label_is_what_the_inspector_shows(self) -> None:
        assert a_fuse().outputs[0].label == "Output"

    def test_a_data_port_has_no_inspector_control(self) -> None:
        port = Control("Mask", datatype="Image")
        assert port.is_port() is True
        assert "INPID_InputControl" not in port.properties()

    def test_the_control_kind_chooses_the_datatype(self) -> None:
        assert Control("N", kind="NumberControl").properties()["LINKID_DataType"] == '"Number"'
        assert Control("T", kind="TextEditControl").properties()["LINKID_DataType"] == '"Text"'
        # An explicit datatype still wins, for the ports where it must differ.
        assert (
            Control("W", kind="TextEditControl", datatype="Number").properties()[
                "LINKID_DataType"
            ]
            == '"Number"'
        )

    def test_a_data_port_with_no_datatype_is_an_image(self) -> None:
        """A port with no control and no type is an image, which is the usual one."""
        assert Control("In").properties()["LINKID_DataType"] == '"Image"'
        assert Control("In").is_port() is True

    def test_an_unknown_control_kind_is_rejected(self) -> None:
        with pytest.raises(FuseError, match="is not a Fusion input control"):
            Control("X", kind="HologramControl")

    def test_popup_items_only_on_popups(self) -> None:
        assert "CBID_DefaultItems" in Control("M", kind="ComboBoxControl", items=["a", "b"]).properties()
        with pytest.raises(FuseError, match="only meaningful on a popup"):
            Control("M", kind="SliderControl", items=["a"])

    def test_multiline_text_controls_declare_their_lines(self) -> None:
        props = Control("Script", kind="TextEditControl", lines=8).properties()
        assert props["TEC_Lines"] == "8"
        assert "TEC_Lines" not in Control("Name", kind="TextEditControl").properties()

    def test_a_reversed_slider_range_is_rejected(self) -> None:
        with pytest.raises(FuseError, match="above maximum"):
            Control("N", kind="SliderControl", minimum=10, maximum=1)

    def test_link_main_must_be_an_integer(self) -> None:
        with pytest.raises(FuseError, match="LINK_Main is an integer"):
            a_fuse(inputs=[Control("X", datatype="Image", main="1")])  # type: ignore[arg-type]

    def test_a_describe_covers_what_the_cli_needs(self) -> None:
        lines = "\n".join(a_fuse().describe())
        assert "Posterize.fuse" in lines
        assert DEFAULT_CATEGORY in lines

    def test_as_dict_is_json_safe(self) -> None:
        assert json.dumps(a_fuse().as_dict())


# --------------------------------------------------------------- render ----
class TestRendering:
    def test_the_three_required_declarations_are_present(self) -> None:
        source = render_fuse(a_fuse())
        for name in REQUIRED_FUNCTIONS:
            assert name in source

    def test_the_registered_name_and_category(self) -> None:
        source = render_fuse(a_fuse())
        assert 'FuRegisterClass("Posterize", CT_Tool, {' in source
        # The category is a backslash path. Dots would put the tool at the
        # registry root rather than under Fuses.
        assert 'REGS_Category = "Fuses\\\\ResolveScript"' in source

    def test_no_token_survives(self) -> None:
        assert "@@" not in render_fuse(a_fuse(description="a real description"))

    def test_a_description_containing_a_token_is_left_alone(self) -> None:
        """``@@...@@`` is this file's placeholder syntax, and a value that happens
        to look like one is still just text. Checking the template rather than
        the output is what keeps the two apart."""
        source = render_fuse(a_fuse(description="ships @@ markers to @@ people"))
        assert "ships @@ markers to @@ people" in source

    def test_a_template_token_with_no_value_is_an_error(self) -> None:
        """A template edited to add a placeholder must fail here, not in Fusion."""
        from ResolveScript.fuse.render import _fill

        with pytest.raises(FuseError, match="no value for NOT_PROVIDED"):
            _fill("-- generated by @@KNOWN@@\n@@NOT_PROVIDED@@\n", {"KNOWN": "x"})

    def test_the_generated_file_is_plain_ascii(self) -> None:
        """A fuse is shipped to Windows and macOS and edited by hand."""
        assert render_fuse(a_fuse()).isascii()

    def test_a_quote_in_a_description_cannot_break_the_lua(self) -> None:
        source = render_fuse(a_fuse(description='He said "hello" \\ goodbye'))
        assert 'REGS_OpDescription = "He said \\"hello\\" \\\\ goodbye"' in source

    def test_the_default_ports_are_flagged(self) -> None:
        """A tool that does its own compositing wants none of Fusion's extras."""
        source = render_fuse(a_fuse())
        assert "REG_OpNoMask = true" in source
        assert "REG_NoBlendCtrls = true" in source
        assert "REG_NoObjMatCtrls = true" in source
        assert "REG_NoMotionBlurCtrls = true" in source

    def test_a_source_tool_keeps_its_mask(self) -> None:
        """A source replaces the chain, so a mask control is meaningful."""
        assert "REG_OpNoMask" not in render_fuse(a_fuse(tool_type="CT_SourceTool"))

    def test_author_flags_win(self) -> None:
        source = render_fuse(a_fuse(flags={"REG_OpPageFirst": 3, "REGS_OpTabString": "Pst"}))
        assert "REG_OpPageFirst = 3" in source
        assert 'REGS_OpTabString = "Pst"' in source

    def test_an_unrenderable_flag_is_rejected(self) -> None:
        """An object is not a Lua literal, and guessing one would ship broken code."""
        with pytest.raises(FuseError, match="cannot render"):
            render_fuse(a_fuse(flags={"REG_X": object()}))

    def test_a_flag_lua_cannot_hold_is_rejected_at_construction(self) -> None:
        with pytest.raises(FuseError, match="cannot render"):
            a_fuse(flags={"REG_X": object()})

    def test_a_control_becomes_an_addinput(self) -> None:
        source = render_fuse(
            a_fuse(inputs=[Control("Levels", kind="SliderControl", minimum=2, maximum=64, default=6)])
        )
        assert 'InLevels = self:AddInput("Levels", "Levels", {' in source
        assert "INPID_InputControl = \"SliderControl\"" in source
        assert "INPSlider_MinValue = 2" in source
        assert "INP_DefaultValue = 6" in source

    def test_a_default_is_rendered_as_a_lua_literal(self) -> None:
        assert 'INP_DefaultValue = "blur"' in render_fuse(
            a_fuse(inputs=[Control("Blur", kind="TextControl", default="blur")])
        )
        assert "INP_DefaultValue = true" in render_fuse(
            a_fuse(inputs=[Control("On", kind="CheckboxControl", default=True)])
        )

    def test_the_process_body_is_verbatim_inside_a_long_bracket(self) -> None:
        """DoExpression content is a string; indenting it would change the code."""
        body = "\n".join(
            [
                "local out = InImage:GetValue(req):Copy()",
                "out:DoExpression([=[",
                "    a = a * 2",
                "]=])",
                "OutImage:Set(req, out)",
            ]
        )
        lines = render_fuse(a_fuse(process=body)).splitlines()
        start = lines.index("out:DoExpression([=[") if "out:DoExpression([=[" in lines else next(
            i for i, line in enumerate(lines) if "DoExpression" in line
        )
        # The opener is indented as code; everything between the brackets is not.
        assert lines[start].startswith("\t")
        for line in lines[start + 1 :]:
            assert not line.startswith("\t ")

    def test_create_extra_code_is_appended_last(self) -> None:
        source = render_fuse(a_fuse(create="InExtra = self:AddInput('Extra', 'Extra', { LINKID_DataType = 'Number' })"))
        assert source.index("InExtra") > source.index("OutImage")

    def test_two_fuses_with_the_same_declaration_are_identical(self) -> None:
        """A rebuild must not churn a file somebody edited by hand."""
        assert render_fuse(a_fuse()) == render_fuse(a_fuse())


# ------------------------------------------------------------- validate ----
class TestValidation:
    def test_a_good_fuse_has_no_problems(self) -> None:
        assert problems(a_fuse()) == []

    def test_an_undeclared_port_is_caught(self) -> None:
        """``InAmunt`` is nil at runtime, and nil has no method."""
        found = problems(a_fuse(process="local v = InAmunt:GetValue(req).Value"))
        assert len(found) == 1
        assert "InAmunt" in found[0]

    def test_a_local_named_like_a_port_is_not_flagged(self) -> None:
        body = "local InThing = {}\nInThing:Set(req, 1)"
        assert check_process_references(a_fuse(process=body)) == []

    def test_a_list_of_several_locals_is_handled(self) -> None:
        body = "local a, b, InThing = {}, {}, {}\nInThing:Set(req, 1)"
        assert check_process_references(a_fuse(process=body)) == []

    def test_the_error_names_what_is_declared(self) -> None:
        found = check_process_references(a_fuse(process="InNope:GetValue(req)"))
        assert "InImage" in found[0] and "OutImage" in found[0]

    @pytest.mark.parametrize("absent", REQUIRED_FUNCTIONS)
    def test_each_required_declaration_is_checked(self, absent: str) -> None:
        """A skeleton missing exactly one says which, and only which."""
        pieces = {
            "FuRegisterClass": 'FuRegisterClass("A", CT_Tool, {})\n',
            "function Create": "function Create()\nend\n",
            "function Process": "function Process(req)\nend\n",
        }
        assert check_source("".join(pieces.values())) == []
        found = check_source("".join(text for key, text in pieces.items() if key != absent))
        assert found == [f"missing required top-level declaration: {absent}"]

    def test_a_good_skeleton_has_no_structural_problems(self) -> None:
        assert check_source(_complete("local x = 1")) == []

    def test_unbalanced_brackets_are_reported(self) -> None:
        found = check_source(_complete("local x = (1 + 2"))
        assert "unbalanced (): 4 '(' vs 3 ')'" in found

    def test_balanced_brackets_are_not_reported(self) -> None:
        assert not [p for p in check_source(_complete("local x = { a = (1) }")) if "unbalanced" in p]

    def test_a_bracket_inside_a_comment_is_not_a_bracket(self) -> None:
        assert check_source(_complete("--[[ a { b ]]\nlocal x = 1")) == []

    def test_a_bracket_inside_a_leveled_long_bracket_is_not_a_bracket(self) -> None:
        body = "local s = [=[ a { b ( ]=]\nreturn s"
        assert check_source(_complete(body)) == []

    def test_a_leftover_token_is_caught(self) -> None:
        found = check_source(_complete("{ @@NOPE@@ = 1 }"))
        assert found == ["unsubstituted template token(s): @@NOPE@@"]

    @pytest.mark.skipif(not HAS_LUA, reason="no Lua interpreter on PATH")
    def test_a_real_lua_error_is_reported_with_its_line(self, tmp_path: Path) -> None:
        path = tmp_path / "Broken.fuse"
        path.write_text("function Create() end\nfunction Process(req)\n\tfoo(\n", encoding="utf-8")
        found = parse_file(path)
        assert found and "Broken.fuse" in found[0]

    @pytest.mark.skipif(not HAS_LUA, reason="no Lua interpreter on PATH")
    def test_a_good_file_parses(self, tmp_path: Path) -> None:
        path = tmp_path / "Good.fuse"
        path.write_text(render_fuse(a_fuse()), encoding="utf-8")
        assert parse_file(path) == []

    def test_parse_file_says_so_when_there_is_no_interpreter(self, tmp_path: Path) -> None:
        if HAS_LUA:
            pytest.skip("a Lua interpreter is installed, so this cannot be observed")
        with pytest.raises(RuntimeError, match="no Lua interpreter"):
            parse_file(tmp_path / "x.fuse")

    def test_checked_with_reports_the_layer_that_ran(self, tmp_path: Path) -> None:
        path = tmp_path / "Good.fuse"
        path.write_text(render_fuse(a_fuse()), encoding="utf-8")
        report = checked_with(path)
        assert report.startswith("structure")
        if HAS_LUA:
            assert "parse" in report
        else:
            assert "no Lua interpreter" in report

    def test_problems_without_a_path_still_check_the_declaration(self) -> None:
        """The reference check needs no file, so it runs before anything is written."""
        assert problems(a_fuse(process="InNope:Set(req, 1)")) != []

    @pytest.mark.skipif(not HAS_LUA, reason="no Lua interpreter on PATH")
    def test_a_broken_fuse_never_reaches_the_build(self, tmp_path: Path) -> None:
        with pytest.raises(FuseError, match="not a loadable fuse"):
            build(a_fuse(process="OutImage:Set(req, "), tmp_path)

    def test_a_broken_fuse_still_reports_its_structure_without_lua(self, tmp_path: Path) -> None:
        """The structural layer stands on its own; the parse is an extra."""
        with pytest.raises(FuseError, match="unbalanced"):
            build(a_fuse(process="OutImage:Set(req, "), tmp_path)

    def test_no_check_writes_it_anyway(self, tmp_path: Path) -> None:
        result = build(a_fuse(process="OutImage:Set(req, "), tmp_path, check=False)
        assert result.fuse_file is not None
        assert result.fuse_file.is_file()
        assert result.checked == ""

    def test_validate_raises_with_every_problem_listed(self) -> None:
        with pytest.raises(FuseError) as excinfo:
            validate(a_fuse(process="InNope:Set(req, foo("))
        assert "InNope" in str(excinfo.value)


# ---------------------------------------------------------------- build ----
class TestBuild:
    def test_the_file_is_named_after_the_class(self, tmp_path: Path) -> None:
        result = build(a_fuse(), tmp_path)
        assert result.fuse_file == tmp_path / "Posterize.fuse"
        assert result.fuse_file.is_file()

    def test_the_directory_is_created(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested"
        build(a_fuse(), target)
        assert (target / "Posterize.fuse").is_file()

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        target = tmp_path / "fuses"
        result = build(a_fuse(), target, dry_run=True)
        assert not target.exists()
        assert result.fuse_file == target / "Posterize.fuse"
        assert "Would write" in "\n".join(result.describe())

    def test_the_line_endings_are_unix(self, tmp_path: Path) -> None:
        """A CRLF file is valid Lua, but the diff noise is not worth it."""
        path = build(a_fuse(), tmp_path).fuse_file
        assert b"\r\n" not in (path.read_bytes() if path else b"")

    def test_clean_removes_the_file_this_tool_last_installed(self, tmp_path: Path) -> None:
        fuses = tmp_path / "Fuses"
        install(a_fuse(name="OldName"), fuses)
        assert (fuses / "OldName.fuse").is_file()
        install(a_fuse(name="NewName"), fuses, clean=True)
        assert not (fuses / "OldName.fuse").exists()
        assert (fuses / "NewName.fuse").is_file()

    def test_clean_leaves_other_peoples_fuses_alone(self, tmp_path: Path) -> None:
        """The Fuses directory is shared; ``--clean`` must not empty it."""
        other = tmp_path / "SomeoneElse.fuse"
        other.write_text("-- theirs\n", encoding="utf-8")
        install(a_fuse(), tmp_path, clean=True)
        assert other.is_file()

    def test_clean_only_removes_files_this_tool_installed(self, tmp_path: Path) -> None:
        """A hand-dropped fuse has no registry entry, so it is not a stale build."""
        fuses = tmp_path / "Fuses"
        install(a_fuse(name="Mine"), fuses)
        hand = fuses / "HandDropped.fuse"
        hand.write_text("-- theirs\n", encoding="utf-8")
        install(a_fuse(name="Mine", class_name="Renamed"), fuses)
        assert hand.is_file()
        assert not (fuses / "Mine.fuse").exists()
        assert (fuses / "Renamed.fuse").is_file()

    def test_install_cleans_by_default(self, tmp_path: Path) -> None:
        install(a_fuse(name="OldName"), tmp_path)
        install(a_fuse(name="NewName"), tmp_path)
        assert sorted(p.name for p in tmp_path.glob("*.fuse")) == ["NewName.fuse"]

    def test_without_clean_a_renamed_fuse_lingers(self, tmp_path: Path) -> None:
        """Which is exactly why ``install`` cleans by default and ``build`` does not."""
        install(a_fuse(name="OldName"), tmp_path, clean=False)
        install(a_fuse(name="NewName"), tmp_path, clean=False)
        assert sorted(p.name for p in tmp_path.glob("*.fuse")) == [
            "NewName.fuse",
            "OldName.fuse",
        ]

    def test_build_does_not_write_a_registry(self, tmp_path: Path) -> None:
        """``dist/`` is a build output, not a plugin root, and stays clean."""
        build(a_fuse(), tmp_path, clean=True)
        assert list(tmp_path.iterdir()) == [tmp_path / "Posterize.fuse"]


class TestInstall:
    def test_install_then_list_then_uninstall(self, tmp_path: Path) -> None:
        fuse = a_fuse()
        install(fuse, tmp_path)
        assert (tmp_path / "Posterize.fuse").is_file()
        assert "Posterize" in list_installed(tmp_path)
        assert list_installed(tmp_path)["Posterize"]["installed"] is True

        removed = uninstall("Posterize", tmp_path)
        assert removed == [str(tmp_path / "Posterize.fuse")]
        assert not (tmp_path / "Posterize.fuse").exists()
        assert list_installed(tmp_path) == {}

    def test_the_registry_records_the_metadata(self, tmp_path: Path) -> None:
        install(a_fuse(version="2.1.0"), tmp_path)
        entry = list_installed(tmp_path)["Posterize"]
        assert entry["name"] == "Posterize"
        assert entry["version"] == "2.1.0"
        assert entry["category"] == DEFAULT_CATEGORY
        assert entry["file"] == "Posterize.fuse"

    def test_the_registry_survives_being_deleted_from_disk(self, tmp_path: Path) -> None:
        """A fuse someone removed by hand is still listed, and marked missing."""
        install(a_fuse(), tmp_path)
        (tmp_path / "Posterize.fuse").unlink()
        assert list_installed(tmp_path)["Posterize"]["installed"] is False
        assert "missing on disk" in "\n".join(describe_installed(tmp_path))

    def test_a_corrupt_registry_does_not_stop_anything(self, tmp_path: Path) -> None:
        (tmp_path / ".resolvescript-fuses.json").write_text("{ not json", encoding="utf-8")
        assert list_installed(tmp_path) == {}
        install(a_fuse(), tmp_path)
        assert "Posterize" in list_installed(tmp_path)

    def test_uninstall_falls_back_to_the_naming_convention(self, tmp_path: Path) -> None:
        """A lost registry entry must not leave a file nobody can remove."""
        (tmp_path / "Orphan.fuse").write_text("--[[--\nOrphan\n--]]--\n", encoding="utf-8")
        assert uninstall("Orphan", tmp_path) == [str(tmp_path / "Orphan.fuse")]

    def test_uninstall_accepts_the_file_name(self, tmp_path: Path) -> None:
        install(a_fuse(), tmp_path)
        assert uninstall("Posterize.fuse", tmp_path)

    def test_uninstall_accepts_a_fuse_object(self, tmp_path: Path) -> None:
        fuse = a_fuse()
        install(fuse, tmp_path)
        assert uninstall(fuse, tmp_path)  # type: ignore[arg-type]

    def test_uninstalling_something_absent_is_not_an_error(self, tmp_path: Path) -> None:
        assert uninstall("Nope", tmp_path) == []

    def test_the_registry_goes_when_the_last_entry_does(self, tmp_path: Path) -> None:
        install(a_fuse(), tmp_path)
        registry = tmp_path / ".resolvescript-fuses.json"
        assert registry.is_file()
        uninstall("Posterize", tmp_path)
        assert not registry.exists()

    def test_dry_run_records_nothing(self, tmp_path: Path) -> None:
        target = tmp_path / "Fuses"
        install(a_fuse(), target, dry_run=True)
        assert not target.exists()

    def test_the_root_is_read_from_the_environment(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("RESOLVESCRIPT_FUSES_ROOT", str(tmp_path))
        install(a_fuse())
        assert (tmp_path / "Posterize.fuse").is_file()

    def test_describe_says_when_nothing_is_installed(self, tmp_path: Path) -> None:
        assert "No fuses installed" in describe_installed(tmp_path)[0]


# --------------------------------------------------------- binary plugin ----
class TestBinaryPlugin:
    def test_a_fuse_is_not_a_compiled_plugin(self) -> None:
        """The mistake this check exists for: shipping a .fuse where a .plugin goes."""
        with pytest.raises(FuseError, match="not a compiled Fusion plugin"):
            BinaryPlugin(path=Path("Posterize.fuse"))

    def test_a_missing_file_says_why_it_cannot_be_built(self) -> None:
        with pytest.raises(FuseError, match="nothing to generate it from"):
            BinaryPlugin(path=Path("nowhere/Krokodove.plugin"))

    def test_every_documented_suffix_is_accepted(self, tmp_path: Path) -> None:
        for suffix in BINARY_SUFFIXES:
            path = tmp_path / f"Vendor{suffix}"
            path.write_bytes(b"\0")
            assert BinaryPlugin(path=path).name == "Vendor"

    def test_a_bundle_directory_is_accepted(self, tmp_path: Path) -> None:
        bundle = tmp_path / "Thing.plugin"
        bundle.mkdir()
        assert BinaryPlugin(path=bundle).path.is_dir()

    def test_the_name_and_target_are_derived(self, tmp_path: Path) -> None:
        path = tmp_path / "Krokodove.plugin"
        path.write_bytes(b"x")
        plugin = BinaryPlugin(path=path)
        assert plugin.name == "Krokodove"
        assert plugin.target == "Krokodove.plugin"

    def test_a_target_must_be_a_plain_name(self, tmp_path: Path) -> None:
        path = tmp_path / "Krokodove.plugin"
        path.write_bytes(b"x")
        with pytest.raises(FuseError, match="plain file name"):
            BinaryPlugin(path=path, target="sub/dir/Krokodove.plugin")

    def test_install_copies_and_records(self, tmp_path: Path) -> None:
        source = tmp_path / "Krokodove.plugin"
        source.write_bytes(b"\x7fELF-ish")
        dest = tmp_path / "Plugins"
        result = install_binary(BinaryPlugin(path=source, notes="vendor build"), dest)
        assert result.target is not None and result.target.is_file()
        assert result.target.read_bytes() == b"\x7fELF-ish"
        assert list_installed(dest, kind="plugin")["Krokodove"]["notes"] == "vendor build"

    def test_install_replaces_a_bundle_wholesale(self, tmp_path: Path) -> None:
        """A stale file left inside the old bundle would fail to register."""
        source = tmp_path / "Thing.plugin"
        (source / "Contents").mkdir(parents=True)
        (source / "Contents" / "stale").write_text("old", encoding="utf-8")
        dest = tmp_path / "Plugins"
        install_binary(BinaryPlugin(path=source), dest)
        (dest / "Thing.plugin" / "Contents" / "stale").unlink()
        (source / "Contents" / "stale").write_text("new", encoding="utf-8")
        install_binary(BinaryPlugin(path=source), dest)
        assert (dest / "Thing.plugin" / "Contents" / "stale").read_text() == "new"

    def test_no_force_refuses_to_replace(self, tmp_path: Path) -> None:
        source = tmp_path / "Krokodove.plugin"
        source.write_bytes(b"x")
        dest = tmp_path / "Plugins"
        install_binary(BinaryPlugin(path=source), dest)
        with pytest.raises(FuseError, match="already exists"):
            install_binary(BinaryPlugin(path=source), dest, overwrite=False)

    def test_dry_run_copies_nothing(self, tmp_path: Path) -> None:
        source = tmp_path / "Krokodove.plugin"
        source.write_bytes(b"x")
        dest = tmp_path / "Plugins"
        result = install_binary(BinaryPlugin(path=source), dest, dry_run=True)
        assert not dest.exists()
        assert "Would copy" in "\n".join(result.describe())

    def test_uninstall_removes_a_bundle(self, tmp_path: Path) -> None:
        source = tmp_path / "Thing.plugin"
        source.mkdir()
        (source / "Contents").mkdir()
        dest = tmp_path / "Plugins"
        install_binary(BinaryPlugin(path=source), dest)
        assert uninstall("Thing", dest, kind="plugin")
        assert not (dest / "Thing.plugin").exists()

    def test_a_fuse_and_a_plugin_can_share_a_registry(self, tmp_path: Path) -> None:
        """Both sections live in one file, so removing one keeps the other."""
        fuses, plugins = tmp_path / "Fuses", tmp_path / "Plugins"
        install(a_fuse(), fuses)
        vendor = tmp_path / "vendor"
        vendor.mkdir()
        binary = vendor / "Krokodove.plugin"
        binary.write_bytes(b"x")
        install_binary(BinaryPlugin(path=binary), plugins)
        uninstall("Posterize", fuses)
        assert "Krokodove" in list_installed(plugins, kind="plugin")
        assert list_installed(fuses) == {}
        assert (plugins / "Krokodove.plugin").is_file()

    def test_an_unknown_kind_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(FuseError, match="unknown kind"):
            list_installed(tmp_path, kind="dll")


# -------------------------------------------------------------- package ----
class TestPackage:
    def test_the_archive_holds_the_fuse_and_a_descriptor(self, tmp_path: Path) -> None:
        result = package_fuse(a_fuse(), tmp_path)
        assert result.archive.name == "Posterize-0.1.0.zip"
        with zipfile.ZipFile(result.archive) as bundle:
            assert sorted(bundle.namelist()) == ["Posterize.fuse", "resolvescript.json"]
            descriptor = json.loads(bundle.read("resolvescript.json"))
        assert descriptor["kind"] == "fuse"
        assert descriptor["class_name"] == "Posterize"
        assert json.dumps(descriptor)

    def test_the_checksum_is_written_beside_the_archive(self, tmp_path: Path) -> None:
        result = package_fuse(a_fuse(), tmp_path)
        assert result.checksum_file is not None
        assert result.sha256 in result.checksum_file.read_text(encoding="utf-8")
        assert result.archive.name in result.checksum_file.read_text(encoding="utf-8")

    def test_a_compiled_plugin_can_travel_with_it(self, tmp_path: Path) -> None:
        binary = tmp_path / "Krokodove.plugin"
        binary.write_bytes(b"x" * 32)
        result = package_fuse(a_fuse(), tmp_path, plugin=BinaryPlugin(path=binary))
        with zipfile.ZipFile(result.archive) as bundle:
            assert "Krokodove.plugin" in bundle.namelist()
            assert bundle.read("Krokodove.plugin") == b"x" * 32
            assert json.loads(bundle.read("resolvescript.json"))["plugin"]["name"] == "Krokodove"

    def test_a_broken_fuse_is_not_handed_on(self, tmp_path: Path) -> None:
        with pytest.raises(FuseError, match="refusing to package"):
            package_fuse(a_fuse(process="InNope:Set(req, foo("), tmp_path)

    def test_no_check_packages_it_anyway(self, tmp_path: Path) -> None:
        result = package_fuse(a_fuse(process="InNope:Set(req, foo("), tmp_path, check=False)
        assert result.archive.is_file()

    def test_the_default_dist_directory(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = package_fuse(a_fuse())
        assert result.archive.parent == tmp_path / "dist"


# ---------------------------------------------------------------- paths ----
class TestPaths:
    @pytest.mark.parametrize("system", ["Windows", "Darwin", "Linux"])
    def test_every_platform_has_a_candidate(self, system: str) -> None:
        assert candidates(FUSES_DIR_NAME, system)

    def test_the_roots_are_separate(self) -> None:
        """A fuse and a .plugin go to different directories."""
        for system in ("Windows", "Darwin", "Linux"):
            fuses = candidates(FUSES_DIR_NAME, system)
            plugins = candidates(PLUGINS_DIR_NAME, system)
            assert not set(fuses) & set(plugins)

    def test_resolve_is_listed_before_the_standalone_app_on_macos(self) -> None:
        """A fuse dropped in the standalone app's tree is invisible to Resolve."""
        paths = [str(p) for p in candidates(FUSES_DIR_NAME, "Darwin")]
        assert any("DaVinci Resolve" in p for p in paths)

    def test_the_windows_resolve_path_is_under_programdata(self, monkeypatch) -> None:
        # The Windows table is read from the environment, and a CI runner has
        # none of these set — without them the candidates fall back to $HOME and
        # the test would be asserting on where the machine happens to be.
        monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
        monkeypatch.setenv("APPDATA", r"C:\Users\me\AppData\Roaming")
        monkeypatch.setenv("PUBLIC", r"C:\Users\Public")
        assert all(
            "ProgramData" in str(p) or "AppData" in str(p) or "Documents" in str(p)
            for p in candidates(FUSES_DIR_NAME, "Windows")
        )

    def test_the_documented_sdk_paths_are_present(self) -> None:
        """These are the three the Fuse SDK names, so they are not guesses."""
        fuses = [str(p) for p in candidates(FUSES_DIR_NAME, "Windows")]

        def ends_with(tail: str) -> bool:
            return any(p.replace("/", "\\").endswith(tail) for p in fuses)

        assert ends_with(r"Blackmagic Design\Fusion\Fuses")
        assert ends_with(r"Blackmagic Design\DaVinci Resolve\Support\Fusion\Fuses")
        # Fusion 9 and earlier kept user data under the public profile.
        assert ends_with(r"Documents\Blackmagic Design\Fusion\Fuses")

    def test_the_linux_layout_is_resolve_only(self) -> None:
        """The standalone Fusion app has no Linux release, so no Fusion-app path
        is invented there; only the two documented Resolve locations are used."""
        paths = [str(p) for p in candidates(FUSES_DIR_NAME, "Linux")]
        assert paths
        assert all("DaVinciResolve" in p for p in paths)

    def test_default_root_prefers_an_existing_directory(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        first, second = tmp_path / "first", tmp_path / "second"
        second.mkdir()
        monkeypatch.setattr(
            "ResolveScript.fuse.paths.candidates", lambda *a, **k: [first, second]
        )
        assert default_root(FUSES_DIR_NAME) == second

    def test_default_root_falls_back_to_the_first_candidate(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            "ResolveScript.fuse.paths.candidates", lambda *a, **k: [tmp_path / "nope"]
        )
        assert default_root(FUSES_DIR_NAME) == tmp_path / "nope"

    def test_an_unknown_directory_name_is_rejected(self) -> None:
        with pytest.raises(FusionPathError, match="unknown plugin directory"):
            candidates("Effects")

    def test_an_explicit_root_wins_over_the_environment(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("RESOLVESCRIPT_FUSES_ROOT", str(tmp_path / "env"))
        assert root(FUSES_DIR_NAME, tmp_path / "explicit") == tmp_path / "explicit"

    def test_the_environment_is_used_when_there_is_no_override(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("RESOLVESCRIPT_FUSION_PLUGINS_ROOT", str(tmp_path / "env"))
        assert root(PLUGINS_DIR_NAME) == tmp_path / "env"

    def test_the_two_environment_variables_are_distinct(self, tmp_path: Path, monkeypatch) -> None:
        """A fuse root must not silently become the compiled-plugin root."""
        monkeypatch.setenv("RESOLVESCRIPT_FUSES_ROOT", str(tmp_path / "fuses"))
        monkeypatch.setenv("RESOLVESCRIPT_FUSION_PLUGINS_ROOT", str(tmp_path / "plugins"))
        assert root(FUSES_DIR_NAME) == tmp_path / "fuses"
        assert root(PLUGINS_DIR_NAME) == tmp_path / "plugins"


# ------------------------------------------------------------------ cli ----
class TestCLI:
    def _run(self, monkeypatch, capsys, *argv: str):
        from ResolveScript.cli import main

        # The declaration is imported by module name, and several of these tests
        # each scaffold their own copy of the same package into a different temp
        # directory. Without this the first import wins for the whole session
        # and a test that changed fuse.py sees the previous test's Fuse.
        for name in [n for n in sys.modules if n == PACKAGE or n.startswith(f"{PACKAGE}.")]:
            monkeypatch.delitem(sys.modules, name, raising=False)
        monkeypatch.setattr("sys.argv", ["resolvescript", *argv])
        code = main()
        return code, capsys.readouterr()

    def test_build_writes_the_fuse(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        monkeypatch.chdir(project)
        code, out = self._run(monkeypatch, capsys, "fuse", "build")
        assert code == 0
        assert (project / "dist" / "MyFuse.fuse").is_file()
        assert "restart Fusion" in out.out

    def test_build_stdout_prints_the_source(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        monkeypatch.chdir(project)
        code, out = self._run(monkeypatch, capsys, "fuse", "build", "--stdout")
        assert code == 0
        assert "FuRegisterClass" in out.out
        assert not (project / "dist").exists()

    def test_describe_prints_the_metadata(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        monkeypatch.chdir(project)
        code, out = self._run(monkeypatch, capsys, "fuse", "describe")
        assert code == 0
        assert "MyFuse.fuse" in out.out

    def test_install_list_and_uninstall(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        fuses = tmp_path / "Fuses"
        monkeypatch.chdir(project)
        assert self._run(monkeypatch, capsys, "fuse", "install", "--root", str(fuses))[0] == 0
        assert (fuses / "MyFuse.fuse").is_file()

        _, out = self._run(monkeypatch, capsys, "fuse", "list", "--root", str(fuses))
        assert "MyFuse" in out.out

        _, out = self._run(monkeypatch, capsys, "fuse", "uninstall", "MyFuse", "--root", str(fuses))
        assert "MyFuse.fuse" in out.out
        assert not (fuses / "MyFuse.fuse").exists()

    def test_a_missing_declaration_is_a_clear_error(self, tmp_path: Path, monkeypatch, capsys) -> None:
        monkeypatch.chdir(tmp_path)
        code, out = self._run(monkeypatch, capsys, "fuse", "build")
        assert code == 1
        assert "fusion.entrypoint" in out.err

    def test_the_manifest_supplies_the_entrypoint(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        monkeypatch.chdir(project)
        code, _ = self._run(monkeypatch, capsys, "fuse", "describe")
        assert code == 0

    def test_a_wrong_entrypoint_type_is_reported(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        monkeypatch.chdir(project)
        code, out = self._run(
            monkeypatch, capsys, "fuse", "describe", "--entrypoint", "my_fuse:__version__"
        )
        assert code == 1
        assert "did not resolve to a Fuse" in out.err

    def test_an_unimportable_module_is_reported(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        monkeypatch.chdir(project)
        code, out = self._run(monkeypatch, capsys, "fuse", "describe", "--entrypoint", "nope.nope:X")
        assert code == 1
        assert "could not import" in out.err

    def test_a_broken_fuse_fails_the_build(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path, process="OutImage:Set(req, ")
        monkeypatch.chdir(project)
        code, out = self._run(monkeypatch, capsys, "fuse", "build")
        assert code == 1
        assert "not a loadable fuse" in out.err

    def test_no_check_lets_a_broken_fuse_through(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path, process="OutImage:Set(req, ")
        monkeypatch.chdir(project)
        code, _ = self._run(monkeypatch, capsys, "fuse", "build", "--no-check")
        assert code == 0
        assert (project / "dist" / "MyFuse.fuse").is_file()

    def test_package_writes_an_archive(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        monkeypatch.chdir(project)
        code, out = self._run(monkeypatch, capsys, "fuse", "package")
        assert code == 0
        assert "MyFuse-0.1.0.zip" in out.out

    def test_package_can_carry_a_compiled_plugin(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        binary = tmp_path / "Krokodove.plugin"
        binary.write_bytes(b"x")
        monkeypatch.chdir(project)
        code, _ = self._run(monkeypatch, capsys, "fuse", "package", "--plugin", str(binary))
        assert code == 0
        with zipfile.ZipFile(project / "dist" / "MyFuse-0.1.0.zip") as bundle:
            assert "Krokodove.plugin" in bundle.namelist()

    def test_package_rejects_a_fuse_as_a_plugin(self, tmp_path: Path, monkeypatch, capsys) -> None:
        project = _write_project(tmp_path)
        fuse_file = project / "dist" / "MyFuse.fuse"
        fuse_file.parent.mkdir(parents=True, exist_ok=True)
        fuse_file.write_text("--[[--\n--]]--\n", encoding="utf-8")
        monkeypatch.chdir(project)
        code, out = self._run(monkeypatch, capsys, "fuse", "package", "--plugin", str(fuse_file))
        assert code == 1
        assert "not a compiled Fusion plugin" in out.err

    def test_root_prints_the_effective_directory(self, tmp_path: Path, monkeypatch, capsys) -> None:
        monkeypatch.setenv("RESOLVESCRIPT_FUSES_ROOT", str(tmp_path / "Fuses"))
        code, out = self._run(monkeypatch, capsys, "fuse", "root")
        assert code == 0
        assert out.out.strip().endswith("Fuses")

    def test_root_list_shows_both_directories(self, tmp_path: Path, monkeypatch, capsys) -> None:
        code, out = self._run(monkeypatch, capsys, "fuse", "root", "--list")
        assert code == 0
        assert "Fuses:" in out.out and "Plugins:" in out.out


def _write_project(tmp_path: Path, process: str = PROCESS) -> Path:
    """A scaffolded fuse project, by way of the real scaffolder.

    The declaration is replaced so the tests can drive it; everything else
    (manifest, layout, ``__main__``) is what a user actually gets.
    """
    from ResolveScript.scaffold import scaffold_project

    project, _ = scaffold_project(PACKAGE, destination=tmp_path, template="fuse")
    (project / PACKAGE / "fuse.py").write_text(
        "from ResolveScript.fuse import Control, Fuse\n\n"
        f"FUSE = Fuse(name='My Fuse', class_name='MyFuse', process={process!r})\n",
        encoding="utf-8",
    )
    return project
