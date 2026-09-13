"""The set of tools an engine exposes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sql_rag_util.exceptions import ToolSpecError, UnknownToolError
from sql_rag_util.schema.resolve import closest

if TYPE_CHECKING:
    from sql_rag_util.commands.spec import ToolSpec

__all__ = ["Registry"]


class Registry:
    """Tools by name, filtered by tier and by whether writes are allowed."""

    def __init__(self, specs: tuple[ToolSpec, ...] = ()) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        """Add ``spec``; a duplicate name is an error."""
        if spec.name in self._specs:
            raise ToolSpecError(f"tool {spec.name!r} is already registered")
        self._specs[spec.name] = spec

    def specs(self, *, tier: str = "standard", include_mutating: bool = False) -> tuple[ToolSpec, ...]:
        """Return the tools in ``tier`` and below, without writers unless asked."""
        return tuple(s for s in self._specs.values() if s.included_in(tier) and (include_mutating or not s.mutating))

    def get(self, name: str, *, tier: str = "full", include_mutating: bool = True) -> ToolSpec:
        """Return the tool called ``name`` if it is exposed under the given filters."""
        exposed = {s.name: s for s in self.specs(tier=tier, include_mutating=include_mutating)}
        if name not in exposed:
            raise UnknownToolError(f"unknown tool {name!r}", suggestions=closest(name, exposed))
        return exposed[name]
