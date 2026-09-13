"""Tool definitions in the OpenAI function-calling shape, strict mode compatible.

Strict mode requires every property to be listed as required, optional
fields expressed as nullable types, and ``additionalProperties: false`` on
every object. The conversion is applied recursively to the derived schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sql_rag_util.engine import SqlRag

__all__ = ["tool_definitions", "strict_schema"]


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    if "anyOf" in schema:
        members = list(schema["anyOf"])
        if not any(m.get("type") == "null" or (isinstance(m.get("type"), list) and "null" in m["type"]) for m in members):
            members.append({"type": "null"})
        return {**schema, "anyOf": members}
    kind = schema.get("type")
    if isinstance(kind, list):
        return {**schema, "type": kind if "null" in kind else [*kind, "null"]}
    if isinstance(kind, str):
        return {**schema, "type": [kind, "null"]}
    return schema


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return ``schema`` rewritten so OpenAI strict mode accepts it."""
    out = dict(schema)
    if "anyOf" in out:
        out["anyOf"] = [strict_schema(m) for m in out["anyOf"]]
    if out.get("type") == "object" and "properties" in out:
        required = set(out.get("required", []))
        properties = {}
        for name, member in out["properties"].items():
            converted = strict_schema(member)
            properties[name] = converted if name in required else _nullable(converted)
        out["properties"] = properties
        out["required"] = list(out["properties"])
        out["additionalProperties"] = False
    if out.get("type") == "array" and "items" in out:
        out["items"] = strict_schema(out["items"])
    return out


def tool_definitions(engine: SqlRag, *, tier: str = "standard") -> list[dict[str, Any]]:
    """Return ``tools`` entries of type function with strict parameters."""
    return [
        {"type": "function", "function": {"name": spec.name, "description": spec.description, "parameters": strict_schema(spec.input_schema()), "strict": True}}
        for spec in engine.tool_specs(tier=tier)
    ]
