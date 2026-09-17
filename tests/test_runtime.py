"""M5b: specifier parsing, semver, resolver, workspace, and consumer CLI flows."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from ResolveScript.resolver import ResolveError, lockfile_satisfies, resolve_spec
from ResolveScript.semver import SemVerError, Version, matches, pick_best
from ResolveScript.spec import SpecError, parse_specifier
from ResolveScript.workspace import add_dependency, read_workspace, remove_dependency


def _write_package(path: Path, name: str, version: str = "1.2.3") -> Path:
    root = path / name
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.py").write_text("def run():\n    return True\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "python": "3.7",
                "compat": {"resolve": "18"},
            }
        ),
        encoding="utf-8",
    )
    return root


def _tar(package_root: Path, dest: Path) -> Path:
    with tarfile.open(dest, "w:gz") as tf:
        tf.add(package_root, arcname=package_root.name)
    return dest


# --------------------------------------------------------------------------
# specifier parsing
# --------------------------------------------------------------------------
def test_parse_bare_name() -> None:
    spec = parse_specifier("hello")
    assert spec.kind == "name"
    assert spec.source == "hello"


def test_parse_owner_repo() -> None:
    spec = parse_specifier("OseMine/tools")
    assert spec.kind == "github"
    assert spec.owner == "OseMine"
    assert spec.repo == "tools"
    assert spec.source == "github:OseMine/tools"


def test_parse_github_semver(tmp_path) -> None:
    spec = parse_specifier("gh:a/b#semver:>=1.0", cwd=tmp_path)
    assert spec.kind == "github"
    assert spec.range_text == ">=1.0"
    assert spec.source == "github:a/b#semver:>=1.0"


def test_parse_github_ref(tmp_path) -> None:
    spec = parse_specifier("github:a/b#main", cwd=tmp_path)
    assert spec.ref == "main"


def test_parse_relative_dir(tmp_path) -> None:
    assert parse_specifier("./pkg", cwd=tmp_path).kind == "path"
    assert parse_specifier("../other", cwd=tmp_path).kind == "path"


def test_parse_archive_url() -> None:
    assert parse_specifier("https://x.example/a.tar.gz").kind == "archive"
    assert parse_specifier("https://x.example/a.zip", cwd=Path.cwd()).kind == "archive"


def test_parse_manifest_url() -> None:
    assert parse_specifier("https://x.example/manifest.json").kind == "manifest"


def test_parse_file_dir(tmp_path) -> None:
    spec = parse_specifier(f"file:{tmp_path / 'pkg'}", cwd=tmp_path)
    assert spec.kind == "path"
    assert spec.location == (tmp_path / "pkg").resolve()


def test_parse_invalid_github(tmp_path) -> None:
    with pytest.raises(SpecError):
        parse_specifier("github:a/b/c", cwd=tmp_path)


def test_release_asset_url() -> None:
    from ResolveScript.sources.release import ReleaseSpec, asset_download_url

    assert (
        asset_download_url(ReleaseSpec(url="https://x.example/a.tgz"), "a", "1.0")
        == "https://x.example/a.tgz"
    )
    assert (
        asset_download_url(ReleaseSpec(owner="OseMine", repo="a"), "a", "1.0.0")
        == "https://github.com/OseMine/a/releases/latest/download/a-1.0.0.tgz"
    )
    assert (
        asset_download_url(
            ReleaseSpec(owner="OseMine", repo="a", asset="a-linux.zip", tag="v1.0"),
            "a",
            "1.0.0",
        )
        == "https://github.com/OseMine/a/releases/download/v1.0/a-linux.zip"
    )


# --------------------------------------------------------------------------
# semver
# --------------------------------------------------------------------------
def test_semver_parse() -> None:
    v = Version.parse("1.2.3")
    assert (v.major, v.minor, v.patch) == (1, 2, 3)
    pre = Version.parse("1.2.3-rc.1")
    assert pre.prerelease == "rc.1"
    with pytest.raises(SemVerError):
        Version.parse("nope")


def test_semver_ordering() -> None:
    assert Version.parse("2.0.0") > Version.parse("1.9.9")
    assert Version.parse("1.0.0-rc.1") < Version.parse("1.0.0")
    assert Version.parse("1.0.0-rc.1") < Version.parse("1.0.0-rc.2")


def test_semver_ranges() -> None:
    assert matches(Version.parse("1.4.0"), ">=1.0 <2.0")
    assert matches(Version.parse("1.4.0"), "^1.2.3")
    assert not matches(Version.parse("2.0.0"), "^1.2.3")
    assert matches(Version.parse("1.2.7"), "~1.2.3")
    assert not matches(Version.parse("1.3.0"), "~1.2.3")
    assert matches(Version.parse("1.5.0"), "1.x")
    assert matches(Version.parse("1.5.0"), "*")
    assert matches(Version.parse("2.3.4"), ">=2.0.0 <=3.0.0")
    assert not matches(Version.parse("1.0.0"), ">=2.0.0")
    assert matches(Version.parse("1.2.3"), "1.2.3")


def test_pick_best() -> None:
    tags = ["1.0.0", "2.1.0", "2.2.0-rc.1", "1.5.0"]
    assert pick_best(tags) == "2.2.0-rc.1"
    assert pick_best(tags, "~1") == "1.5.0"
    assert pick_best(tags, "~1.0") == "1.0.0"
    assert pick_best(tags, "^1.2") == "1.5.0"


# --------------------------------------------------------------------------
# resolver: hermetic path / archive sources
# --------------------------------------------------------------------------
def test_resolve_path_source(tmp_path) -> None:
    pkg = _write_package(tmp_path, "widget")
    resolved = resolve_spec(f"file:{pkg}", cwd=tmp_path, work_dir=tmp_path / "work")
    assert resolved.name == "widget"
    assert resolved.version == "1.2.3"
    assert resolved.kind == "path"
    assert resolved.integrity == ""
    assert resolved.package_dir == pkg


def test_resolve_relative_path_source(tmp_path, monkeypatch) -> None:
    _write_package(tmp_path / "proj", "widget")
    monkeypatch.chdir(tmp_path / "proj")
    resolved = resolve_spec("./widget", cwd=tmp_path / "proj", work_dir=tmp_path / "proj" / "work")
    assert resolved.name == "widget"


def test_resolve_archive_source(tmp_path) -> None:
    pkg = _write_package(tmp_path / "src", "gadget")
    archive = _tar(pkg, tmp_path / "gadget-1.2.3.tar.gz")
    resolved = resolve_spec(f"file:{archive}", cwd=tmp_path, work_dir=tmp_path / "work")
    assert resolved.name == "gadget"
    assert resolved.kind == "archive"
    assert len(resolved.integrity) == 64
    assert (resolved.package_dir / "manifest.json").is_file()


def test_resolve_unknown_name(tmp_path) -> None:
    with pytest.raises(ResolveError, match="unknown extension"):
        resolve_spec("definitely-not-real", cwd=tmp_path, work_dir=tmp_path / "work")


def test_resolve_github_semver(tmp_path, monkeypatch) -> None:
    from ResolveScript.fetch import Fetched, sha256_file
    from ResolveScript.sources import git

    pkg = _write_package(tmp_path / "src", "gizmo", "1.2.0")
    archive = _tar(pkg, tmp_path / "gizmo-1.2.0.tar.gz")
    archive_bytes = archive.read_bytes()

    requests: list[str] = []

    def fake_fetch_json(url, timeout=45.0):
        if "tags" in url:
            return [{"name": "v1.0.0"}, {"name": "v1.2.0"}]
        return {"default_branch": "main"}

    def fake_fetch(url, *, dest, expected_sha256=None, timeout=45.0):
        requests.append(url)
        dest.write_bytes(archive_bytes)
        return Fetched(
            path=dest, sha256=sha256_file(dest), size=len(archive_bytes), url=url
        )

    monkeypatch.setattr(git, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(git, "fetch", fake_fetch)

    resolved = resolve_spec(
        "github:a/b#semver:>=1.0 <1.3",
        cwd=tmp_path,
        work_dir=tmp_path / "work",
    )
    assert resolved.name == "gizmo"
    assert resolved.version == "1.2.0"
    assert resolved.kind == "github"
    assert len(resolved.integrity) == 64
    assert requests and "/tar.gz/v1.2.0" in requests[0]
    assert resolved.source == "github:a/b#semver:>=1.0 <1.3"


def test_resolve_github_precise_ref(tmp_path, monkeypatch) -> None:
    from ResolveScript.fetch import Fetched, sha256_file
    from ResolveScript.sources import git

    pkg = _write_package(tmp_path / "src", "gizmo", "1.2.0")
    archive = _tar(pkg, tmp_path / "gizmo-1.2.0.tar.gz")
    archive_bytes = archive.read_bytes()

    def fake_fetch(url, *, dest, expected_sha256=None, timeout=45.0):
        dest.write_bytes(archive_bytes)
        return Fetched(
            path=dest, sha256=sha256_file(dest), size=len(archive_bytes), url=url
        )

    monkeypatch.setattr(git, "fetch", fake_fetch)
    resolved = resolve_spec(
        "github:a/b#main", cwd=tmp_path, work_dir=tmp_path / "work"
    )
    assert resolved.version == "1.2.0"
    assert resolved.source == "github:a/b#main"


def test_resolve_missing_manifest(tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ResolveError, match="manifest.json"):
        resolve_spec(f"file:{empty}", cwd=tmp_path, work_dir=tmp_path / "work")


def test_lockfile_satisfies(tmp_path) -> None:
    spec = "github:a/b#semver:>=1.0 <2.0"
    assert lockfile_satisfies(
        {"source": "github:a/b#semver:>=1.0 <2.0", "version": "1.4.0"}, spec, cwd=tmp_path
    )
    assert not lockfile_satisfies(
        {"source": "github:a/b#semver:>=1.0 <2.0", "version": "2.5.0"}, spec, cwd=tmp_path
    )
    assert not lockfile_satisfies(
        {"source": "github:a/c", "version": "1.4.0"}, spec, cwd=tmp_path
    )
    assert not lockfile_satisfies(None, spec, cwd=tmp_path)


# --------------------------------------------------------------------------
# workspace
# --------------------------------------------------------------------------
def test_workspace_add_remove(tmp_path) -> None:
    from ResolveScript.workspace import save

    data = add_dependency("widget", "github:OseMine/widget#semver:^1.0", tmp_path)
    save(data, tmp_path)
    assert read_workspace(tmp_path)["dependencies"]["widget"].endswith("^1.0")
    removed = remove_dependency("widget", tmp_path)
    assert "widget" not in removed["dependencies"]


# --------------------------------------------------------------------------
# consumer CLI flows (hermetic: local archive / path sources)
# --------------------------------------------------------------------------
def _run_cli(tmp_path, monkeypatch, argv, cwd=None):

    from ResolveScript.cli import main

    target = cwd or tmp_path
    monkeypatch.chdir(target)
    return main(argv)


def test_cli_add_from_archive_then_install_locked(tmp_path, monkeypatch, capsys) -> None:
    from ResolveScript.cli import main
    from ResolveScript.install.registry import get_extension, read_registry

    pkg = _write_package(tmp_path / "src", "gizmo", "2.0.0")
    archive = _tar(pkg, tmp_path / "gizmo-2.0.0.tar.gz")
    scripts = tmp_path / "Scripts"

    monkeypatch.chdir(tmp_path)
    code = main(["add", f"file:{archive}", "--scripts-root", str(scripts)])
    assert code == 0
    entry = get_extension(read_registry(scripts), "gizmo")
    assert entry["version"] == "2.0.0"
    assert entry["source"] == f"file:{archive}"
    assert len(entry["integrity"]) == 64
    assert entry["name"] == "gizmo"

    deps = read_workspace(tmp_path)["dependencies"]
    assert deps["gizmo"] == f"file:{archive}"
    assert (scripts / "Comp" / "gizmo" / "gizmo.py").is_file()

    capsys.readouterr()
    code = main(["install", "--scripts-root", str(scripts)])
    out = capsys.readouterr().out
    assert code == 0
    assert "already installed gizmo 2.0.0" in out

    capsys.readouterr()
    code = main(["install", "--locked", "--scripts-root", str(scripts)])
    out = capsys.readouterr().out
    assert code == 0
    assert "locked gizmo 2.0.0" in out

    # remove uninstalls AND unrecords from resolvescript.json
    code = main(["remove", "gizmo", "--scripts-root", str(scripts)])
    assert code == 0
    out = capsys.readouterr().out
    assert "unrecorded gizmo" in out
    assert not (scripts / "Comp" / "gizmo").exists()
    assert "gizmo" not in read_workspace(tmp_path)["dependencies"]


def test_cli_install_author_flow_and_workspace_materialize(tmp_path, monkeypatch, capsys) -> None:
    from ResolveScript.cli import main
    from ResolveScript.install.registry import get_extension, read_registry
    from ResolveScript.scaffold import scaffold_project

    scripts = tmp_path / "Scripts"
    scaffold_project("demo", destination=tmp_path)
    project = tmp_path / "demo"
    deps = {"widget": f"file:{_write_package(tmp_path / 'dep', 'widget', '0.9.0')}"}
    (project / "resolvescript.json").write_text(
        json.dumps({"dependencies": deps}), encoding="utf-8"
    )

    monkeypatch.chdir(project)
    # author flow: scaffolded manifest present -> install self
    code = main(["install", "--scripts-root", str(scripts)])
    assert code == 0
    assert get_extension(read_registry(scripts), "demo")
    assert (scripts / "Comp" / "demo").is_dir()

    # remove the manifest to exercise the workspace-materialize branch
    (project / "manifest.json").unlink()
    capsys.readouterr()
    code = main(["install", "--scripts-root", str(scripts)])
    out = capsys.readouterr().out
    assert code == 0
    assert "widget" in out
    assert get_extension(read_registry(scripts), "widget")


def test_cli_update_precise(tmp_path, monkeypatch, capsys) -> None:
    from ResolveScript.cli import main
    from ResolveScript.install.registry import get_extension, read_registry

    scripts = tmp_path / "Scripts"
    archive = _tar(_write_package(tmp_path / "src", "gizmo", "2.0.0"), tmp_path / "gizmo.tar.gz")
    (tmp_path / "resolvescript.json").write_text(
        json.dumps({"dependencies": {"gizmo": f"file:{archive}"}}), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    code = main(["update", "--scripts-root", str(scripts)])
    assert code == 0
    entry = get_extension(read_registry(scripts), "gizmo")
    assert entry["version"] == "2.0.0"
    out = capsys.readouterr().out
    assert "Installed gizmo 2.0.0" in out


def test_cli_update_requires_workspace(tmp_path, monkeypatch, capsys) -> None:
    from ResolveScript.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["update"]) == 2
    assert "no resolvescript.json" in capsys.readouterr().err


def test_cli_search_known(tmp_path, monkeypatch, capsys) -> None:
    from ResolveScript.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["search", "hello"]) == 0
    out = capsys.readouterr().out
    assert "hello" in out


def test_cli_manage_list_json(tmp_path, monkeypatch, capsys) -> None:
    from ResolveScript.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["manage", "list", "--json"]) == 0
    assert capsys.readouterr().out.strip() == "{}"
