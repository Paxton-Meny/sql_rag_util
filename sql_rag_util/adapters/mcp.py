"""Tool definitions and call results in the Model Context Protocol shape."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sql_rag_util.commands.dispatch import compact_text, envelope
from sql_rag_util.exceptions import SqlRagError

if TYPE_CHECKING:
    from sql_rag_util.engine import SqlRag

__all__ = ["tool_definitions", "call_tool"]


def tool_definitions(engine: SqlRag, *, tier: str = "standard") -> list[dict[str, Any]]:
    """Return ``tools/list`` entries with input schemas and behavior annotations."""
    out = []
    for spec in engine.tool_specs(tier=tier):
        out.append(
            {
                "name": spec.name,
                "title": spec.title,
                "description": spec.description,
                "inputSchema": spec.input_schema(),
                "annotations": {"readOnlyHint": not spec.mutating, "destructiveHint": False, "idempotentHint": not spec.mutating, "openWorldHint": False},
            }
        )
    return out


def call_tool(engine: SqlRag, name: str, arguments: dict[str, Any], *, tier: str = "standard") -> dict[str, Any]:
    """Return a ``tools/call`` result: compact text content plus the JSON envelope as structured content."""
    try:
        result = engine.dispatcher(tier=tier).run(name, arguments)
    except SqlRagError as exc:
        hint = f" Try: {', '.join(exc.suggestions)}." if exc.suggestions else ""
        message = f"{exc.type_name}: {exc.message}{hint}"
        return {"content": [{"type": "text", "text": message}], "isError": True, "structuredContent": {"error": {"type": exc.type_name, "message": exc.message, "suggestions": list(exc.suggestions)}}}
    structured = envelope(result, engine.schema_version)
    wants_text = getattr(arguments, "get", lambda k, d=None: d)("format") == "compact"
    text = compact_text(result, engine.schema_version) if wants_text else json.dumps(structured, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return {"content": [{"type": "text", "text": text}], "structuredContent": structured}
