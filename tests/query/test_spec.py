"""Tests for query spec validation."""

from __future__ import annotations

import unittest

from sql_rag_util.exceptions import QuerySpecError
from sql_rag_util.query.spec import AggregateFn, Filter, FilterOp, Measure, Order, QuerySpec


class FilterTest(unittest.TestCase):
    """Filters validate operator and value shape."""

    def test_operators_accept_matching_values(self) -> None:
        """Each operator family accepts its value shape and lists become tuples."""
        self.assertEqual(Filter("a", "eq", 1).op, FilterOp.EQ)
        self.assertEqual(Filter("a", "in", [1, 2]).value, (1, 2))
        self.assertEqual(Filter("a.b", "between", [1, 2]).value, (1, 2))
        self.assertIsNone(Filter("a", "is_null").value)
        self.assertEqual(Filter("a", "since_days", 30).value, 30)

    def test_rejections(self) -> None:
        """Bad operators, paths, and value shapes raise QuerySpecError."""
        cases = [
            ("a", "like", "x"), ("a b", "eq", 1), ("a", "eq", None), ("a", "eq", [1]), ("a", "in", []),
            ("a", "in", [[1]]), ("a", "between", [1]), ("a", "is_null", 1), ("a", "since_days", -1),
            ("a", "since_days", True), ("a", "since_days", "30"),
        ]
        for column, op, value in cases:
            with self.subTest(op=op, value=value):
                with self.assertRaises(QuerySpecError):
                    Filter(column, op, value)
        with self.assertRaises(QuerySpecError) as ctx:
            Filter("a", "like", "x")
        self.assertIn("contains", ctx.exception.suggestions)


class MeasureAndOrderTest(unittest.TestCase):
    """Measures and orders validate their pieces and derive names."""

    def test_measure_names(self) -> None:
        """Names default to fn or fn_column and honor an alias."""
        self.assertEqual(Measure("count").name, "count")
        self.assertEqual(Measure("sum", "amount").name, "sum_amount")
        self.assertEqual(Measure("avg", "customer.age").name, "avg_customer_age")
        self.assertEqual(Measure("sum", "amount", "revenue").name, "revenue")
        self.assertEqual(Measure("count_distinct", "x").fn, AggregateFn.COUNT_DISTINCT)

    def test_measure_and_order_rejections(self) -> None:
        """Unknown functions, missing columns, bad aliases, and bad directions are refused."""
        for args in (("median", "a"), ("sum",), ("sum", "a", "Bad Alias")):
            with self.subTest(args=args):
                with self.assertRaises(QuerySpecError):
                    Measure(*args)
        with self.assertRaises(QuerySpecError):
            Order("a", "up")
        self.assertEqual(Order("a", "desc").direction, "desc")


class QuerySpecTest(unittest.TestCase):
    """Specs validate their combination rules."""

    def test_valid_shapes(self) -> None:
        """Rows, counts, distincts, and aggregates all construct."""
        rows = QuerySpec("orders", columns=["id", "customer.name"], limit=5)
        self.assertEqual(rows.columns, ("id", "customer.name"))
        self.assertFalse(rows.is_aggregate)
        count = QuerySpec("orders", measures=[Measure("count")])
        self.assertTrue(count.is_aggregate)
        distinct = QuerySpec("orders", group_by=["status"], measures=[Measure("count")], order=[Order("count", "desc")])
        self.assertEqual(distinct.names, ("count",))

    def test_rejections(self) -> None:
        """Conflicting fields, bad limits, formats, and duplicate measure names are refused."""
        with self.assertRaises(QuerySpecError):
            QuerySpec("orders", columns=["id"], group_by=["status"])
        with self.assertRaises(QuerySpecError):
            QuerySpec("orders", columns=["id"], measures=[Measure("count")])
        with self.assertRaises(QuerySpecError):
            QuerySpec("orders", limit=0)
        with self.assertRaises(QuerySpecError):
            QuerySpec("orders", format="yaml")
        with self.assertRaises(QuerySpecError):
            QuerySpec("orders", measures=[Measure("count"), Measure("count", "id", "count")])
        with self.assertRaises(QuerySpecError):
            QuerySpec("orders", concepts=["Active"])


if __name__ == "__main__":
    unittest.main()
