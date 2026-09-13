"""Tests for the MCP stdio server, in process and as a subprocess."""

from __future__ import annotations

import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from sql_rag_util.engine import SqlRag
from sql_rag_util.mcp.server import PROTOCOL_VERSION, handle_message, serve_stdio
from tests.support.fixture import FIXTURE_SQL, build_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "metadata"
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def _request(identifier: int, method: str, params: dict | None = None) -> str:  # type: ignore[type-arg]
    return json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params or {}})


class HandleMessageTest(unittest.TestCase):
    """Each method answers per JSON-RPC, and notifications are silent."""

    def setUp(self) -> None:
        conn = build_fixture()
        self.addCleanup(conn.close)
        self.engine = SqlRag(conn, metadata_root=FIXTURES)

    def test_methods(self) -> None:
        """initialize, ping, tools/list, tools/call, unknown method, bad request."""
        init = handle_message(self.engine, json.loads(_request(1, "initialize", {"protocolVersion": PROTOCOL_VERSION})))
        self.assertEqual(init["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertIn("get_context", init["result"]["instructions"])
        self.assertIsNone(handle_message(self.engine, {"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(handle_message(self.engine, json.loads(_request(2, "ping")))["result"], {})
        tools = handle_message(self.engine, json.loads(_request(3, "tools/list")))["result"]["tools"]
        self.assertIn("query", [t["name"] for t in tools])
        call = handle_message(self.engine, json.loads(_request(4, "tools/call", {"name": "query", "arguments": {"table": "orders", "measures": [{"fn": "count"}]}})))
        self.assertEqual(call["result"]["structuredContent"]["rows"], [[4]])
        bad = handle_message(self.engine, json.loads(_request(5, "tools/call", {"name": 7})))
        self.assertEqual(bad["error"]["code"], -32602)
        self.assertEqual(handle_message(self.engine, json.loads(_request(6, "nope")))["error"]["code"], -32601)
        self.assertEqual(handle_message(self.engine, {"id": 7})["error"]["code"], -32600)

    def test_serve_stdio_streams(self) -> None:
        """Lines in, one response line per request out; parse errors are answered too."""
        stdin = io.StringIO(_request(1, "ping") + "\n\nnot json\n" + json.dumps({"jsonrpc": "2.0", "method": "notifications/x"}) + "\n")
        stdout = io.StringIO()
        serve_stdio(self.engine, stdin=stdin, stdout=stdout)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(lines[0]["result"], {})
        self.assertEqual(lines[1]["error"]["code"], -32700)
        self.assertEqual(len(lines), 2)


class SubprocessTest(unittest.TestCase):
    """The module entry point serves a SQLite file read-only."""

    def test_entry_point(self) -> None:
        """A real subprocess answers initialize and a tools/call."""
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "shop.db"
            import sqlite3

            conn = sqlite3.connect(db)
            conn.executescript(FIXTURE_SQL)
            conn.close()
            requests = _request(1, "initialize", {"protocolVersion": PROTOCOL_VERSION}) + "\n" + _request(2, "tools/call", {"name": "search_rows", "arguments": {"table": "customers", "term": "acme"}}) + "\n"
            completed = subprocess.run(
                [sys.executable, "-m", "sql_rag_util.mcp", "--sqlite", str(db), "--metadata", str(FIXTURES), "--cache", tmp],
                input=requests, capture_output=True, text=True, cwd=ROOT, timeout=60, check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        lines = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "sql_rag_util")
        self.assertEqual(lines[1]["result"]["structuredContent"]["rows"][0][1], "Acme Corp")


if __name__ == "__main__":
    unittest.main()
