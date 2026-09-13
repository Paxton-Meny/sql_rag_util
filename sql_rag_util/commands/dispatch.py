"""Run a tool by name with JSON arguments and wrap the result in an envelope."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sql_rag_util.commands.arguments import build_arguments
from sql_rag_util.exceptions import SqlRagError

if TYPE_CHECKING:
    from sql_rag_util.commands.registry import Registry
    from sql_rag_util.commands.spec import CommandResult

__all__ = ["Dispatcher", "envelope", "error_envelope", "compact_text"]


def envelope(result: CommandResult, schema_version: str) -> dict[str, Any]:
    """Return the JSON envelope for ``result``."""
    return {"schema_version": schema_version, "truncated": result.truncated, "notes": list(result.notes), **result.data}


def error_envelope(exc: SqlRagError) -> dict[str, Any]:
    """Return the JSON envelope for a failed call."""
    return {"error": {"type": exc.type_name, "message": exc.message, "suggestions": list(exc.suggestions)}}


def compact_text(result: CommandResult, schema_version: str) -> str:
    """Return the compact rendering with notes and the version appended."""
    lines = [result.text.rstrip("\n")]
    lines.extend(f"note: {note}" for note in result.notes)
    if result.truncated:
        lines.append("note: result truncated; narrow with filters or lower the limit")
    lines.append(f"schema_version: {schema_version}")
    return "\n".join(lines)


class Dispatcher:
    """Name plus JSON arguments in, envelope out.

    Parameters
    ----------
    registry
        Tools available.
    engine
        The engine handed to each handler; it must expose ``schema_version``.
    tier
        The tier exposed through this dispatcher.
    include_mutating
        Whether writing tools are callable.
    """

    def __init__(self, registry: Registry, engine: Any, *, tier: str = "standard", include_mutating: bool = False) -> None:
        self._registry = registry
        self._engine = engine
        self._tier = tier
        self._include_mutating = include_mutating

    def run(self, name: str, arguments: object) -> CommandResult:
        """Build the arguments and call the handler; errors propagate."""
        spec = self._registry.get(name, tier=self._tier, include_mutating=self._include_mutating)
        args = build_arguments(spec.args_type, arguments)
        return spec.handler(self._engine, args)

    def call(self, name: str, arguments: object) -> dict[str, Any]:
        """Return the JSON envelope, or an error envelope for any package error."""
        try:
            return envelope(self.run(name, arguments), self._engine.schema_version)
        except SqlRagError as exc:
            return error_envelope(exc)

    def call_text(self, name: str, arguments: object) -> str:
        """Return the compact text rendering, or a one-line error with suggestions."""
        try:
            return compact_text(self.run(name, arguments), self._engine.schema_version)
        except SqlRagError as exc:
            hint = f" (try: {', '.join(exc.suggestions)})" if exc.suggestions else ""
            return f"error {exc.type_name}: {exc.message}{hint}"

    def call_json(self, name: str, arguments: object) -> str:
        """Return :meth:`call` serialized compactly."""
        return json.dumps(self.call(name, arguments), separators=(",", ":"), ensure_ascii=False)
