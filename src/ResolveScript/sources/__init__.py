"""Extension sources: where a package comes from.

Kind matrix (mirrors the design notes):

``path``        a directory on disk (``./dir``, ``../dir``, absolute; ``file:dir``)
``archive``     a tar.gz/zip downloaded from a URL (or ``file:`` archive)
``github``      ``owner/repo`` or ``github:owner/repo`` (codeload tarball,
                ``#semver:<range>``/``#<ref>`` selection)
``manifest``    a URL pointing at a manifest.json (follows ``release.url``)
``name``        bare name -> looked up in the known-extensions table
"""

from __future__ import annotations

from .archive import (
    ARCHIVE_SUFFIXES,
    ArchiveError,
    is_archive_path,
    make_archive,
    unpack_archive,
)
from .git import (
    GitSourceError,
    codeload_url,
    default_branch,
    download_github,
    list_tags,
    resolve_tag,
    tags_have_version,
)
from .known import (
    CONVENTIONS,
    canonical_source,
    known_names,
    lookup,
    search,
)
from .registry_index import (
    RegistryIndex,
    canonical_source_enhanced,
    get_registry,
    lookup_enhanced,
    refresh_registry,
    search_enhanced,
)
from .release import ReleaseError, ReleaseSpec, asset_download_url

__all__ = [
    "ARCHIVE_SUFFIXES",
    "ArchiveError",
    "CONVENTIONS",
    "GitSourceError",
    "ReleaseError",
    "ReleaseSpec",
    "RegistryIndex",
    "asset_download_url",
    "canonical_source",
    "canonical_source_enhanced",
    "codeload_url",
    "default_branch",
    "download_github",
    "get_registry",
    "is_archive_path",
    "known_names",
    "list_tags",
    "lookup",
    "lookup_enhanced",
    "make_archive",
    "refresh_registry",
    "resolve_tag",
    "search",
    "search_enhanced",
    "tags_have_version",
    "unpack_archive",
]
