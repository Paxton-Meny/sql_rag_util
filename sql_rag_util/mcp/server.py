"""JSON-RPC 2.0 over newline-delimited stdio, implementing the MCP tool methods."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

import sql_rag_util
from sql_rag_util.adapters.mcp import call_tool, tool_definitions

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TextIO

    from sql_rag_util.engine import SqlRag

__all__ = ["PROTOCOL_VERSION", "SERVER_NAME", "handle_message", "serve_stdio"]

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "sql_rag_util"
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


def _error(identifier: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def _result(identifier: object, result: object) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def handle_message(engine: SqlRag, message: object, *, tier: str = "standard", version: str | None = None) -> dict[str, Any] | None:
    """Return the response for one request, or ``None`` for a notification.

    ``version`` is reported as ``serverInfo.version`` and defaults to the
    package version.
    """
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _error(message.get("id") if isinstance(message, dict) else None, _INVALID_REQUEST, "invalid request")
    method = message["method"]
    identifier = message.get("id")
    params = message.get("params") or {}
    if method.startswith("notifications/"):
        return None
    if not isinstance(params, dict):
        return _error(identifier, _INVALID_PARAMS, "params must be an object")
    if method == "initialize":
        return _result(
            identifier,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": version or sql_rag_util.__version__},
                "instructions": engine.instructions(),
            },
        )
    if method == "ping":
        return _result(identifier, {})
    if method == "tools/list":
        return _result(identifier, {"tools": tool_definitions(engine, tier=tier)})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _error(identifier, _INVALID_PARAMS, "tools/call needs a name and an arguments object")
        return _result(identifier, call_tool(engine, name, arguments, tier=tier))
    return _error(identifier, _METHOD_NOT_FOUND, f"unknown method {method}")


def serve_stdio(
    engine: SqlRag,
    *,
    tier: str = "standard",
    version: str | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    on_error: Callable[[str], None] | None = None,
) -> None:
    """Read requests line by line until end of input, writing one response per line.

    A server must answer every request rather than die on one, so any
    exception raised while handling a request is passed to ``on_error`` and
    answered as a JSON-RPC internal error (-32603) naming only its type.
    """
    reader = stdin if stdin is not None else sys.stdin
    writer = stdout if stdout is not None else sys.stdout
    for line in reader:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response: dict[str, Any] | None = _error(None, _PARSE_ERROR, "parse error")
        else:
            try:
                response = handle_message(engine, message, tier=tier, version=version)
            except Exception as exc:
                if on_error is not None:
                    on_error(f"{type(exc).__name__}: {exc}")
                response = _error(message.get("id") if isinstance(message, dict) else None, _INTERNAL_ERROR, f"internal error: {type(exc).__name__}")
        if response is not None:
            writer.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False) + "\n")
            writer.flush()
