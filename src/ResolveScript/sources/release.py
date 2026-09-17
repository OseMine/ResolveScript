"""GitHub release-asset URLs from ``manifest.release``."""

from __future__ import annotations

from dataclasses import dataclass


class ReleaseError(RuntimeError):
    pass


@dataclass
class ReleaseSpec:
    url: str = ""
    owner: str | None = None
    repo: str | None = None
    asset: str | None = None
    tag: str | None = None

    @classmethod
    def from_data(cls, data: dict) -> ReleaseSpec:
        owner = data.get("owner")
        repo = data.get("repo")
        return cls(
            url=str(data.get("url", "")) or None,
            owner=str(owner) if owner else None,
            repo=str(repo) if repo else None,
            asset=(data.get("asset") and str(data["asset"])) or None,
            tag=(data.get("tag") and str(data["tag"])) or None,
        )


def asset_download_url(spec: ReleaseSpec, manifest_name: str, version: str) -> str:
    """Resolve ``spec`` to a direct-download URL.

    ``manifest.release.url`` wins when present. Otherwise build the GitHub
    ``releases/latest/download/<asset>`` URL from owner/repo; the asset name
    defaults to ``<name>-<version>.tgz``.
    """
    if spec.url:
        return spec.url
    if not spec.owner or not spec.repo:
        raise ReleaseError(
            "manifest.release needs 'url' or both 'owner' and 'repo'"
        )
    asset = spec.asset or f"{manifest_name}-{version}.tgz"
    if spec.tag:
        return (
            f"https://github.com/{spec.owner}/{spec.repo}"
            f"/releases/download/{spec.tag}/{asset}"
        )
    return (
        f"https://github.com/{spec.owner}/{spec.repo}"
        f"/releases/latest/download/{asset}"
    )
