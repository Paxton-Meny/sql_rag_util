"""Tests for the framework adapters."""

from __future__ import annotations

import unittest
from typing import Any

from sql_rag_util.adapters import anthropic, mcp, openai
from sql_rag_util.engine import SqlRag
from tests.support.fixture import FIXTURES, fixture_connection


def _walk(schema: dict[str, Any]) -> list[dict[str, Any]]:
    found = [schema]
    for member in schema.get("anyOf", []):
        found += _walk(member)
    for member in schema.get("properties", {}).values():
        found += _walk(member)
    if "items" in schema:
        found += _walk(schema["items"])
    return found


class AdapterTest(unittest.TestCase):
    """One spec yields each framework's shape."""

    def setUp(self) -> None:
        conn = fixture_connection(self)
        self.engine = SqlRag(conn, metadata_root=FIXTURES)

    def test_anthropic(self) -> None:
        """Entries carry input_schema and examples; the minimal tier is smaller."""
        tools = anthropic.tool_definitions(self.engine)
        by_name = {t["name"]: t for t in tools}
        self.assertEqual(by_name["query"]["input_schema"]["required"], ["table"])
        self.assertTrue(by_name["query"]["input_examples"])
        self.assertEqual(len(anthropic.tool_definitions(self.engine, tier="minimal")), 2)

    def test_openai_strict(self) -> None:
        """Every object lists all properties as required, optional ones nullable, no additional properties."""
        tools = openai.tool_definitions(self.engine)
        query = next(t for t in tools if t["function"]["name"] == "query")
        self.assertTrue(query["function"]["strict"])
        for obj in _walk(query["function"]["parameters"]):
            if obj.get("type") == "object" and "properties" in obj:
                with self.subTest(properties=list(obj["properties"])):
                    self.assertEqual(obj["required"], list(obj["properties"]))
                    self.assertFalse(obj["additionalProperties"])
        params = query["function"]["parameters"]["properties"]
        self.assertIn("null", params["limit"]["type"])
        self.assertEqual(params["table"]["type"], "string")
        self.assertIn("null", params["group_by"]["type"])
        self.assertTrue(any(m.get("type") == "null" for m in params["columns"]["anyOf"]))

    def test_mcp(self) -> None:
        """Definitions carry annotations; calls return text plus structured content, errors flagged."""
        tools = mcp.tool_definitions(self.engine)
        query = next(t for t in tools if t["name"] == "query")
        self.assertEqual(query["annotations"]["readOnlyHint"], True)
        self.assertIn("inputSchema", query)
        result = mcp.call_tool(self.engine, "query", {"table": "orders", "measures": [{"fn": "count"}]})
        self.assertEqual(result["structuredContent"]["rows"], [[4]])
        self.assertIn('"rows":[[4]]', result["content"][0]["text"])
        compact = mcp.call_tool(self.engine, "query", {"table": "orders", "measures": [{"fn": "count"}], "format": "compact"})
        self.assertTrue(compact["content"][0]["text"].startswith("count\n4\n"))
        error = mcp.call_tool(self.engine, "query", {"table": "ordr"})
        self.assertTrue(error["isError"])
        self.assertIn("Try: orders", error["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
