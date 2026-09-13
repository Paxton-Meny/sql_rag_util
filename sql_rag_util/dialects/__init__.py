"""Dialect registry with lazy loading from a fixed name-to-module map."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import UnsupportedDialectError

if TYPE_CHECKING:
    from sql_rag_util.dialects.base import Dialect

__all__ = ["SUPPORTED", "ALIASES", "canonical_name", "load"]

SUPPORTED: tuple[str, ...] = ("sqlite", "mysql", "mssql", "postgres")
ALIASES: dict[str, str] = {
    "sqlite3": "sqlite",
    "mariadb": "mysql",
    "postgresql": "postgres",
    "pg": "postgres",
    "sqlserver": "mssql",
    "tsql": "mssql",
}
_MODULES: dict[str, str] = {name: f"sql_rag_util.dialects.{name}" for name in SUPPORTED}
_CLASS_NAMES: dict[str, str] = {
    "sqlite": "SqliteDialect",
    "mysql": "MysqlDialect",
    "mssql": "MssqlDialect",
    "postgres": "PostgresDialect",
}


def canonical_name(name: str) -> str:
    """Return the supported dialect name for ``name`` or one of its aliases."""
    folded = name.strip().lower()
    folded = ALIASES.get(folded, folded)
    if folded not in _MODULES:
        raise UnsupportedDialectError(f"unsupported dialect {name!r}", suggestions=SUPPORTED)
    return folded


def load(name: str) -> Dialect:
    """Import and instantiate the dialect called ``name``."""
    canonical = canonical_name(name)
    module = importlib.import_module(_MODULES[canonical])
    return getattr(module, _CLASS_NAMES[canonical])()
