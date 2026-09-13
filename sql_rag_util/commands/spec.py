"""Tool specifications and command results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from sql_rag_util.commands.jsonschema import schema_for
from sql_rag_util.exceptions import ToolSpecError

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Tier", "TIERS", "ToolSpec", "CommandResult"]

Tier = Literal["minimal", "standard", "full"]
TIERS: tuple[str, ...] = ("minimal", "standard", "full")


@dataclass(frozen=True, slots=True)
class CommandResult:
    """What a command returns before dispatch wraps it in an envelope.

    Parameters
    ----------
    data
        JSON-serializable fields merged into the envelope.
    text
        Compact rendering of the same result for text-only consumers.
    truncated
        Whether the result was cut by a limit.
    notes
        Advice for the agent.
    """

    data: dict[str, Any]
    text: str
    truncated: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A command as a framework sees it.

    Parameters
    ----------
    name
        Tool name, unique in the registry.
    title
        Short human title.
    description
        The prompt text explaining when and how to use the tool.
    args_type
        Frozen dataclass of arguments; its schema is derived.
    handler
        Callable taking the engine and the arguments instance.
    tier
        The smallest tier that includes this tool.
    mutating
        Whether the tool writes metadata.
    examples
        Example argument objects shown to models that accept them.
    """

    name: str
    title: str
    description: str
    args_type: type
    handler: Callable[[Any, Any], CommandResult]
    tier: Tier = "standard"
    mutating: bool = False
    examples: tuple[dict[str, Any], ...] = field(default=())

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ToolSpecError(f"{self.name}: tier must be one of {TIERS}")
        if not self.description.strip():
            raise ToolSpecError(f"{self.name}: description is required")
        self.input_schema()

    def input_schema(self) -> dict[str, object]:
        """Return the JSON Schema of the arguments."""
        return schema_for(self.args_type)

    def included_in(self, tier: str) -> bool:
        """Return whether this tool belongs to ``tier`` or a smaller one."""
        if tier not in TIERS:
            raise ToolSpecError(f"unknown tier {tier!r}; expected one of {TIERS}")
        return TIERS.index(self.tier) <= TIERS.index(tier)
