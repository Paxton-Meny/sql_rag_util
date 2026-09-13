"""Run the MCP server on a SQLite database: ``python -m sql_rag_util.mcp --sqlite app.db``.

Other databases are served by constructing :class:`~sql_rag_util.engine.SqlRag`
with the driver's connection and calling :func:`~sql_rag_util.mcp.server.serve_stdio`.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

import sql_rag_util
from sql_rag_util.commands.spec import TIERS
from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
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


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, build the engine, and serve until stdin closes."""
    args = _parser().parse_args(argv)
    uri = f"file:{args.sqlite}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
    if not args.no_fuzzy:
        register_sqlite_functions(connection)
    engine = SqlRag(connection, metadata_root=args.metadata, cache_dir=args.cache, config=Config(allow_metadata_writes=args.allow_writes))
    serve_stdio(engine, tier=args.tier, version=sql_rag_util.__version__, on_error=lambda text: print(text, file=sys.stderr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
