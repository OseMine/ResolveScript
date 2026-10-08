"""Base exception for every error raised by ResolveScript.

Catch one class anywhere in the pipeline::

    try:
        resolvescript add github:example/tool
    except ResolveScriptError as exc:
        ...  # every ResolveScript failure lands here

Domain exceptions keep their historical bases so existing handlers keep
working: ``SpecError`` is still a ``ValueError``, ``FetchError`` is still a
``RuntimeError``, and so on. ``ResolveScriptError`` is always the *first*
base so ``except ResolveScriptError`` wins regardless of MRO ordering.
"""

from __future__ import annotations


class ResolveScriptError(Exception):
    """Base class for all errors raised by the ResolveScript library and CLI."""
