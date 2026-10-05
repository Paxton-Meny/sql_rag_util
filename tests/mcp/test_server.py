"""Tests for the MCP stdio server, in process and as a subprocess."""

from __future__ import annotations

import io
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import sql_rag_util
from sql_rag_util.engine import SqlRag
from sql_rag_util.mcp.server import PROTOCOL_VERSION, handle_message, serve_stdio
from tests.support.fixture import FIXTURE_SQL, build_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "metadata"
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def _request(identifier: int, method: str, params: dict[str, object] | None = None) -> str:
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

    def test_version_defaults_to_the_package(self) -> None:
        """serverInfo reports the installed package version unless told otherwise."""
        init = handle_message(self.engine, json.loads(_request(1, "initialize")))
        self.assertEqual(init["result"]["serverInfo"]["version"], sql_rag_util.__version__)

    def test_handler_failures_are_internal_errors(self) -> None:
        """An exception while handling a request is reported and answered with -32603; serving continues."""
        stdin = io.StringIO(_request(1, "ping") + "\n" + _request(2, "ping") + "\n")
        stdout = io.StringIO()
        reported: list[str] = []
        with mock.patch("sql_rag_util.mcp.server.handle_message", side_effect=[RuntimeError("boom"), {"jsonrpc": "2.0", "id": 2, "result": {}}]):
            serve_stdio(self.engine, stdin=stdin, stdout=stdout, on_error=reported.append)
        first, second = (json.loads(line) for line in stdout.getvalue().splitlines())
        self.assertEqual((first["id"], first["error"]["code"], first["error"]["message"]), (1, -32603, "internal error: RuntimeError"))
        self.assertEqual(second["result"], {})
        self.assertEqual(reported, ["RuntimeError: boom"])

    def test_serve_stdio_streams(self) -> None:
        """Lines in, one response line per request out; parse errors are answered too."""
        stdin = io.StringIO(_request(1, "ping") + "\n\nnot json\n" + json.dumps({"jsonrpc": "2.0", "method": "notifications/x"}) + "\n")
        stdout = io.StringIO()
        serve_stdio(self.engine, stdin=stdin, stdout=stdout)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(lines[0]["result"], {})
        self.assertEqual(lines[1]["error"]["code"], -32700)
        self.assertEqual(len(lines), 2)


def _database(path: pathlib.Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(FIXTURE_SQL)
    conn.close()


def _serve(*args: str, requests: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "sql_rag_util.mcp", *args], input=requests, capture_output=True, text=True, cwd=ROOT, timeout=60, check=False)


class SubprocessTest(unittest.TestCase):
    """The module entry point serves a SQLite file read-only."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.dir = self.tmp / "db"
        self.dir.mkdir()

    def test_entry_point(self) -> None:
        """A real subprocess answers initialize and a tools/call."""
        db = self.dir / "shop.db"
        _database(db)
        requests = _request(1, "initialize", {"protocolVersion": PROTOCOL_VERSION}) + "\n" + _request(2, "tools/call", {"name": "search_rows", "arguments": {"table": "customers", "term": "acme"}}) + "\n"
        completed = _serve("--sqlite", str(db), "--metadata", str(FIXTURES), "--cache", str(self.tmp / "cache"), requests=requests)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        lines = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(lines[0]["result"]["serverInfo"], {"name": "sql_rag_util", "version": sql_rag_util.__version__})
        self.assertEqual(lines[1]["result"]["structuredContent"]["rows"][0][1], "Acme Corp")

    def test_uri_characters_in_the_path_are_plain_characters(self) -> None:
        """A path containing '#', '?', '%', and a space opens that file read-only and creates nothing else."""
        db = self.dir / "shop #1?mode=rwc%20.db"
        _database(db)
        before = db.read_bytes()
        completed = _serve("--sqlite", str(db), requests=_request(1, "tools/call", {"name": "list_tables", "arguments": {}}) + "\n")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        tables = json.loads(completed.stdout)["result"]["structuredContent"]["tables"]
        self.assertEqual(len(tables), 5)
        self.assertEqual([p.name for p in self.dir.iterdir()], [db.name])
        self.assertEqual(db.read_bytes(), before)

    def test_missing_or_broken_databases_fail_cleanly(self) -> None:
        """No file exits 2 and creates none; a file that is not a database exits 1; neither prints a traceback."""
        missing = _serve("--sqlite", str(self.dir / "absent.db"))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("error: no SQLite database file at", missing.stderr)
        self.assertEqual(list(self.dir.iterdir()), [])
        junk = self.dir / "junk.db"
        junk.write_text("not a database")
        broken = _serve("--sqlite", str(junk))
        self.assertEqual(broken.returncode, 1)
        self.assertTrue(broken.stderr.startswith("error: "), broken.stderr)
        for completed in (missing, broken):
            self.assertNotIn("Traceback", completed.stderr)


if __name__ == "__main__":
    unittest.main()
