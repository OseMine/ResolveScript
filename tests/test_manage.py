"""Tests for the manage subcommands (M8)."""

from __future__ import annotations

import tarfile
from pathlib import Path

from ResolveScript.cli import main
from ResolveScript.install.registry import get_extension, read_registry


def _tar(package_root: Path, dest: Path) -> Path:
    with tarfile.open(dest, "w:gz") as tf:
        tf.add(package_root, arcname=package_root.name)
    return dest


def test_manage_remove_all(tmp_path, monkeypatch) -> None:
    pkg_dir = tmp_path / "src" / "widget"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "widget.py").write_text("def run(): pass\n", encoding="utf-8")
    (pkg_dir / "manifest.json").write_text(
        '{"name":"widget","version":"1.0.0","compat":{"resolve":"18"}}',
        encoding="utf-8",
    )
    archive = _tar(pkg_dir, tmp_path / "widget.tar.gz")
    scripts = tmp_path / "Scripts"
    monkeypatch.chdir(tmp_path)

    code = main(["add", f"file:{archive}", "--scripts-root", str(scripts)])
    assert code == 0
    assert (scripts / "Comp" / "widget").is_dir()

    code = main(["manage", "remove", "widget", "--all", "--scripts-root", str(scripts)])
    assert code == 0
    assert not (scripts / "Comp" / "widget").exists()
    assert get_extension(read_registry(scripts), "widget") is None


def test_manage_remove_without_all_keeps_registry(tmp_path, monkeypatch) -> None:
    pkg_dir = tmp_path / "src" / "widget"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "widget.py").write_text("def run(): pass\n", encoding="utf-8")
    (pkg_dir / "manifest.json").write_text(
        '{"name":"widget","version":"1.0.0","compat":{"resolve":"18"}}',
        encoding="utf-8",
    )
    archive = _tar(pkg_dir, tmp_path / "widget.tar.gz")
    scripts = tmp_path / "Scripts"
    monkeypatch.chdir(tmp_path)

    code = main(["add", f"file:{archive}", "--scripts-root", str(scripts)])
    assert code == 0
    entry = get_extension(read_registry(scripts), "widget")
    assert entry

    code = main(["manage", "remove", "widget", "--scripts-root", str(scripts)])
    assert code == 0
    assert not (scripts / "Comp" / "widget").exists()
    assert get_extension(read_registry(scripts), "widget") is not None
