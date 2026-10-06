"""The README's examples, run as written in the setting the README describes."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from tests.support.fixture import FIXTURE_SQL, FIXTURES

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _blocks(language: str) -> list[str]:
    return re.findall(rf"```{language}\n(.*?)```", README, re.S)


class ReadmeTest(unittest.TestCase):
    """A shop.db and sqlrag_metadata/ in the working directory, then every fenced example."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cwd = pathlib.Path(tmp.name)
        connection = sqlite3.connect(self.cwd / "shop.db")
        connection.executescript(FIXTURE_SQL)
        connection.close()
        shutil.copytree(FIXTURES, self.cwd / "sqlrag_metadata")

    def test_python_examples_run_in_order(self) -> None:
        """The SDK example prints Acme's open order, and the framework example builds definitions from its engine."""
        namespace: dict[str, object] = {}
        printed = io.StringIO()
        previous = pathlib.Path.cwd()
        os.chdir(self.cwd)
        self.addCleanup(os.chdir, previous)
        with contextlib.redirect_stdout(printed):
            for number, code in enumerate(_blocks("python")):
                exec(compile(code, f"README.md python block {number + 1}", "exec"), namespace)
        connection = namespace["connection"]
        assert isinstance(connection, sqlite3.Connection)
        connection.close()
        self.assertEqual(printed.getvalue(), "['id', 'amount', 'customer.name'] [[10, 19.99, 'Acme Corp']] ()\n")
        self.assertEqual([t["name"] for t in namespace["tools"]], ["get_context", "query", "describe_table", "list_tables", "search_rows"])
        self.assertTrue(namespace["system_prompt"])

    def test_mcp_command_serves(self) -> None:
        """The shell example starts a server that answers initialize and lists the tools."""
        (command,) = [line for block in _blocks("bash") for line in block.splitlines() if "sql_rag_util.mcp" in line]
        argv = [sys.executable if part == "python3" else part for part in shlex.split(command)]
        requests = "".join(json.dumps({"jsonrpc": "2.0", "id": i, "method": m, "params": {}}) + "\n" for i, m in ((1, "initialize"), (2, "tools/list")))
        environment = {**os.environ, "PYTHONPATH": str(ROOT)}
        completed = subprocess.run(argv, input=requests, capture_output=True, text=True, cwd=self.cwd, env=environment, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        initialized, listed = (json.loads(line) for line in completed.stdout.splitlines())
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "sql_rag_util")
        self.assertIn("search_rows", [t["name"] for t in listed["result"]["tools"]])


if __name__ == "__main__":
    unittest.main()
