"""GitHub sources: codeload tarball URLs and SemVer tag selection."""

from __future__ import annotations

from pathlib import Path

from ..fetch import fetch, fetch_json
from ..semver import Version, pick_best
from .archive import unpack_archive


class GitSourceError(RuntimeError):
    pass


def codeload_url(owner: str, repo: str, ref: str | None = None) -> str:
    slug = ref or "HEAD"
    return f"https://codeload.github.com/{owner}/{repo}/tar.gz/{slug}"


def default_branch(owner: str, repo: str) -> str:
    """Best-effort default branch (falls back to HEAD on failure)."""
    try:
        data = fetch_json(f"https://api.github.com/repos/{owner}/{repo}")
    except Exception:
        return "HEAD"
    if isinstance(data, dict):
        default = data.get("default_branch")
        if isinstance(default, str) and default:
            return default
    return "HEAD"


def list_tags(owner: str, repo: str) -> list[str]:
    """Return release tag names (e.g. ``v1.2.3``) from the GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=100"
    data = fetch_json(url)
    if not isinstance(data, list):
        raise GitSourceError(f"unexpected GitHub tags response for {owner}/{repo}")
    return [str(item.get("name")) for item in data if isinstance(item, dict)]


def resolve_tag(owner: str, repo: str, range_text: str | None, ref: str | None):
    """Pick the ref to download.

    An explicit ``ref`` wins. Otherwise, with ``#semver:<range>``, the highest
    tag satisfying the range; with no range, ``HEAD``.
    """
    if ref:
        return ref
    if not range_text:
        return "HEAD"
    tags = list_tags(owner, repo)
    candidates = [t[1:] if t.startswith("v") else t for t in tags]
    best = pick_best(candidates, range_text)
    if best is None:
        raise GitSourceError(
            f"no tag of {owner}/{repo} satisfies '{range_text}' "
            f"(tags: {', '.join(tags) or 'none'})"
        )
    if f"v{best}" in tags:
        return f"v{best}"
    return best


def download_github(
    owner: str,
    repo: str,
    *,
    ref: str | None = None,
    range_text: str | None = None,
    cache_dir: Path,
) -> tuple[Path, str]:
    """Download the codeload tarball and unpack it.

    Returns ``(package_root, integrity_sha256)``.
    """
    selected = resolve_tag(owner, repo, range_text, ref)
    if selected and selected != "HEAD" and selected.startswith("v"):
        # keep the v-prefixed tag if that is what the repo calls it
        pass
    url = codeload_url(owner, repo, None if selected == "HEAD" else selected)
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive = cache_dir / f"{owner}-{repo}-{selected or 'head'}.tgz"
    from ..fetch import FetchError, sha256_file

    try:
        if not archive.is_file():
            fetch(url=url, dest=archive)
    except FetchError as exc:
        raise GitSourceError(str(exc)) from exc
    package_dir = cache_dir / f"{owner}-{repo}-{selected or 'head'}"
    if not (package_dir / "manifest.json").is_file():
        package_dir = unpack_archive(archive, cache_dir / "unpacked" / f"{owner}-{repo}-{selected}")
    return package_dir, sha256_file(archive)


def tags_have_version(tags: list[str]) -> bool:
    return any(_is_version_tag(t) for t in tags)


def _is_version_tag(tag: str) -> bool:
    try:
        Version.parse(tag[1:] if tag.startswith("v") else tag)
        return True
    except Exception:
        return False
