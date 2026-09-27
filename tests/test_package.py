"""M7: packaging + release artifact tests."""

from __future__ import annotations

import tarfile

import pytest

from ResolveScript.cli import main
from ResolveScript.package import PackageError, _sha256, package_project
from ResolveScript.scaffold import scaffold_project


def test_package_scaffold(tmp_path) -> None:
    scaffold_project("hello", destination=tmp_path)
    root = tmp_path / "hello"
    result = package_project(root)
    assert result.archive.is_file()
    assert result.archive.name.endswith(".tar.gz")
    assert result.sha256
    assert result.checksum_file and result.checksum_file.is_file()
    content = result.checksum_file.read_text(encoding="utf-8")
    assert result.sha256 in content

    with tarfile.open(result.archive) as tf:
        names = tf.getnames()
    assert "manifest.json" in names
    assert "hello_main.py" in names
    assert "hello/__init__.py" in names
    assert "hello/menu.py" in names


def test_package_dist_override(tmp_path) -> None:
    scaffold_project("hello", destination=tmp_path)
    root = tmp_path / "hello"
    custom = tmp_path / "release"
    result = package_project(root, custom)
    assert result.archive.parent == custom


def test_package_missing_manifest(tmp_path) -> None:
    with pytest.raises(PackageError, match="no manifest"):
        package_project(tmp_path)


def test_package_checksum_integrity(tmp_path) -> None:
    scaffold_project("hello", destination=tmp_path)
    root = tmp_path / "hello"
    result = package_project(root)
    actual = _sha256(result.archive)
    assert actual == result.sha256


def test_cli_package(tmp_path, monkeypatch, capsys) -> None:
    scaffold_project("hello", destination=tmp_path)
    monkeypatch.chdir(tmp_path / "hello")
    assert main(["package"]) == 0
    out = capsys.readouterr().out
    assert "hello-0.1.0.tar.gz" in out
    assert "SHA-256" in out


def test_cli_package_no_manifest(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["package"]) == 1
    assert "no manifest" in capsys.readouterr().err
