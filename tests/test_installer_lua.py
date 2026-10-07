"""``resolvescript build --installable`` — the draggable Lua installer.

The promise is one file: dropped on Fusion's Console or Workspace it opens an
install window and writes the consolidated script where Resolve looks for it.
Nothing else in the suite exercises the generator, so these tests pin the shape
— window, payload, target path, no tokens left behind — and the failure modes,
because an installer that half-renders is worse than one that refuses to.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

from ResolveScript import cli
from ResolveScript.installer_lua import (
    InstallerTemplateError,
    build_installable_lua,
    render_installer,
)
from ResolveScript.manifest.json_reader import load_manifest


def write_project(root: Path) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("VALUE = 42\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        '{"name": "My Tool", "version": "0.2.0", "package_dir": "pkg",'
        ' "consolidate": {"entry": "pkg/__init__.py"}}',
        encoding="utf-8",
    )


def installer_for(root: Path) -> str:
    manifest = load_manifest(root / "manifest.json")
    return render_installer(manifest, root)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- the CLI contract --------------------------------------------------------


def test_the_cli_writes_the_installer_and_says_how_to_use_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert cli.main(["build", "--installable"]) == 0

    out = capsys.readouterr().out
    assert (tmp_path / "dist" / "My_Tool_installer.lua").is_file()
    assert "Created Lua installer" in out
    assert "Console or Workspace" in out


def test_an_output_without_a_lua_suffix_gets_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "out" / "installer"

    assert cli.main(["build", "--installable", "--output", str(target)]) == 0

    assert (tmp_path / "out" / "installer.lua").is_file()


def test_without_a_manifest_the_build_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli.main(["build", "--installable"]) == 1

    assert "manifest" in capsys.readouterr().err


# --- what the file actually contains ----------------------------------------


def test_the_installer_builds_a_real_window(tmp_path: Path) -> None:
    write_project(tmp_path)
    text = installer_for(tmp_path)

    assert "local ui = fu.UIManager" in text
    assert "bmd.UIDispatcher(ui)" in text
    assert 'ID = "install_btn"' in text
    assert 'ID = "cancel_btn"' in text
    assert 'window_title = "Install My_Tool"' in text


def test_the_payload_is_the_consolidated_script(tmp_path: Path) -> None:
    write_project(tmp_path)
    text = installer_for(tmp_path)

    match = re.search(r"local SCRIPT_B64 = \[===\[\n(.*?)\n\]===\]", text, re.S)
    assert match is not None, "the payload block is missing"
    payload = base64.b64decode(match.group(1)).decode("utf-8")
    assert "VALUE = 42" in payload


def test_the_install_target_comes_from_fusion_not_a_guess(tmp_path: Path) -> None:
    write_project(tmp_path)
    text = installer_for(tmp_path)

    assert 'MapPath("Scripts:' in text
    assert 'target_category = "Scripts/Utility"' in text


def test_the_generated_file_is_plain_ascii_with_no_tokens(tmp_path: Path) -> None:
    write_project(tmp_path)
    text = installer_for(tmp_path)

    text.encode("ascii")  # raises on anything outside the portable subset
    assert "@@" not in text


def test_every_file_is_written_before_the_installer_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert cli.main(["build", "--installable"]) == 0

    installer = tmp_path / "dist" / "My_Tool_installer.lua"
    assert installer.stat().st_size > 0
    # no `.part`/temporary sibling left over from a half-finished write
    assert [p for p in installer.parent.iterdir() if p.suffix != ".lua"] == []


# --- templates ---------------------------------------------------------------


def test_a_project_template_is_picked_up_by_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(tmp_path)
    (tmp_path / "installer.lua.j2").write_text("-- @@SCRIPT_NAME@@ ready\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["build", "--installable"]) == 0

    assert "-- My_Tool ready" in read(tmp_path / "dist" / "My_Tool_installer.lua")


def test_a_missing_template_fails_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert cli.main(["build", "--installable", "--installer-template", "nope.j2"]) == 1

    err = capsys.readouterr().err
    assert "installer template not found" in err


def test_an_unknown_token_fails_instead_of_shipping(tmp_path: Path) -> None:
    write_project(tmp_path)
    manifest = load_manifest(tmp_path / "manifest.json")
    template = tmp_path / "bad.j2"
    template.write_text("-- @@NOPE@@\n", encoding="utf-8")

    with pytest.raises(InstallerTemplateError, match="unsubstituted"):
        render_installer(manifest, tmp_path, installer_template=template)


def test_a_custom_template_wins_over_the_project_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(tmp_path)
    (tmp_path / "installer.lua.j2").write_text("-- project\n", encoding="utf-8")
    explicit = tmp_path / "explicit.j2"
    explicit.write_text("-- explicit\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert (
        cli.main(["build", "--installable", "--installer-template", str(explicit)])
        == 0
    )

    assert "-- explicit" in read(tmp_path / "dist" / "My_Tool_installer.lua")


def test_build_installable_lua_writes_where_it_was_told(tmp_path: Path) -> None:
    write_project(tmp_path)
    manifest = load_manifest(tmp_path / "manifest.json")
    target = tmp_path / "elsewhere" / "installer.lua"

    returned = build_installable_lua(manifest, tmp_path, target)

    assert returned == target
    assert target.is_file()
