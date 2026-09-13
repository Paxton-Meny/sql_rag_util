"""Dependency-free, safety-first SQL retrieval for AI agents and tools.

The public surface is :class:`SqlRag`, the configuration types, the query
spec types, the exceptions, and the SQLite function registration. Dialects
load lazily through :mod:`sql_rag_util.dialects`.
"""

from __future__ import annotations

from sql_rag_util.config import Config, Limits, StatementEvent
from sql_rag_util.engine import SqlRag
from sql_rag_util.exceptions import SqlRagError
from sql_rag_util.query.spec import Filter, Measure, Order, QuerySpec
from sql_rag_util.search.sqlite_functions import register_sqlite_functions

__all__ = [
    "__version__",
    "SqlRag",
    "Config",
    "Limits",
    "StatementEvent",
    "QuerySpec",
    "Filter",
    "Measure",
    "Order",
    "SqlRagError",
    "register_sqlite_functions",
]

__version__ = "0.1.0"
