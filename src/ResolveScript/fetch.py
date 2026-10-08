"""HTTP(S) download + SHA-256 integrity verification (stdlib only)."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .errors import ResolveScriptError

# Maximum download size (100 MB) to prevent DoS via unbounded downloads
_MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024

logger = logging.getLogger(__name__)


class FetchError(ResolveScriptError, RuntimeError):
    pass


# Non-public address ranges that must never be fetched. Kept explicit (rather
# than relying on ipaddress.is_private/is_reserved, whose ranges vary across
# Python versions) so behavior is deterministic. Includes loopback, RFC 1918,
# CGNAT/shared space, link-local (cloud-metadata), documentation, benchmark and
# multicast ranges for both address families.
_BLOCKED_NETS = tuple(
    ipaddress.ip_network(prefix)
    for prefix in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::/128",
        "::1/128",
        "100::/64",
        "2001:db8::/32",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)


def _assert_public_host(url: str) -> None:
    """Reject URLs whose host is not a public internet address (SSRF guard).

    Loopback, private (RFC 1918 / CGNAT / ULA) and link-local addresses
    (including the cloud-metadata ``169.254.169.254``) are blocked, along
    with documentation, benchmark, multicast, unspecified and reserved ranges.
    """
    host = urlparse(url).hostname
    if not host:
        raise FetchError(f"URL has no host: {url!r}")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            resolved = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise FetchError(f"cannot resolve host {host!r}: {exc}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in resolved]
    for addr in addresses:
        if (
            addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_unspecified
            or any(addr in net for net in _BLOCKED_NETS)
        ):
            raise FetchError(
                f"{host!r} resolves to non-public address {addr} "
                "(loopback, private or link-local hosts are blocked)"
            )


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects to non-http(s) schemes, plaintext downgrades, or
    non-public hosts (SSRF guard)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913
        old_scheme = urlparse(req.full_url).scheme.lower()
        new_scheme = urlparse(newurl).scheme.lower()
        if new_scheme not in ("http", "https"):
            raise FetchError(f"redirect to non-http(s) scheme blocked: {newurl!r}")
        if old_scheme == "https" and new_scheme != "https":
            raise FetchError(
                f"refusing to downgrade https connection to plaintext http via redirect: {newurl!r}"
            )
        _assert_public_host(newurl)
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
    _assert_public_host(url)
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
    logger.info("downloaded %s (%d bytes, sha256 %s)", url, size, digest[:12])
    return Fetched(path=dest, sha256=digest, size=size, url=url)


def fetch_json(
    url: str, *, timeout: float = 45.0
) -> object:
    """Download a JSON document (used for the GitHub tags API in tests)."""
    with tempfile.TemporaryDirectory() as tmp:
        result = fetch(url, dest=Path(tmp) / "payload", timeout=timeout)
    import json

    return json.loads(result.path.read_text("utf-8"))
