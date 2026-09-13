"""Tests for argument building, the registry, and dispatch envelopes."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from sql_rag_util.commands.arguments import build_arguments
from sql_rag_util.commands.dispatch import Dispatcher
from sql_rag_util.commands.registry import Registry
from sql_rag_util.commands.spec import CommandResult, ToolSpec
from sql_rag_util.exceptions import ArgumentError, QuerySpecError, ToolSpecError, UnknownTableError, UnknownToolError
from sql_rag_util.query.spec import Filter, FilterOp, QuerySpec


@dataclass(frozen=True)
class EchoArgs:
    table: str = field(metadata={"description": "Table."})
    limit: int | None = field(default=None, metadata={"description": "Limit."})
    filters: tuple[Filter, ...] = field(default=(), metadata={"description": "Filters."})


class FakeEngine:
    schema_version = "abc123"


def _echo(engine: FakeEngine, args: EchoArgs) -> CommandResult:
    return CommandResult({"table": args.table, "limit": args.limit, "filters": len(args.filters)}, f"echo {args.table}", truncated=args.limit == 1, notes=("hi",))


def _boom(engine: FakeEngine, args: EchoArgs) -> CommandResult:
    raise UnknownTableError(f"unknown table {args.table!r}", suggestions=("orders",))


ECHO = ToolSpec("echo", "Echo", "Echoes.", EchoArgs, _echo, tier="minimal")
BOOM = ToolSpec("boom", "Boom", "Fails.", EchoArgs, _boom)
WRITE = ToolSpec("write", "Write", "Writes.", EchoArgs, _echo, tier="full", mutating=True)


class BuildArgumentsTest(unittest.TestCase):
    """JSON shapes become dataclasses, and every mismatch names its path."""

    def test_nested_conversion(self) -> None:
        """Lists become tuples, dicts become nested dataclasses, enums parse."""
        args = build_arguments(EchoArgs, {"table": "orders", "filters": [{"column": "a", "op": "eq", "value": 1}]})
        self.assertEqual(args.filters[0], Filter("a", FilterOp.EQ, 1))
        spec = build_arguments(QuerySpec, {"table": "orders", "measures": [{"fn": "count"}], "group_by": ["status"], "order": [{"by": "count", "direction": "desc"}]})
        self.assertEqual(spec.names, ("count",))

    def test_rejections(self) -> None:
        """Wrong shapes, unknown keys, and missing keys raise ArgumentError with paths."""
        cases = {
            "not an object": "x",
            "unknown key": {"table": "t", "limt": 3},
            "missing required": {"limit": 3},
            "wrong type": {"table": 3},
            "bool for int": {"table": "t", "limit": True},
            "bad enum": {"table": "t", "filters": [{"column": "a", "op": "like", "value": 1}]},
            "bad literal": {"table": "t", "format": "yaml"},
            "list expected": {"table": "t", "filters": {"column": "a"}},
        }
        for label, data in cases.items():
            with self.subTest(label=label):
                with self.assertRaises((ArgumentError, QuerySpecError)):
                    build_arguments(QuerySpec if label == "bad literal" else EchoArgs, data)
        with self.assertRaises(ArgumentError) as ctx:
            build_arguments(EchoArgs, {"table": "t", "limt": 3})
        self.assertEqual(ctx.exception.suggestions, ("limit",))
        self.assertIn("arguments.filters[0].op", str(self._error({"table": "t", "filters": [{"column": "a", "op": 7}]})))

    @staticmethod
    def _error(data: object) -> Exception:
        try:
            build_arguments(EchoArgs, data)
        except ArgumentError as exc:
            return exc
        raise AssertionError("expected an error")


class RegistryAndDispatchTest(unittest.TestCase):
    """Tiers and mutation gates filter tools; envelopes carry version, notes, and errors."""

    def setUp(self) -> None:
        self.registry = Registry((ECHO, BOOM, WRITE))

    def test_registry_filters(self) -> None:
        """Tier and mutating filters apply to listing and lookup; duplicates are refused."""
        self.assertEqual([s.name for s in self.registry.specs(tier="minimal")], ["echo"])
        self.assertEqual([s.name for s in self.registry.specs(tier="full")], ["echo", "boom"])
        self.assertEqual([s.name for s in self.registry.specs(tier="full", include_mutating=True)], ["echo", "boom", "write"])
        with self.assertRaises(UnknownToolError) as ctx:
            self.registry.get("ecoh", tier="minimal")
        self.assertEqual(ctx.exception.suggestions, ("echo",))
        with self.assertRaises(UnknownToolError):
            self.registry.get("write", include_mutating=False)
        with self.assertRaises(ToolSpecError):
            self.registry.register(ECHO)

    def test_envelopes(self) -> None:
        """Success, package errors, argument errors, and compact text all render."""
        dispatcher = Dispatcher(self.registry, FakeEngine(), tier="standard")
        self.assertEqual(dispatcher.call("echo", {"table": "orders", "limit": 1}), {"schema_version": "abc123", "truncated": True, "notes": ["hi"], "table": "orders", "limit": 1, "filters": 0})
        error = dispatcher.call("boom", {"table": "ordr"})
        self.assertEqual(error, {"error": {"type": "UnknownTableError", "message": "unknown table 'ordr'", "suggestions": ["orders"]}})
        self.assertEqual(dispatcher.call("echo", {"table": 1})["error"]["type"], "ArgumentError")
        self.assertEqual(dispatcher.call("write", {"table": "t"})["error"]["type"], "UnknownToolError")
        text = dispatcher.call_text("echo", {"table": "orders", "limit": 1})
        self.assertEqual(text, "echo orders\nnote: hi\nnote: result truncated; narrow with filters or lower the limit\nschema_version: abc123")
        self.assertEqual(dispatcher.call_text("boom", {"table": "x"}), "error UnknownTableError: unknown table 'x' (try: orders)")
        self.assertIn('"schema_version":"abc123"', dispatcher.call_json("echo", {"table": "t"}))


if __name__ == "__main__":
    unittest.main()
