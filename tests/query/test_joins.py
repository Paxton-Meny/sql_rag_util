"""Tests for join planning and measures."""

from __future__ import annotations

import unittest

from sql_rag_util.config import Limits
from sql_rag_util.dialects import load
from sql_rag_util.exceptions import LimitExceededError, QuerySpecError, SensitiveColumnError, UnknownRelationshipError
from sql_rag_util.executor import Executor
from sql_rag_util.query.aggregate import measure_sql
from sql_rag_util.query.joins import JoinPlan
from sql_rag_util.query.policy import ColumnPolicy
from sql_rag_util.query.spec import Measure
from sql_rag_util.schema.introspect import introspect
from sql_rag_util.schema.model import TableRef
from sql_rag_util.sql.render import render
from tests.support.fixture import fixture_connection


class JoinPlanTest(unittest.TestCase):
    """Paths add joins once, respect depth, and produce aliased references."""

    def setUp(self) -> None:
        conn = fixture_connection(self)
        self.dialect = load("sqlite")
        self.catalog = introspect(Executor(conn, "qmark"), self.dialect)
        self.policy = ColumnPolicy(sensitive={TableRef(None, "customers"): frozenset({"password_hash"})})

    def _plan(self, table: str = "orders", depth: int = 2) -> JoinPlan:
        return JoinPlan(self.catalog, self.policy, self.catalog.table(TableRef(None, table)), depth)

    def test_base_column_and_one_hop(self) -> None:
        """A bare column uses t0; a dotted path adds one LEFT JOIN and reuses it."""
        plan = self._plan()
        base = plan.resolve("status")
        self.assertEqual(plan.column_sql(self.dialect, base), '"t0"."status"')
        first = plan.resolve("customers_via_customer_id.name")
        second = plan.resolve("customers_via_customer_id.region")
        self.assertEqual((first.alias, second.alias), ("t1", "t1"))
        self.assertEqual(len(plan.steps), 1)
        self.assertFalse(plan.fans_out)
        self.assertEqual(
            render(plan.from_clause(self.dialect), "qmark")[0],
            'FROM "orders" AS "t0" LEFT JOIN "customers" AS "t1" ON "t0"."customer_id" = "t1"."id"',
        )

    def test_two_hops_composite_and_fan_out(self) -> None:
        """A two-hop path joins twice, composite keys produce two conditions, to_many fans out."""
        plan = self._plan("shipment_events")
        resolved = plan.resolve("shipments.orders.status")
        self.assertEqual(resolved.alias, "t2")
        text = render(plan.from_clause(self.dialect), "qmark")[0]
        self.assertIn('ON "t0"."order_id" = "t1"."order_id" AND "t0"."seq" = "t1"."seq"', text)
        self.assertFalse(plan.fans_out)
        reverse = self._plan("customers")
        reverse.resolve("orders_via_customer_id.amount")
        self.assertTrue(reverse.fans_out)

    def test_limits_and_refusals(self) -> None:
        """Depth, unknown relationships, and sensitive columns are refused."""
        with self.assertRaises(LimitExceededError):
            self._plan("shipment_events", depth=1).resolve("shipments.orders.status")
        with self.assertRaises(UnknownRelationshipError):
            self._plan().resolve("customer.name")
        with self.assertRaises(SensitiveColumnError):
            self._plan().resolve("customers_via_customer_id.password_hash")


class MeasureSqlTest(unittest.TestCase):
    """Measures render with aliases and kind gates."""

    def setUp(self) -> None:
        conn = fixture_connection(self)
        self.dialect = load("sqlite")
        self.catalog = introspect(Executor(conn, "qmark"), self.dialect)
        self.plan = JoinPlan(self.catalog, ColumnPolicy(), self.catalog.table(TableRef(None, "orders")), Limits().max_join_depth)

    def test_measures(self) -> None:
        """Each function renders as expected."""
        cases = {
            Measure("count"): 'COUNT(*) AS "count"',
            Measure("count", "notes"): 'COUNT("t0"."notes") AS "count_notes"',
            Measure("count_distinct", "status"): 'COUNT(DISTINCT "t0"."status") AS "count_distinct_status"',
            Measure("sum", "amount", "revenue"): 'SUM("t0"."amount") AS "revenue"',
            Measure("max", "created_at"): 'MAX("t0"."created_at") AS "max_created_at"',
        }
        for measure, expected in cases.items():
            with self.subTest(measure=measure.name):
                self.assertEqual(render(measure_sql(self.dialect, self.plan, measure), "qmark")[0], expected)

    def test_kind_gates(self) -> None:
        """sum and avg need numeric columns."""
        with self.assertRaises(QuerySpecError):
            measure_sql(self.dialect, self.plan, Measure("sum", "status"))
        with self.assertRaises(QuerySpecError):
            measure_sql(self.dialect, self.plan, Measure("avg", "notes"))


if __name__ == "__main__":
    unittest.main()
