"""Tool definitions in the shape the Anthropic Messages API accepts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sql_rag_util.engine import SqlRag

__all__ = ["tool_definitions"]


def tool_definitions(engine: SqlRag, *, tier: str = "standard") -> list[dict[str, Any]]:
    """Return ``tools`` entries: name, description, input_schema, and input_examples."""
    out = []
    for spec in engine.tool_specs(tier=tier):
        entry: dict[str, Any] = {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema()}
        if spec.examples:
            entry["input_examples"] = [dict(e) for e in spec.examples]
        out.append(entry)
    return out
