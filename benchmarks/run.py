"""Measure bytes per tool output and tool calls per scripted question.

Run from the repository root: ``python3 -m benchmarks.run``. The numbers are
copied into ``docs/context-cost.md`` when they move.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
from typing import Any

from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
from sql_rag_util.search.sqlite_functions import register_sqlite_functions
from tests.support.fixture import build_fixture

__all__ = ["QUESTIONS", "run", "main"]

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "metadata"

QUESTIONS: tuple[tuple[str, tuple[tuple[str, dict[str, Any]], ...]], ...] = (
    (
        "Which open orders does Acme Corp have?",
        (
            ("get_context", {"question": "Which open orders does Acme Corp have?"}),
            ("query", {"table": "orders", "columns": ["id", "amount", "customer.name"], "filters": [{"column": "status", "op": "eq", "value": "open"}, {"column": "customer.name", "op": "eq", "value": "Acme Corp"}]}),
        ),
    ),
    (
        "Revenue by region for active orders",
        (
            ("get_context", {"question": "Revenue by region for active orders"}),
            ("query", {"table": "orders", "group_by": ["customer.region"], "measures": [{"fn": "measure", "column": "revenue"}], "concepts": ["active"]}),
        ),
    ),
    (
        "Find the customer called John Smith",
        (
            ("get_context", {"question": "Find the customer called John Smith"}),
            ("search_rows", {"table": "customers", "term": "John Smith"}),
        ),
    ),
    (
        "How many orders per status?",
        (
            ("query", {"table": "orders", "group_by": ["status"], "measures": [{"fn": "count"}]}),
        ),
    ),
)


def run() -> list[dict[str, Any]]:
    """Return one record per scripted question with byte counts for both formats."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "meta"
        shutil.copytree(FIXTURES, root)
        connection = build_fixture()
        register_sqlite_functions(connection)
        engine = SqlRag(connection, metadata_root=root, config=Config())
        records = []
        for question, calls in QUESTIONS:
            json_bytes = text_bytes = 0
            for name, arguments in calls:
                envelope = engine.dispatch(name, arguments)
                if "error" in envelope:
                    raise RuntimeError(f"{name} failed: {envelope['error']}")
                json_bytes += len(json.dumps(envelope, separators=(",", ":")).encode())
                text_bytes += len(engine.dispatch_text(name, arguments).encode())
            records.append({"question": question, "calls": len(calls), "json_bytes": json_bytes, "compact_bytes": text_bytes})
        definitions = sum(len(json.dumps({"name": s.name, "description": s.description, "input_schema": s.input_schema()}).encode()) for s in engine.tool_specs())
        records.append({"question": "tool definitions (standard tier)", "calls": 0, "json_bytes": definitions, "compact_bytes": definitions})
        records.append({"question": "instructions block", "calls": 0, "json_bytes": len(engine.instructions().encode()), "compact_bytes": len(engine.instructions().encode())})
        connection.close()
        return records


def main() -> None:
    """Print the records as a Markdown table."""
    print("| Question | Calls | JSON bytes | Compact bytes |")
    print("| --- | --- | --- | --- |")
    for record in run():
        print(f"| {record['question']} | {record['calls']} | {record['json_bytes']} | {record['compact_bytes']} |")


if __name__ == "__main__":
    main()
