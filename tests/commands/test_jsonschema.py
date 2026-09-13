"""Tests for JSON schema derivation and tool specs."""

from __future__ import annotations

import enum
import unittest
from dataclasses import dataclass, field
from typing import Literal

from sql_rag_util.commands.jsonschema import schema_for
from sql_rag_util.commands.spec import CommandResult, ToolSpec
from sql_rag_util.exceptions import ToolSpecError
from sql_rag_util.query.spec import Filter, QuerySpec


class Color(enum.StrEnum):
    RED = "red"
    BLUE = "blue"


@dataclass(frozen=True)
class Inner:
    name: str = field(metadata={"description": "A name."})


@dataclass(frozen=True)
class Args:
    table: str = field(metadata={"description": "Table."})
    limit: int | None = field(default=None, metadata={"description": "Limit."})
    tags: tuple[str, ...] = field(default=(), metadata={"description": "Tags."})
    mode: Literal["a", "b"] = field(default="a", metadata={"description": "Mode."})
    color: Color = field(default=Color.RED, metadata={"description": "Color."})
    inner: Inner | None = field(default=None, metadata={"description": "Inner."})
    value: str | int | tuple[str, ...] = field(default="", metadata={"description": "Value."})
    hidden: str = field(default="", init=False)


class SchemaForTest(unittest.TestCase):
    """Every supported annotation maps to a schema subset any framework accepts."""

    def test_supported_annotations(self) -> None:
        """Simple types, nullable unions, arrays, literals, enums, nested objects, and anyOf."""
        schema = schema_for(Args)
        props = schema["properties"]
        self.assertEqual(schema["required"], ["table"])
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("hidden", props)
        self.assertEqual(props["table"], {"type": "string", "description": "Table."})
        self.assertEqual(props["limit"]["type"], ["integer", "null"])
        self.assertEqual(props["tags"], {"type": "array", "items": {"type": "string"}, "description": "Tags."})
        self.assertEqual(props["mode"]["enum"], ["a", "b"])
        self.assertEqual(props["color"]["enum"], ["red", "blue"])
        self.assertEqual(props["inner"]["anyOf"][0], {"type": "null"})
        self.assertEqual(props["inner"]["anyOf"][1]["properties"]["name"]["type"], "string")
        self.assertEqual(props["value"]["anyOf"][0], {"type": ["string", "integer"]})
        self.assertEqual(props["value"]["anyOf"][1]["type"], "array")

    def test_query_spec_schema(self) -> None:
        """The real query spec derives, with the filter value as scalar or array."""
        schema = schema_for(QuerySpec)
        self.assertEqual(schema["required"], ["table"])
        filters = schema["properties"]["filters"]["items"]
        self.assertEqual(filters["required"], ["column", "op"])
        self.assertIn("since_days", filters["properties"]["op"]["enum"])
        self.assertEqual(filters["properties"]["value"]["anyOf"][0]["type"], ["string", "integer", "number", "boolean", "null"])
        self.assertNotIn("names", schema["properties"])
        self.assertEqual(schema_for(Filter)["properties"]["column"]["type"], "string")

    def test_rejections(self) -> None:
        """Missing descriptions and unsupported annotations fail at derivation time."""

        @dataclass(frozen=True)
        class NoDescription:
            a: str

        @dataclass(frozen=True)
        class BadTuple:
            a: tuple[str, int] = field(default=("", 0), metadata={"description": "x"})

        @dataclass(frozen=True)
        class Dict:
            a: dict[str, str] = field(default_factory=dict, metadata={"description": "x"})

        for bad in (NoDescription, BadTuple, Dict, int):
            with self.subTest(bad=bad):
                with self.assertRaises(ToolSpecError):
                    schema_for(bad)


class ToolSpecTest(unittest.TestCase):
    """Specs validate at construction and answer tier membership."""

    def test_spec(self) -> None:
        """A spec derives its schema once and reports tier inclusion."""
        spec = ToolSpec("t", "T", "Use it.", Args, lambda engine, args: CommandResult({}, ""), tier="minimal")
        self.assertEqual(spec.input_schema()["required"], ["table"])
        self.assertTrue(spec.included_in("minimal"))
        self.assertTrue(spec.included_in("full"))
        standard = ToolSpec("s", "S", "Use it.", Args, lambda engine, args: CommandResult({}, ""))
        self.assertFalse(standard.included_in("minimal"))
        with self.assertRaises(ToolSpecError):
            standard.included_in("huge")
        with self.assertRaises(ToolSpecError):
            ToolSpec("x", "X", " ", Args, lambda engine, args: CommandResult({}, ""))
        with self.assertRaises(ToolSpecError):
            ToolSpec("x", "X", "d", Args, lambda engine, args: CommandResult({}, ""), tier="big")


if __name__ == "__main__":
    unittest.main()
