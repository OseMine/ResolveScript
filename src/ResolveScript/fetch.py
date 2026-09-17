"""HTTP(S) download + SHA-256 integrity verification (stdlib only)."""

from __future__ import annotations

import hashlib
import socket
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# Maximum download size (100 MB) to prevent DoS via unbounded downloads
_MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024


class FetchError(RuntimeError):
    pass


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects that switch to a non-http(s) scheme (SSRF guard)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913
        scheme = urlparse(newurl).scheme.lower()
        if scheme not in ("http", "https"):
            raise FetchError(f"redirect to non-http(s) scheme blocked: {newurl!r}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SafeRedirectHandler())


@dataclass
class Fetched:
    path: Path
    sha256: str
    size: int
    url: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allow_remote() -> bool:
    """Whether remote downloads are allowed (default on; off via env)."""
    import os

    return os.environ.get("RESOLVESCRIPT_ALLOW_NETWORK", "1").lower() not in (
        "0",
        "false",
        "no",
    )


def fetch(
    url: str,
    *,
    dest: Path,
    expected_sha256: str | None = None,
    timeout: float = 45.0,
) -> Fetched:
    """Download ``url`` to a fresh ``dest``; verify integrity when provided.

    Only ``http://`` and ``https://`` schemes are allowed; other schemes
    (e.g. ``file://``, ``ftp://``) raise :class:`FetchError` to prevent
    local‑file reads and SSRF.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise FetchError(f"only http/https URLs are allowed (got {url!r})")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    if not allow_remote():
        raise FetchError("network downloads are disabled (RESOLVESCRIPT_ALLOW_NETWORK=0)")
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        try:
            with _OPENER.open(url, timeout=timeout) as response:
                data = response.read(_MAX_DOWNLOAD_SIZE + 1)
        except Exception as exc:  # URLError, HTTPError, timeout…
            raise FetchError(f"failed to download {url}: {exc}") from exc
    finally:
        socket.setdefaulttimeout(previous)
    if len(data) > _MAX_DOWNLOAD_SIZE:
        raise FetchError(f"download exceeds maximum allowed size ({_MAX_DOWNLOAD_SIZE} bytes)")
    size = len(data)
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise FetchError(
            f"integrity check failed for {url}: expected sha256 "
            f"{expected_sha256}, got {digest}"
        )
    dest.write_bytes(data)
    return Fetched(path=dest, sha256=digest, size=size, url=url)


def fetch_json(
    url: str, *, timeout: float = 45.0
) -> object:
    """Download a JSON document (used for the GitHub tags API in tests)."""
    with tempfile.TemporaryDirectory() as tmp:
        result = fetch(url, dest=Path(tmp) / "payload", timeout=timeout)
    import json

    return json.loads(result.path.read_text("utf-8"))
