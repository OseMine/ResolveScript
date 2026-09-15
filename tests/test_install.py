"""Installer tests (M5): discovery, registry, atomic install, uninstall, CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from resolve_script.cli import main
from resolve_script.install.discovery import (
    default_scripts_root,
    resolve_scripts_root,
    target_dir,
)
from resolve_script.install.installer import (
    InstallError,
    InstallOptions,
    discover_entrypoint,
    install_package,
    install_project,
    select_files,
    uninstall_package,
)
from resolve_script.install.registry import (
    add_or_update_entry,
    get_extension,
    read_registry,
    remove_entry,
)
from resolve_script.manifest.json_reader import load_manifest
from resolve_script.manifest.model import ManifestError
from resolve_script.scaffold import scaffold_project


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------
def test_default_scripts_root_windows(monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", r"C:\Users\me\AppData\Roaming")
    monkeypatch.setattr("resolve_script.install.discovery.platform.system", lambda: "Windows")
    assert default_scripts_root() == Path(
        r"C:\Users\me\AppData\Roaming\Blackmagic Design\DaVinci Resolve\Fusion\Scripts"
    )


def test_default_scripts_root_macos(monkeypatch) -> None:
    monkeypatch.setattr("resolve_script.install.discovery.platform.system", lambda: "Darwin")
    root = default_scripts_root()
    assert "DaVinci Resolve" in str(root) and root.name == "Scripts"


def test_default_scripts_root_linux(monkeypatch) -> None:
    monkeypatch.setattr("resolve_script.install.discovery.platform.system", lambda: "Linux")
    root = default_scripts_root()
    assert root.name == "Scripts"
    assert "DaVinci Resolve" in str(root)


def test_resolve_scripts_root_override_priority(monkeypatch, tmp_path) -> None:
    explicit = tmp_path / "explicit"
    env_value = tmp_path / "env"
    monkeypatch.setenv("RESOLVESCRIPT_SCRIPTS_ROOT", str(env_value))
    assert resolve_scripts_root(explicit) == explicit
    assert resolve_scripts_root() == env_value
    monkeypatch.delenv("RESOLVESCRIPT_SCRIPTS_ROOT")
    assert resolve_scripts_root() == default_scripts_root()


def test_target_dir_validation(tmp_path) -> None:
    assert target_dir(tmp_path, "Comp") == tmp_path / "Comp"
    assert target_dir(tmp_path, "root") == tmp_path
    with pytest.raises(ManifestError, match="unknown script target"):
        target_dir(tmp_path, "comp")
    with pytest.raises(ManifestError, match="did you mean 'Utility'"):
        target_dir(tmp_path, "utility")


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
def test_registry_empty_default(tmp_path) -> None:
    assert read_registry(tmp_path) == {"schema_version": 1, "extensions": {}}


def test_registry_roundtrip(tmp_path) -> None:
    add_or_update_entry(
        tmp_path,
        "demo",
        {"id": "demo", "name": "demo", "version": "1.0.0", "files": ["a.py"], "targets": ["Comp"]},
    )
    loaded = read_registry(tmp_path)
    assert loaded["extensions"]["demo"]["version"] == "1.0.0"
    assert get_extension(loaded, "demo")["name"] == "demo"
    assert get_extension(loaded, "demo")["id"] == "demo"
    assert get_extension(loaded, "missing") is None

    assert remove_entry(tmp_path, "demo") is not None
    assert remove_entry(tmp_path, "demo") is None
    assert "demo" not in read_registry(tmp_path)["extensions"]


def test_registry_corrupt_raises(tmp_path) -> None:
    path = tmp_path / ".resolvescript" / "install.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(Exception, match="corrupt"):
        read_registry(tmp_path)


# ---------------------------------------------------------------------------
# file selection & entrypoint
# ---------------------------------------------------------------------------
def test_select_files_with_include_exclude(tmp_path) -> None:
    for rel in ["pkg/__init__.py", "pkg/core.py", "manifest.json", "pkg/__pycache__/x.pyc"]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# x\n", encoding="utf-8")
    selected = select_files(tmp_path, include=["pkg/**", "manifest.json"], exclude=["**/__pycache__/**"])
    rels = {r.as_posix() for r in selected}
    assert rels == {"pkg/__init__.py", "pkg/core.py", "manifest.json"}


def test_select_files_default_skips_caches(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\x00")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("", encoding="utf-8")
    rels = [r.as_posix() for r in select_files(tmp_path)]
    assert rels == ["a.py"]


def test_discover_entrypoint_priority(tmp_path) -> None:
    pkg = tmp_path / "demo"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("__version__ = '0.1.0'\n", encoding="utf-8")

    # 1. explicit entrypoint field wins
    manifest = load_manifest(_write_manifest(tmp_path, {"entrypoint": "start.py"}))
    (tmp_path / "start.py").write_text("# hello\n", encoding="utf-8")
    assert discover_entrypoint(tmp_path, manifest).name == "start.py"

    # 2. root <name>.py next
    manifest = load_manifest(_write_manifest(tmp_path, {}))
    (tmp_path / "demo.py").write_text("# hello\n", encoding="utf-8")
    assert discover_entrypoint(tmp_path, manifest).name == "demo.py"

    # 3. remove root file so dist fallback wins
    (tmp_path / "demo.py").unlink()
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "demo.py").write_text("# built\n", encoding="utf-8")
    manifest = load_manifest(
        _write_manifest(tmp_path, {"consolidate": {"enabled": True, "output": "demo.py"}})
    )
    entry = discover_entrypoint(tmp_path, manifest)
    assert entry.name == "demo.py"
    assert entry.parent.name == "dist"


# ---------------------------------------------------------------------------
# install / uninstall
# ---------------------------------------------------------------------------
@pytest.fixture
def scripts_root(tmp_path):
    return tmp_path / "Scripts"


def _write_manifest(root: Path, overrides: dict) -> Path:
    raw = {
        "name": "demo",
        "version": "0.1.0",
        "targets": ["Comp", "Utility"],
        "python": "demo",
        "consolidate": {"enabled": True, "output": "demo.py"},
        "install": {"as_directory": True, "include": ["demo/**", "demo.py", "manifest.json"]},
    }
    raw.update(overrides)
    path = root / "manifest.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _install_demo(scripts_root: Path, source: Path, manifest=None) -> None:
    manifest = manifest or load_manifest(source / "manifest.json")
    install_package(source, manifest, InstallOptions(scripts_root=scripts_root))


def test_install_project_directory_layout(tmp_path, scripts_root) -> None:
    project = tmp_path / "demo"
    scaffold_project("demo", destination=tmp_path)
    result = install_project(project, InstallOptions(scripts_root=scripts_root))

    target = scripts_root / "Comp" / "demo"
    assert (target / "manifest.json").is_file()
    assert (target / "demo.py").is_file()
    assert (target / "demo" / "__init__.py").is_file()
    assert result.container == target

    registry = read_registry(scripts_root)
    entry = registry["extensions"]["demo"]
    assert entry["name"] == "demo"
    assert entry["targets"] == ["Comp", "Utility"]
    assert "demo/demo/__init__.py" in entry["files"]
    assert not (scripts_root / "Comp" / "demo" / "demo.pyc").exists()
    assert entry["installed_at"]
    assert entry["integrity"]


def test_install_single_file_layout(tmp_path, scripts_root) -> None:
    source = tmp_path / "single"
    source.mkdir()
    (source / "single.py").write_text("def run():\n    return True\n", encoding="utf-8")
    manifest_path = _write_manifest(source, {"name": "single", "install": {"as_directory": False}})
    _install_demo(scripts_root, source, load_manifest(manifest_path))

    assert (scripts_root / "Comp" / "single.py").is_file()
    assert not (scripts_root / "Comp" / "single").exists()
    entry = read_registry(scripts_root)["extensions"]["single"]
    assert entry["as_directory"] is False
    assert entry["files"] == ["single.py"]


def test_install_rejects_bad_syntax_atomically(tmp_path, scripts_root) -> None:
    source = tmp_path / "demo"
    scaffold_project("demo", destination=tmp_path)
    (source / "demo.py").write_text("def run(:\n", encoding="utf-8")

    with pytest.raises(InstallError, match="not valid Python"):
        install_project(source, InstallOptions(scripts_root=scripts_root))

    assert not (scripts_root / "Comp" / "demo").exists()
    assert any(p.name.startswith(".resolvescript-stage-") for p in scripts_root.rglob("*")) is False
    assert read_registry(scripts_root)["extensions"] == {}


def test_install_replaces_previous_version(tmp_path, scripts_root) -> None:
    source = tmp_path / "demo"
    scaffold_project("demo", destination=tmp_path)
    manifest = load_manifest(source / "manifest.json")
    _install_demo(scripts_root, source, manifest)
    (source / "demo" / "__init__.py").write_text("__version__ = '0.2.0'\n__all__ = []\n", encoding="utf-8")

    _install_demo(scripts_root, source)
    entry = read_registry(scripts_root)["extensions"]["demo"]
    assert entry["version"] == "0.1.0"  # version string comes from the manifest
    assert (scripts_root / "Comp" / "demo" / "demo" / "__init__.py").read_text().startswith("__version__")


def test_install_conflict_detected_and_forced(tmp_path, scripts_root) -> None:
    a = tmp_path / "a"
    a.mkdir()
    (a / "a.py").write_text("x = 1\n", encoding="utf-8")
    (a / "manifest.json").write_text(
        json.dumps({"name": "a", "version": "1", "install": {"as_directory": False}}),
        encoding="utf-8",
    )
    _install_demo(scripts_root, a, load_manifest(a / "manifest.json"))

    b = tmp_path / "b"
    b.mkdir()
    (b / "a.py").write_text("y = 2\n", encoding="utf-8")
    (b / "manifest.json").write_text(
        json.dumps(
            {"name": "b", "version": "1", "entrypoint": "a.py", "install": {"as_directory": False}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(InstallError, match="owned by 'a'"):
        install_package(b, load_manifest(b / "manifest.json"), InstallOptions(scripts_root=scripts_root))

    result = install_package(
        b, load_manifest(b / "manifest.json"), InstallOptions(scripts_root=scripts_root, force=True)
    )
    assert result.container == scripts_root / "Comp"
    assert (scripts_root / "Comp" / "a.py").read_text() == "y = 2\n"


def test_uninstall_removes_files_and_entry(tmp_path, scripts_root) -> None:
    project = tmp_path / "demo"
    scaffold_project("demo", destination=tmp_path)
    install_project(project, InstallOptions(scripts_root=scripts_root))

    other = tmp_path / "other"
    scaffold_project("other", destination=tmp_path)
    install_project(other, InstallOptions(scripts_root=scripts_root))

    removed = uninstall_package("demo", InstallOptions(scripts_root=scripts_root))
    assert removed
    assert not (scripts_root / "Comp" / "demo").exists()
    assert (scripts_root / "Comp" / "other").exists()
    assert "demo" not in read_registry(scripts_root)["extensions"]

    with pytest.raises(InstallError, match="not installed"):
        uninstall_package("demo", InstallOptions(scripts_root=scripts_root))


def test_install_dry_run_writes_nothing(tmp_path, scripts_root, capsys) -> None:
    project = tmp_path / "demo"
    scaffold_project("demo", destination=tmp_path)
    result = install_project(project, InstallOptions(scripts_root=scripts_root, dry_run=True))
    assert result.dry_run
    assert not (scripts_root / "Comp").exists()
    assert read_registry(scripts_root)["extensions"] == {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_install_author_flow(tmp_path, monkeypatch, capsys) -> None:
    project = tmp_path / "demo"
    scaffold_project("demo", destination=tmp_path)
    monkeypatch.chdir(project)
    assert main(["install", "--scripts-root", str(tmp_path / "Scripts")]) == 0
    out = capsys.readouterr().out
    assert "Installed demo 0.1.0" in out
    assert (tmp_path / "Scripts" / "Utility" / "demo" / "demo" / "menu.py").is_file()


def test_cli_install_dry_run(tmp_path, monkeypatch, capsys) -> None:
    project = tmp_path / "demo"
    scaffold_project("demo", destination=tmp_path)
    monkeypatch.chdir(project)
    assert main(["install", "--scripts-root", str(tmp_path / "Scripts"), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "(dry run" in out
    assert not (tmp_path / "Scripts").exists()


def test_cli_install_requires_context(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["install", "--scripts-root", str(tmp_path / "Scripts")]) == 2
    assert "nothing to install" in capsys.readouterr().err


def test_cli_remove_flow(tmp_path, monkeypatch, capsys) -> None:
    project = tmp_path / "demo"
    scaffold_project("demo", destination=tmp_path)
    monkeypatch.chdir(project)
    assert main(["install", "--scripts-root", str(tmp_path / "Scripts")]) == 0
    capsys.readouterr()
    assert main(["remove", "demo", "--scripts-root", str(tmp_path / "Scripts")]) == 0
    out = capsys.readouterr().out
    assert "removed" in out
    assert not (tmp_path / "Scripts" / "Comp" / "demo").exists()


def test_cli_remove_missing(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["remove", "ghost", "--scripts-root", str(tmp_path / "Scripts")]) == 1
    assert "not installed" in capsys.readouterr().err
