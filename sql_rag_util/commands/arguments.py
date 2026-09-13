"""Build a tool's argument dataclass from JSON-shaped input.

The same annotations that drive the JSON Schema drive conversion here, so a
value the schema would refuse is refused with a message naming the field.
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from typing import Any

from sql_rag_util.exceptions import ArgumentError, SqlRagError
from sql_rag_util.schema.resolve import closest

__all__ = ["build_arguments"]

_SIMPLE: dict[object, tuple[type, ...]] = {str: (str,), int: (int,), float: (int, float), bool: (bool,), type(None): (type(None),)}


def _fits_simple(annotation: object, value: object) -> bool:
    accepted = _SIMPLE[annotation]
    if isinstance(value, bool) and annotation is not bool:
        return False
    return isinstance(value, accepted)


def _convert(annotation: object, value: object, path: str) -> Any:
    if annotation in _SIMPLE:
        if not _fits_simple(annotation, value):
            raise ArgumentError(f"{path}: expected {getattr(annotation, '__name__', 'null')}, got {type(value).__name__}")
        return value
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        for member in args:
            try:
                return _convert(member, value, path)
            except ArgumentError:
                continue
        raise ArgumentError(f"{path}: value {value!r} fits none of the accepted shapes")
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise ArgumentError(f"{path}: expected a list, got {type(value).__name__}")
        return tuple(_convert(args[0], item, f"{path}[{index}]") for index, item in enumerate(value))
    if origin is typing.Literal:
        if value not in args:
            raise ArgumentError(f"{path}: expected one of {list(args)}, got {value!r}", suggestions=tuple(str(a) for a in args))
        return value
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        try:
            return annotation(value)
        except ValueError:
            raise ArgumentError(f"{path}: expected one of {[m.value for m in annotation]}, got {value!r}", suggestions=tuple(m.value for m in annotation)) from None
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return build_arguments(annotation, value, path)
    raise ArgumentError(f"{path}: unsupported annotation {annotation!r}")


def build_arguments(args_type: type, data: object, path: str = "arguments") -> Any:
    """Return an ``args_type`` instance built from ``data``.

    Raises
    ------
    ArgumentError
        For a non-object, an unknown key (with close matches), a missing
        required key, or a value of the wrong shape. Validation errors the
        dataclass raises itself pass through unchanged.
    """
    if not isinstance(data, dict):
        raise ArgumentError(f"{path}: expected an object, got {type(data).__name__}")
    hints = typing.get_type_hints(args_type)
    fields = {f.name: f for f in dataclasses.fields(args_type) if f.init}
    for key in data:
        if key not in fields:
            raise ArgumentError(f"{path}: unknown key {key!r}", suggestions=closest(str(key), fields))
    values: dict[str, Any] = {}
    for name, f in fields.items():
        if name in data:
            values[name] = _convert(hints[name], data[name], f"{path}.{name}")
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            raise ArgumentError(f"{path}: missing required key {name!r}")
    try:
        return args_type(**values)
    except SqlRagError:
        raise
    except (TypeError, ValueError) as exc:
        raise ArgumentError(f"{path}: {exc}") from None
