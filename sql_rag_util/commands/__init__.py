"""Agent-facing commands: tool specs, JSON schema derivation, dispatch, rendering."""

from __future__ import annotations

from sql_rag_util.commands.registry import Registry

__all__ = ["default_registry"]


def default_registry() -> Registry:
    """Return a registry holding every built-in tool."""
    return Registry(())
