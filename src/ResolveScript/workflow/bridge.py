"""The line protocol between the Electron shell and the Python integration.

A Workflow Integration **script** is the portable artifact: Python, any
platform, and the UI drawn by Resolve's own Qt UIManager. A Workflow
Integration **plugin** is an Electron app, and Resolve only loads it on
Windows and macOS. The two are not alternatives — the plugin is a shell and
the script is the brain, so the generated ``main.js`` starts the Python
integration once and talks to it over this protocol rather than shelling out
per click.

One JSON object per line, in both directions. ResolveScript owns both halves,
so the wire format is ours to change, but it is deliberately the smallest thing
that works: no framing, no handshake, no ids.

Request::

    {"action": "launch"}
    {"action": "callback", "name": "RenderStart"}
    {"action": "ping"}

Response::

    {"ok": true, "result": {...}}
    {"ok": false, "error": "..."}

A handler's return value is passed through :func:`plain`, which drops anything
that is not JSON-serialisable rather than failing the whole call. An exception
becomes ``{"ok": false, "error": "TypeError: ..."}`` — the shell has no way to
read a Python traceback otherwise, so the type name is included in the message.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from typing import Any

from .model import Context, Integration, WorkflowError

__all__ = ["ACTIONS", "Bridge", "dumps", "loads", "plain"]

#: Every action :class:`Bridge` answers. ``quit`` ends the session.
ACTIONS: tuple[str, ...] = ("ping", "describe", "launch", "callback", "context", "quit")


def plain(value: Any) -> Any:
    """Coerce a handler's return value into something JSON can carry."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [plain(v) for v in value]
    return repr(value)


def dumps(payload: Mapping[str, Any]) -> str:
    """Serialise one message as a single line (no embedded newlines)."""
    return json.dumps(payload, default=plain, separators=(",", ":"))


def loads(line: str) -> dict[str, Any]:
    """Parse one line, raising :class:`WorkflowError` on anything malformed."""
    text = line.strip()
    if not text:
        raise WorkflowError("empty message")
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise WorkflowError(f"not a JSON message: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowError(f"expected a JSON object, got {type(payload).__name__}")
    return payload


class Bridge:
    """Answers protocol requests for one integration.

    Keeping this separate from the transport means the Electron half and the
    test half exercise exactly the same code: a test writes lines into
    :meth:`handle` and asserts on the replies, and ``--serve`` does the same
    over real pipes.
    """

    def __init__(self, integration: Integration, context: Context | None = None):
        self.integration = integration
        self.context = context if context is not None else integration.context()
        self.stopped = False

    # -- dispatch --------------------------------------------------------
    def handle(self, line: str) -> dict[str, Any]:
        """Answer one request line. Never raises."""
        try:
            request = loads(line)
        except WorkflowError as exc:
            return {"ok": False, "error": str(exc)}
        return self.dispatch(request)

    def dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Answer one decoded request. Never raises."""
        action = str(request.get("action", ""))
        try:
            if action == "ping":
                return self._ok({"pong": True, "id": self.integration.id})
            if action == "describe":
                return self._ok(self.integration.as_dict())
            if action == "context":
                return self._ok(self.context.describe())
            if action == "launch":
                return self._ok(self.launch())
            if action == "callback":
                return self._ok(self.callback(str(request.get("name", ""))))
            if action == "quit":
                self.stopped = True
                return self._ok({"bye": True})
        except WorkflowError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # the shell cannot show a traceback
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {
            "ok": False,
            "error": f"unknown action {action!r}; expected one of {', '.join(ACTIONS)}",
        }

    def _ok(self, result: Any) -> dict[str, Any]:
        return {"ok": True, "result": plain(result)}

    # -- actions ---------------------------------------------------------
    def launch(self) -> Any:
        return self.integration.launch(self.context)

    def callback(self, name: str) -> Any:
        return self.integration.trigger(name, self.context)

    def calls(self, lines: Iterator[str] | list[str]) -> list[dict[str, Any]]:
        """Answer a batch of lines, stopping at ``quit``. For tests."""
        replies: list[dict[str, Any]] = []
        for line in lines:
            reply = self.handle(line)
            replies.append(reply)
            if reply.get("ok") and self.stopped:
                break
        return replies


def serve(
    integration: Integration,
    context: Context | None = None,
    stdin: Any = None,
    stdout: Any = None,
) -> int:
    """Run the protocol over ``stdin``/``stdout`` until ``quit`` or EOF.

    This is what the generated launcher does under ``--serve``; the Electron
    shell spawns it once and keeps the process alive for the life of its
    window.
    """
    bridge = Bridge(integration, context)
    source = stdin if stdin is not None else sys.stdin
    sink = stdout if stdout is not None else sys.stdout
    for line in source:
        reply = bridge.handle(line)
        sink.write(dumps(reply) + "\n")
        sink.flush()
        if bridge.stopped:
            break
    return 0


def callback_cli(
    integration: Integration,
    name: str,
    context: Context | None = None,
) -> int:
    """Run one callback and report it as JSON. Used by the plugin's callbacks.

    Resolve's Electron API delivers callbacks to JavaScript, not to Python, so
    the shell invokes the script once per event with ``--callback NAME``. The
    exit code carries the outcome and stdout carries the result, which is the
    same shape every other command in the project uses.
    """
    bridge = Bridge(integration, context)
    reply = bridge.dispatch({"action": "callback", "name": name})
    sys.stdout.write(dumps(reply) + "\n")
    sys.stdout.flush()
    return 0 if reply.get("ok") else 1
