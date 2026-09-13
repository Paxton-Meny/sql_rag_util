"""Agent-facing commands: tool specs, JSON schema derivation, dispatch, rendering."""

from __future__ import annotations

from sql_rag_util.commands.context import GET_CONTEXT
from sql_rag_util.commands.describe import DESCRIBE_TABLE, LIST_TABLES
from sql_rag_util.commands.query import QUERY
from sql_rag_util.commands.search import SEARCH_ROWS
from sql_rag_util.commands.registry import Registry

__all__ = ["default_registry"]


def default_registry() -> Registry:
    """Return a registry holding every built-in tool."""
    return Registry((GET_CONTEXT, QUERY, DESCRIBE_TABLE, LIST_TABLES, SEARCH_ROWS))
