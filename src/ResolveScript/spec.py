"""Specifier parsing: ``add``/``install`` arguments -> :class:`Spec`."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import ResolveScriptError
from .sources.archive import is_archive_path


class SpecError(ResolveScriptError, ValueError):
    pass


@dataclass
class Spec:
    raw: str
    kind: str  # path | file-archive | archive | manifest | github | name
    source: str  # canonical source string recorded in the registry / deps
    location: Path | None = None
    url: str | None = None
    owner: str | None = None
    repo: str | None = None
    ref: str | None = None
    range_text: str | None = None

    @property
    def name_hint(self) -> str:
        if self.owner and self.repo:
            return self.repo
        if self.location:
            return self.location.name
        return self.raw


def _split_fragment(text: str) -> tuple[str, str | None]:
    index = text.find("#")
    if index == -1:
        return text, None
    return text[:index], text[index + 1 :]


def _looks_like_windows_path(text: str) -> bool:
    return bool(
        re.match(r"^[a-zA-Z]:[\\/]", text)
    )


def parse_specifier(raw: str, *, cwd: Path | None = None) -> Spec:
    """Classify a raw specifier string into a :class:`Spec`."""
    cwd = cwd or Path.cwd()
    text = raw.strip()
    if not text:
        raise SpecError("empty specifier")

    # file: scheme (archive or directory)
    if text.startswith("file:"):
        location = Path(text[len("file:") :])
        if not location.is_absolute():
            location = (cwd / location).resolve()
        if is_archive_path(str(location)):
            return Spec(raw=raw, kind="file-archive", source=f"file:{location}", location=location)
        return Spec(raw=raw, kind="path", source=f"file:{location}", location=location)

    # https?:// URLs
    lower = text.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        if is_archive_path(text):
            return Spec(raw=raw, kind="archive", source=text, url=text)
        return Spec(raw=raw, kind="manifest", source=text, url=text)

    # github:owner/repo[...]
    if text.startswith("github:") or text.startswith("gh:"):
        body, fragment = _split_fragment(text.split(":", 1)[1])
        owner, repo = _split_owner_repo(body)
        return _github_spec(raw, owner, repo, fragment)

    # paths: relative markers, absolute, existing, or windows paths
    if (
        text in (".", "..")
        or text.startswith("./")
        or text.startswith("../")
        or text.startswith("\\")
        or _looks_like_windows_path(text)
        or Path(text).is_absolute()
        or Path(cwd / text).exists()
    ):
        location = (cwd / text).resolve()
        if is_archive_path(str(location)):
            return Spec(raw=raw, kind="file-archive", source=f"file:{location}", location=location)
        return Spec(raw=raw, kind="path", source=str(location), location=location)

    # owner/repo
    if "/" in text:
        body, fragment = _split_fragment(text)
        owner, repo = _split_owner_repo(body)
        return _github_spec(raw, owner, repo, fragment)

    # bare name
    return Spec(raw=raw, kind="name", source=text)


def _split_owner_repo(body: str) -> tuple[str, str]:
    parts = body.split("/")
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    if len(parts) > 2:
        raise SpecError(f"invalid github specifier {body!r} (expected owner/repo)")
    owner = os.environ.get("RESOLVESCRIPT_USER", "")
    if not owner:
        raise SpecError(
            f"cannot infer github owner for {body!r} (set RESOLVESCRIPT_USER)"
        )
    return owner, body


def _github_spec(raw: str, owner: str, repo: str, fragment: str | None) -> Spec:
    source = f"github:{owner}/{repo}"
    ref: str | None = None
    range_text: str | None = None
    if fragment:
        if fragment.startswith("semver:"):
            range_text = fragment[len("semver:") :] or "*"
        else:
            ref = fragment
        source = f"{source}#{'semver:' + range_text if range_text else ref}"
    return Spec(
        raw=raw,
        kind="github",
        source=source,
        owner=owner,
        repo=repo,
        ref=ref,
        range_text=range_text,
    )
