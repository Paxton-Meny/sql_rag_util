"""Run the MCP server on a SQLite database: ``python -m sql_rag_util.mcp --sqlite app.db``.

Other databases are served by constructing :class:`~sql_rag_util.engine.SqlRag`
with the driver's connection and calling :func:`~sql_rag_util.mcp.server.serve_stdio`.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from sql_rag_util.commands.spec import TIERS
from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
from sql_rag_util.exceptions import SqlRagError
from sql_rag_util.mcp.server import serve_stdio
from sql_rag_util.search.sqlite_functions import register_sqlite_functions

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sql_rag_util.mcp", description="Serve a SQLite database to MCP clients over stdio.")
    parser.add_argument("--sqlite", required=True, help="path to the SQLite database file")
    parser.add_argument("--metadata", default=None, help="metadata directory")
    parser.add_argument("--cache", default=None, help="cache directory (default: .cache under the metadata directory)")
    parser.add_argument("--tier", default="standard", choices=TIERS, help="tool tier to expose")
    parser.add_argument("--allow-writes", action="store_true", help="expose the metadata toolkit tools")
    parser.add_argument("--no-fuzzy", action="store_true", help="do not register the fuzzy matching functions")
    return parser


def _report(text: str) -> None:
    print(text, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, build the engine, and serve until stdin closes.

    The database is opened read-only through a percent-encoded ``file:`` URI,
    so no character in the path can change the open mode or create a file.

    Returns
    -------
    int
        0 after stdin closes, 1 when the engine cannot be built, 2 when the
        database file does not exist.
    """
    args = _parser().parse_args(argv)
    path = Path(args.sqlite).expanduser().resolve()
    if not path.is_file():
        _report(f"error: no SQLite database file at {path}")
        return 2
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, check_same_thread=False)) as connection:
        try:
            if not args.no_fuzzy:
                register_sqlite_functions(connection)
            engine = SqlRag(connection, metadata_root=args.metadata, cache_dir=args.cache, config=Config(allow_metadata_writes=args.allow_writes))
        except (SqlRagError, sqlite3.Error) as exc:
            _report(f"error: {exc}")
            return 1
        serve_stdio(engine, tier=args.tier, on_error=_report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
