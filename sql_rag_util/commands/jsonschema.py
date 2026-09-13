"""Derive the JSON Schema of a tool's arguments from a frozen dataclass.

Supported annotations: ``str``, ``int``, ``float``, ``bool``, ``None``,
unions of those, ``tuple[X, ...]``, ``Literal`` of strings, string enums,
and nested dataclasses. Every init field needs a description in its field
metadata; anything else is a :class:`~sql_rag_util.exceptions.ToolSpecError`
at registration, never a surprise at runtime.
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing

from sql_rag_util.exceptions import ToolSpecError

__all__ = ["schema_for"]

_SIMPLE: dict[object, str] = {str: "string", int: "integer", float: "number", bool: "boolean", type(None): "null"}


def _is_simple(schema: dict[str, object]) -> bool:
    return set(schema) == {"type"} and isinstance(schema["type"], str)


def _schema(annotation: object, owner: str) -> dict[str, object]:
    if annotation in _SIMPLE:
        return {"type": _SIMPLE[annotation]}
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        members = [_schema(a, owner) for a in args]
        simple = list(dict.fromkeys(str(m["type"]) for m in members if _is_simple(m)))
        complex_members = [m for m in members if not _is_simple(m)]
        simple_schema: dict[str, object] = {"type": simple[0] if len(simple) == 1 else simple}
        if not complex_members:
            return simple_schema
        return {"anyOf": ([simple_schema] if simple else []) + complex_members}
    if origin is tuple:
        if len(args) != 2 or args[1] is not Ellipsis:
            raise ToolSpecError(f"{owner}: only tuple[X, ...] is supported, got {annotation!r}")
        return {"type": "array", "items": _schema(args[0], owner)}
    if origin is typing.Literal:
        if not all(isinstance(a, str) for a in args):
            raise ToolSpecError(f"{owner}: Literal members must be strings")
        return {"type": "string", "enum": list(args)}
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return {"type": "string", "enum": [member.value for member in annotation]}
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return schema_for(annotation)
    raise ToolSpecError(f"{owner}: unsupported annotation {annotation!r}")


def schema_for(args_type: type) -> dict[str, object]:
    """Return the object schema for ``args_type``."""
    if not dataclasses.is_dataclass(args_type):
        raise ToolSpecError(f"{args_type!r} is not a dataclass")
    hints = typing.get_type_hints(args_type)
    properties: dict[str, object] = {}
    required: list[str] = []
    for f in dataclasses.fields(args_type):
        if not f.init:
            continue
        owner = f"{args_type.__name__}.{f.name}"
        description = f.metadata.get("description")
        if not isinstance(description, str) or not description:
            raise ToolSpecError(f"{owner} has no description")
        schema = _schema(hints[f.name], owner)
        schema["description"] = description
        properties[f.name] = schema
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            required.append(f.name)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
