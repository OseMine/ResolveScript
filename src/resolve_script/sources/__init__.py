"""Extension sources: where a package comes from.

Kind matrix (mirrors the design notes):

``path``        a directory on disk (``./dir``, ``../dir``, absolute; ``file:dir``)
``archive``     a tar.gz/zip downloaded from a URL (or ``file:`` archive)
``github``      ``owner/repo`` or ``github:owner/repo`` (codeload tarball,
                ``#semver:<range>``/``#<ref>`` selection)
``manifest``    a URL pointing at a manifest.json (follows ``release.url``)
``name``        bare name -> looked up in the known-extensions table
"""

from .archive import ARCHIVE_SUFFIXES, is_archive_path, unpack_archive  # noqa: F401

__all__ = ["ARCHIVE_SUFFIXES", "is_archive_path", "unpack_archive"]
