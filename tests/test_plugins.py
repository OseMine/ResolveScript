"""Framework extension (plugin) lifecycle, isolation and CLI tests (M5c)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ResolveScript import cli
from ResolveScript.install.installer import InstallError, InstallOptions, install_package
from ResolveScript.manifest import load_manifest
from ResolveScript.manifest.model import RequiresConfig
from ResolveScript.plugins import (
    PluginEntry,
    PluginError,
    PluginManifest,
    PluginRegistry,
    _get_config_dir,
    install_plugin,
    list_plugins,
    uninstall_plugin,
)

EXAMPLE_LINT = Path(__file__).resolve().parents[1] / "examples" / "resolvescript-lint"

_ENTRY_SOURCE = (
    "def register_commands(parser):\n"
    "    sub = parser.add_parser('demo-cmd', help='demo')\n"
    "    sub.set_defaults(func=lambda args: 0)\n"
)


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the plugin registry at a throwaway CLI config directory."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("RESOLVESCRIPT_CONFIG_DIR", str(cfg))
    return cfg


def _extension_pkg(
    root: Path,
    *,
    kind: str = "extension",
    name: str = "demo-plugin",
    commands: list[str] | None = None,
    requires: dict[str, str] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "demo_entry.py").write_text(_ENTRY_SOURCE, encoding="utf-8")
    manifest: dict = {
        "name": name,
        "version": "1.0.0",
        "entrypoint": "demo_entry.py",
        "consolidate": {"enabled": False},
    }
    if kind == "extension":
        manifest["kind"] = "extension"
        manifest["install"] = {"to": "framework"}
        manifest["release"] = {"owner": "example", "repo": name}
        extension: dict = {
            "extension_kind": "commands",
            "commands": commands if commands is not None else ["demo-cmd"],
        }
        if requires:
            extension["requires"] = requires
        manifest["extension"] = extension
    else:
        manifest["targets"] = ["Comp"]
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _plugin_json_pkg(root: Path, changes: dict | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "demo_entry.py").write_text(_ENTRY_SOURCE, encoding="utf-8")
    plugin: dict = {
        "name": "demo-plugin",
        "version": "1.0.0",
        "kind": "extension",
        "entry": "demo_entry.py",
        "commands": ["demo-cmd"],
    }
    plugin.update(changes or {})
    (root / "plugin.json").write_text(json.dumps(plugin), encoding="utf-8")
    return root


def _register_fake_entry(
    config_dir: Path,
    *,
    name: str = "ghost",
    entry: str = "ghost_mod.py",
    commands: list[str] | None = None,
    requires: RequiresConfig | None = None,
) -> PluginEntry:
    plugin_dir = config_dir / "plugins" / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = PluginManifest(
        name=name,
        version="1.0.0",
        extension_kind="commands",
        commands=commands or ["ghost-cmd"],
        requires=requires or RequiresConfig(),
        entry=entry,
    )
    plugin_entry = PluginEntry(
        name=name,
        version="1.0.0",
        path=str(plugin_dir),
        manifest=manifest,
        installed_at="2026-01-01T00:00:00+00:00",
    )
    PluginRegistry(config_dir).register(plugin_entry)
    return plugin_entry


# --- config dir / library API -------------------------------------------------


def test_config_dir_env_override(config_dir: Path) -> None:
    assert _get_config_dir() == config_dir


def test_install_plugin_json_package(config_dir: Path, tmp_path: Path) -> None:
    pkg = _plugin_json_pkg(tmp_path / "pkg")
    entry = install_plugin(pkg, source="file:demo", integrity="abc123")
    assert entry.name == "demo-plugin"
    assert Path(entry.path).is_dir()
    assert (Path(entry.path) / "demo_entry.py").is_file()
    installed = list_plugins()
    assert [p.name for p in installed] == ["demo-plugin"]
    assert installed[0].source == "file:demo"
    assert installed[0].integrity == "abc123"
    # registry round-trips on disk
    assert PluginRegistry(config_dir).get("demo-plugin") is not None


@pytest.mark.parametrize(
    ("changes", "needle"),
    [
        ({"name": ""}, "missing required 'name'"),
        ({"version": ""}, "missing required 'version'"),
        ({"entry": ""}, "missing required 'entry'"),
        ({"kind": "script"}, "only 'extension' kind"),
    ],
)
def test_install_plugin_json_requires_fields(
    config_dir: Path, tmp_path: Path, changes: dict, needle: str
) -> None:
    pkg = _plugin_json_pkg(tmp_path / "pkg", changes)
    with pytest.raises(PluginError, match=needle):
        install_plugin(pkg)


def test_install_rejects_resolve_script(config_dir: Path, tmp_path: Path) -> None:
    pkg = _extension_pkg(tmp_path / "pkg", kind="script")
    with pytest.raises(PluginError, match="resolvescript add"):
        install_plugin(pkg)


def test_install_from_extension_manifest(config_dir: Path, tmp_path: Path) -> None:
    pkg = _extension_pkg(tmp_path / "pkg", commands=["demo-cmd", "extra"])
    entry = install_plugin(pkg)
    assert entry.manifest.entry == "demo_entry.py"
    assert entry.manifest.commands == ["demo-cmd", "extra"]
    assert entry.manifest.requires.resolvescript == ""


def test_version_gate_rejects_incompatible(config_dir: Path, tmp_path: Path) -> None:
    pkg = _extension_pkg(tmp_path / "pkg", requires={"resolvescript": ">=99.0"})
    with pytest.raises(PluginError, match="requires resolvescript"):
        install_plugin(pkg)


def test_force_reinstall(config_dir: Path, tmp_path: Path) -> None:
    pkg = _extension_pkg(tmp_path / "pkg")
    install_plugin(pkg)
    with pytest.raises(PluginError, match="already installed"):
        install_plugin(pkg)
    assert install_plugin(pkg, force=True).name == "demo-plugin"


def test_uninstall(config_dir: Path, tmp_path: Path) -> None:
    pkg = _extension_pkg(tmp_path / "pkg")
    install_plugin(pkg)
    assert uninstall_plugin("demo-plugin") is True
    assert list_plugins() == []
    assert uninstall_plugin("demo-plugin") is False


def test_corrupt_registry_reports(config_dir: Path) -> None:
    (config_dir / "plugins.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PluginError, match="corrupt plugin registry"):
        list_plugins()


def test_install_package_rejects_framework_extension(tmp_path: Path) -> None:
    """A plugin must never be installable into a Resolve Scripts root."""
    pkg = _extension_pkg(tmp_path / "pkg")
    manifest = load_manifest(pkg / "manifest.json")
    with pytest.raises(InstallError, match="extensions add"):
        install_package(pkg, manifest, InstallOptions(scripts_root=tmp_path / "root"))


# --- CLI: extensions add / remove / list -------------------------------------


def test_extensions_cli_add_list_remove(
    config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _extension_pkg(tmp_path / "pkg")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["extensions", "add", "./pkg"]) == 0
    out = capsys.readouterr().out
    assert "installed demo-plugin 1.0.0" in out
    assert "commands: demo-cmd" in out

    assert cli.main(["extensions", "list"]) == 0
    assert "demo-plugin" in capsys.readouterr().out

    assert cli.main(["extensions", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["name"] == "demo-plugin"
    assert payload[0]["manifest"]["commands"] == ["demo-cmd"]

    assert cli.main(["extensions", "remove", "demo-plugin"]) == 0
    assert cli.main(["extensions", "list"]) == 0
    assert "no framework extensions installed" in capsys.readouterr().out

    assert cli.main(["extensions", "remove", "demo-plugin"]) == 1
    assert "not installed" in capsys.readouterr().err


def test_extensions_add_rejects_resolve_script(
    config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _extension_pkg(tmp_path / "pkg", kind="script")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["extensions", "add", "./pkg"]) == 1
    err = capsys.readouterr().err
    assert "resolvescript add" in err
    assert "framework extension" in err


def test_extensions_add_from_plugin_json_dir(
    config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A §4.5-style directory carrying only plugin.json installs directly."""
    _plugin_json_pkg(tmp_path / "plug")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["extensions", "add", "./plug"]) == 0
    assert "installed demo-plugin" in capsys.readouterr().out


def test_extensions_add_missing_spec(
    config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["extensions", "add", "./nope"]) == 1
    assert "manifest.json" in capsys.readouterr().err


# --- startup registration and failure isolation ------------------------------


def test_plugin_missing_module_is_isolated(
    config_dir: Path, capsys: pytest.CaptureFixture
) -> None:
    _register_fake_entry(config_dir)
    assert cli.main(["extensions", "list"]) == 0  # CLI keeps working
    err = capsys.readouterr().err
    assert "skipping plugin 'ghost'" in err


def test_plugin_missing_register_hook_warns(
    config_dir: Path, capsys: pytest.CaptureFixture
) -> None:
    plugin_dir = config_dir / "plugins" / "nohook"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "nohook_mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    _register_fake_entry(config_dir, name="nohook", entry="nohook_mod.py")
    assert cli.main(["extensions", "list"]) == 0
    err = capsys.readouterr().err
    assert "skipping plugin 'nohook'" in err
    assert "no register_commands" in err


def test_version_gate_skips_plugin_at_startup(
    config_dir: Path, capsys: pytest.CaptureFixture
) -> None:
    _register_fake_entry(
        config_dir,
        name="future",
        requires=RequiresConfig(resolvescript=">=99.0"),
    )
    assert cli.main(["extensions", "list"]) == 0
    err = capsys.readouterr().err
    assert "skipping plugin 'future'" in err
    assert "requires resolvescript" in err


def test_broken_registry_does_not_crash_cli(
    config_dir: Path, capsys: pytest.CaptureFixture
) -> None:
    (config_dir / "plugins.json").write_text("{bad", encoding="utf-8")
    # build_parser isolates the registry failure; 'extensions list' reports it
    assert cli.main(["extensions", "list"]) == 1
    err = capsys.readouterr().err
    assert "plugin registry unavailable" in err
    assert "corrupt plugin registry" in err


# --- first-party example plugin (e2e acceptance) -----------------------------


def test_example_plugin_end_to_end(
    config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli.main(["extensions", "add", str(EXAMPLE_LINT)]) == 0
    out = capsys.readouterr().out
    assert "installed resolvescript-lint 1.0.0" in out
    assert "commands: analyze-extra" in out

    # the contributed command is registered at CLI startup and dispatches
    assert cli.main(["analyze-extra"]) == 0
    assert "analyze-extra: 0 issues" in capsys.readouterr().out

    # ... and shows up in --help
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    assert "analyze-extra" in capsys.readouterr().out

    assert cli.main(["extensions", "remove", "resolvescript-lint"]) == 0
    assert cli.main(["extensions", "list"]) == 0
    assert "no framework extensions installed" in capsys.readouterr().out
