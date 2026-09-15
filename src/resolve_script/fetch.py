"""HTTP(S) download + SHA-256 integrity verification (stdlib only)."""

from __future__ import annotations

import hashlib
import socket
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


class FetchError(RuntimeError):
    pass


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

    Raises :class:`FetchError` on HTTP errors, or if the downloaded bytes do
    not match ``expected_sha256`` (the file is then removed).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    if not allow_remote():
        raise FetchError("network downloads are disabled (RESOLVESCRIPT_ALLOW_NETWORK=0)")
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                data = response.read()
        except Exception as exc:  # URLError, HTTPError, timeout…
            raise FetchError(f"failed to download {url}: {exc}") from exc
    finally:
        socket.setdefaulttimeout(previous)
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
