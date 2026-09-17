"""Manifest model, readers and validation tests (M1)."""

from __future__ import annotations

import json

import pytest

from ResolveScript.manifest.json_reader import dumps, load_manifest
from ResolveScript.manifest.json_reader import loads as json_loads
from ResolveScript.manifest.model import Manifest, ManifestError
from ResolveScript.manifest.validation import is_valid_semver, validate_manifest, validate_target
from ResolveScript.manifest.xml_reader import loads as xml_loads

KITCHEN_SINK_JSON = {
    "name": "my_extension",
    "version": "0.1.0",
    "author": "You",
    "description": "Rotoscoping helper",
    "python": "rotoscope",
    "compat": {"resolve": ">=18.5", "python": ">=3.10"},
    "package_dir": "src/my_extension",
    "entrypoint": "my_extension.py",
    "id": "io.github.ose.my_extension",
    "release": {"owner": "OseMine", "repo": "my_extension"},
    "targets": ["Comp", "Utility"],
    "scripts_root": "",
    "consolidate": {
        "enabled": True,
        "output": "my_extension.py",
        "entry": "my_extension/__init__.py",
        "exclude": ["tests", "other_module"],
        "no_comment": ["sys", "os"],
    },
    "dependencies": ["pytest"],
    "install": {
        "as_directory": True,
        "include": ["my_extension/**", "manifest.json"],
        "exclude": ["**/__pycache__/**"],
    },
}

KITCHEN_SINK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <name>my_extension</name>
  <id>io.github.ose.my_extension</id>
  <version>0.1.0</version>
  <author>You</author>
  <description>Rotoscoping helper</description>
  <python>rotoscope</python>
  <compat>
    <resolve>&gt;=18.5</resolve>
    <python>&gt;=3.10</python>
  </compat>
  <package_dir>src/my_extension</package_dir>
  <entrypoint>my_extension.py</entrypoint>
  <targets>
    <target>Comp</target>
    <target>Utility</target>
  </targets>
  <consolidate enabled="true" output="my_extension.py">
    <entry>my_extension/__init__.py</entry>
    <exclude>tests</exclude>
    <exclude>other_module</exclude>
    <no_comment>sys</no_comment>
    <no_comment>os</no_comment>
  </consolidate>
  <dependencies>
    <dependency>pytest</dependency>
  </dependencies>
  <install as_directory="true">
    <include>my_extension/**</include>
    <include>manifest.json</include>
    <exclude>**/__pycache__/**</exclude>
  </install>
  <release>
    <owner>OseMine</owner>
    <repo>my_extension</repo>
  </release>
</manifest>
"""


def _assert_kitchen_sink(m: Manifest) -> None:
    assert m.name == "my_extension"
    assert m.version == "0.1.0"
    assert m.author == "You"
    assert m.python == "rotoscope"
    assert m.id == "io.github.ose.my_extension"
    assert m.compat.resolve == ">=18.5"
    assert m.compat.python == ">=3.10"
    assert m.package_dir == "src/my_extension"
    assert m.entrypoint == "my_extension.py"
    assert m.targets == ["Comp", "Utility"]
    assert m.consolidate.output == "my_extension.py"
    assert m.consolidate.entry == "my_extension/__init__.py"
    assert m.consolidate.exclude == ["tests", "other_module"]
    assert m.consolidate.no_comment == ["sys", "os"]
    assert m.dependencies == ["pytest"]
    assert m.install.include == ["my_extension/**", "manifest.json"]
    assert m.release.owner == "OseMine"
    assert m.release.repo == "my_extension"
    assert m.release.github_spec == "github:OseMine/my_extension"
    assert not m.is_plugin


def test_json_loads() -> None:
    _assert_kitchen_sink(json_loads(json.dumps(KITCHEN_SINK_JSON)))


def test_json_round_trip_preserves_fields() -> None:
    parsed = json_loads(json.dumps(KITCHEN_SINK_JSON))
    reread = json_loads(dumps(parsed))
    assert parsed == reread


def test_xml_parity_with_json() -> None:
    _assert_kitchen_sink(xml_loads(KITCHEN_SINK_XML))


def test_xml_round_trip_matches_json_dict() -> None:
    """XML and JSON must normalize to the identical Manifest."""

    def keys(m: Manifest) -> dict:
        return m.to_dict()

    xml_manifest = xml_loads(KITCHEN_SINK_XML)
    json_manifest = json_loads(json.dumps(KITCHEN_SINK_JSON))
    assert keys(xml_manifest) == keys(json_manifest)


def test_minimal_manifest() -> None:
    m = json_loads('{"name": "foo", "version": "0.0.1"}')
    assert m.name == "foo"
    assert m.targets == []
    assert m.default_package_dir == "foo"


def test_plugin_manifest_kind() -> None:
    m = json_loads(
        json.dumps(
            {
                "kind": "extension",
                "name": "resolvescript-lint",
                "version": "1.0.0",
                "release": {"owner": "OseMine", "repo": "resolvescript-lint"},
                "install": {"to": "framework"},
            }
        )
    )
    assert m.is_plugin
    assert m.install.to == "framework"


def test_malformed_json_reports_line(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{\n  \"name\": \"broken\",\n  \n  \"version\": }", encoding="utf-8")
    with pytest.raises(ManifestError) as exc:
        load_manifest(path)
    assert "invalid JSON" in str(exc.value)
    assert "manifest.json" in str(exc.value)
    assert exc.value.line is not None


def test_missing_name_raises() -> None:
    with pytest.raises(ManifestError, match="missing required field 'name'"):
        json_loads('{"version": "1.0.0"}')


def test_wrong_type_raises() -> None:
    with pytest.raises(ManifestError, match="must contain only strings"):
        json_loads('{"name": "x", "version": "1.0.0", "targets": [1, 2]}')


def test_malformed_xml_reports_position() -> None:
    with pytest.raises(ManifestError) as exc:
        xml_loads("<manifest><name>oops</name></manifest")
    assert "invalid XML" in str(exc.value)


def test_xml_wrong_root() -> None:
    with pytest.raises(ManifestError, match="expected a <manifest>"):
        xml_loads("<not_manifest><name>a</name></not_manifest>")


# ---------------------------------------------------------------------------
# Validation


def test_validation_empty_for_kitchen_sink() -> None:
    assert validate_manifest(json_loads(json.dumps(KITCHEN_SINK_JSON))) == []


def test_validation_missing_fields() -> None:
    errors = validate_manifest(Manifest(name="", version=""))
    assert any("name" in e and "missing" in e for e in errors)
    assert any("version" in e and "missing" in e for e in errors)


def test_validation_bad_version() -> None:
    errors = validate_manifest(json_loads('{"name": "x", "version": "v1.0"}'))
    assert any("semver" in e for e in errors)


def test_validation_unknown_target_suggests_fix() -> None:
    error = validate_target("comp")
    assert error is not None
    assert "Comp" in error


def test_validation_output_path_traversal() -> None:
    m = json_loads('{"name": "x", "version": "1.0.0", "targets": ["Comp"],'
                   '"consolidate": {"output": "../../evil.py", "entry": "x/__init__.py"}}')
    errors = validate_manifest(m)
    assert any("consolidate.output" in e for e in errors)


def test_validation_consolidate_entry_required() -> None:
    m = json_loads('{"name": "x", "version": "1.0.0", "targets": ["Comp"],'
                   '"consolidate": {"enabled": true}}')
    errors = validate_manifest(m)
    assert any("consolidate.entry" in e for e in errors)


def test_validation_plugin_needs_source() -> None:
    m = json_loads('{"kind": "extension", "name": "p", "version": "1.0.0"}')
    errors = validate_manifest(m)
    assert any("plugin manifests need a source" in e for e in errors)


@pytest.mark.parametrize(
    "version,expected",
    [
        ("1.2.3", True),
        ("0.0.1", True),
        ("10.20.30-rc1", True),
        ("1.2.3+build.5", True),
        ("v1.2.3", False),
        ("1.2", False),
        ("1.2.3.4", False),
        ("", False),
    ],
)
def test_semver(version: str, expected: bool) -> None:
    assert is_valid_semver(version) is expected
