"""The ``get_context`` tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from sql_rag_util.commands.spec import CommandResult, ToolSpec
from sql_rag_util.exceptions import LimitExceededError, QuerySpecError

if TYPE_CHECKING:
    from sql_rag_util.engine import SqlRag

__all__ = ["GetContextArgs", "get_context", "GET_CONTEXT"]

_MAX_QUESTION_CHARS = 2000
_MAX_BUDGET = 8000


@dataclass(frozen=True, slots=True)
class GetContextArgs:
    """Arguments of ``get_context``."""

    question: str = field(metadata={"description": "The user's question or the task, in natural language."})
    budget_tokens: int | None = field(default=None, metadata={"description": "Approximate size cap for the returned cards; default 1500, maximum 8000."})
    format: Literal["json", "compact"] = field(default="json", metadata={"description": "json for structured cards; compact for text cards."})


def get_context(engine: SqlRag, args: GetContextArgs) -> CommandResult:
    """Return the tables, values, and terms that matter for the question."""
    if not args.question.strip():
        raise QuerySpecError("question must not be empty")
    if len(args.question) > _MAX_QUESTION_CHARS:
        raise QuerySpecError(f"question is longer than {_MAX_QUESTION_CHARS} characters")
    budget = args.budget_tokens if args.budget_tokens is not None else engine.limits.context_budget_tokens
    if budget < 1 or budget > _MAX_BUDGET:
        raise LimitExceededError(f"budget_tokens must be between 1 and {_MAX_BUDGET}")
    pack = engine.retriever.pack(args.question, budget_tokens=budget)
    notes = () if pack.data["tables"] else ("No table matched; call list_tables and describe_table.",)
    return CommandResult(pack.data, pack.text, notes=notes)


GET_CONTEXT = ToolSpec(
    "get_context",
    "Get context",
    "Start here for any question about the data. Returns schema cards for the tables that matter, ranked by "
    "name, meaning, and the known column values that match words in the question (value_hits tell you which "
    "column holds a literal such as a customer name or a status), plus matching glossary terms. Cards show "
    "columns with kinds and known values, relationship names for joins, and concepts and measures you can apply "
    "by name in query. Lower-ranked tables appear as one-line summaries under more.",
    GetContextArgs,
    get_context,
    tier="minimal",
    examples=({"question": "Which open orders does Acme have?"}, {"question": "revenue by region last month", "budget_tokens": 800, "format": "compact"}),
)
