"""Regression tests for the security hardening (SSRF, XXE, path traversal,
predictable temp files, loader confinement, and cache-slug sanitization)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ResolveScript.fetch import FetchError, _assert_public_host, _SafeRedirectHandler, fetch
from ResolveScript.manifest.model import ManifestError
from ResolveScript.manifest.xml_reader import loads as xml_loads
from ResolveScript.resolver import _slug
from ResolveScript.sandbox.loader import load_source_module


# ---------------------------------------------------------------------------
# fetch: SSRF host restriction
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/anything",
        "https://[::1]/anything",
        "https://169.254.169.254/latest/meta-data/",
        "https://10.0.0.5/x",
        "https://172.16.0.1/x",
        "https://192.168.1.1/x",
        "https://100.64.0.1/x",
        "https://0.0.0.0/x",
        "https://224.0.0.1/x",
    ],
)
def test_fetch_blocks_non_public_hosts(url: str) -> None:
    with pytest.raises(FetchError):
        _assert_public_host(url)


def test_fetch_accepts_public_literal_host() -> None:
    _assert_public_host("https://93.184.216.34/example.com")


def test_fetch_rejects_non_http_scheme() -> None:
    with pytest.raises(FetchError):
        fetch("file://C:/secret.txt", dest=Path("none"))  # noqa: S108


# ---------------------------------------------------------------------------
# fetch: redirect guards
# ---------------------------------------------------------------------------
def _redirect(req_url: str, new_url: str) -> None:
    request = __import__("urllib.request", fromlist=["Request"]).Request(req_url)
    _SafeRedirectHandler().redirect_request(request, None, 302, "Found", {}, new_url)


def test_redirect_blocks_scheme_switch() -> None:
    with pytest.raises(FetchError):
        _redirect("https://cdn.example.com/a", "ftp://cdn.example.com/b")


def test_redirect_blocks_https_downgrade() -> None:
    with pytest.raises(FetchError):
        _redirect("https://cdn.example.com/a", "http://cdn.example.com/b")


def test_redirect_blocks_private_host() -> None:
    with pytest.raises(FetchError):
        _redirect("https://cdn.example.com/a", "http://127.0.0.1:8000/b")


# ---------------------------------------------------------------------------
# xml_reader: DOCTYPE / entity declarations rejected
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        '<?xml version="1.0"?><!DOCTYPE foo><!DOCTYPE bar><manifest/>',
        '<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY x "boom">]>\n<manifest/>',
        '<?xml version="1.0"?>\n<!doctype foo><manifest/>',
        '<?xml version="1.0"?><manifest><!ENTITY x "boom"></manifest>',
    ],
)
def test_xml_loads_rejects_doctype_and_entities(payload: str) -> None:
    with pytest.raises(ManifestError):
        xml_loads(payload)


# ---------------------------------------------------------------------------
# resolver: cache slug sanitization
# ---------------------------------------------------------------------------
def test_slug_keeps_safe_tail() -> None:
    assert _slug("https://cdn.example.com/files/tool-1.0.tgz") == "tool-1.0.tgz"


def test_slug_strips_path_separators_and_traversal() -> None:
    for url in (
        "https://cdn.example.com/..%2F..%2F..%2Fevil.tgz",
        "https://cdn.example.com/..%5C..%5Cevil.tgz",
        "https://cdn.example.com/..\\..\\..\\evil.tgz",
    ):
        slug = _slug(url)
        assert "/" not in slug and "\\" not in slug, slug
        assert ".." not in slug, slug


def test_slug_falls_back_to_hash() -> None:
    slug = _slug("https://cdn.example.com/../")
    assert slug.endswith(".tgz")


# ---------------------------------------------------------------------------
# sandbox loader: path confinement
# ---------------------------------------------------------------------------
def test_load_source_module_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ImportError):
        load_source_module("../escape", tmp_path)


# ---------------------------------------------------------------------------
# manage remove: registry paths re-validated
# ---------------------------------------------------------------------------
def test_manage_remove_blocked_traversal_in_registry(tmp_path: Path, monkeypatch) -> None:
    from ResolveScript.cli import main

    scripts = tmp_path / "Scripts"
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "secret.txt").write_text("sensitive", encoding="utf-8")

    registry = scripts / ".resolvescript" / "install.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "extensions": {
                    "widget": {
                        "id": "widget",
                        "name": "../../victim",
                        "targets": ["Comp"],
                        "as_directory": True,
                        "files": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    code = main(["manage", "remove", "widget", "--scripts-root", str(scripts)])
    assert code == 1
    assert victim.is_dir()
    assert (victim / "secret.txt").read_text(encoding="utf-8") == "sensitive"
