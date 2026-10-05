"""Tests for query compilation: golden SQL per dialect and live SQLite results."""

from __future__ import annotations

import datetime as dt
import unittest

from sql_rag_util.config import Limits
from sql_rag_util.dialects import load
from sql_rag_util.exceptions import LimitExceededError, SensitiveColumnError, UnknownColumnError
from sql_rag_util.executor import Executor
from sql_rag_util.query.compile import compile_query
from sql_rag_util.query.policy import ColumnPolicy
from sql_rag_util.query.spec import Filter, Measure, Order, QuerySpec
from sql_rag_util.schema.introspect import introspect
from sql_rag_util.schema.model import TableRef
from sql_rag_util.sql.render import render
from tests.support.fixture import build_fixture

CUSTOMERS = TableRef(None, "customers")
POLICY = ColumnPolicy(hidden={CUSTOMERS: frozenset({"password_hash"})}, sensitive={CUSTOMERS: frozenset({"email"})})
NOW = dt.datetime(2026, 9, 13, tzinfo=dt.timezone.utc)


class CompileTest(unittest.TestCase):
    """Specs compile to one bounded, ordered statement."""

    def setUp(self) -> None:
        self.conn = build_fixture()
        self.addCleanup(self.conn.close)
        self.executor = Executor(self.conn, "qmark")
        self.catalog = introspect(self.executor, load("sqlite"))
        self.limits = Limits()

    def _compile(self, spec: QuerySpec, dialect: str = "sqlite", **kw):
        return compile_query(load(dialect), self.catalog, POLICY, spec, self.limits, now=NOW, **kw)

    def _run(self, spec: QuerySpec):
        compiled = self._compile(spec)
        return compiled, self.executor.fetch(compiled.statement, command="query", limit=compiled.limit)

    def test_rows_default_columns_and_order(self) -> None:
        """No columns selects every selectable column, ordered by primary key, with limit plus one bound."""
        compiled, fetched = self._run(QuerySpec("customers", limit=2))
        self.assertEqual(compiled.columns, ("id", "name", "region"))
        self.assertEqual(
            render(compiled.statement, "qmark"),
            ('SELECT "t0"."id" AS "id", "t0"."name" AS "name", "t0"."region" AS "region" FROM "customers" AS "t0" ORDER BY "t0"."id" LIMIT ?', (3,)),
        )
        self.assertEqual(fetched.rows, ((1, "Acme Corp", "north"), (2, "Jon Smyth", "south")))
        self.assertTrue(fetched.truncated)

    def test_join_filter_and_dotted_output_names(self) -> None:
        """Dotted columns join, appear under their path, and filters bind values."""
        spec = QuerySpec("orders", columns=["id", "customers_via_customer_id.name"], filters=[Filter("status", "in", ["open", "paid"]), Filter("customers_via_customer_id.region", "eq", "north")])
        compiled, fetched = self._run(spec)
        self.assertEqual(compiled.columns, ("id", "customers_via_customer_id.name"))
        self.assertEqual(fetched.rows, ((10, "Acme Corp"), (11, "Acme Corp")))
        self.assertEqual(compiled.notes, ())

    def test_count_distinct_and_aggregate_idioms(self) -> None:
        """Counts return one row; group_by with count is the distinct idiom; measures order desc by default."""
        _, count = self._run(QuerySpec("orders", measures=[Measure("count")]))
        self.assertEqual(count.rows, ((4,),))
        compiled, distinct = self._run(QuerySpec("orders", group_by=["status"], measures=[Measure("count")]))
        self.assertIn('GROUP BY "t0"."status" ORDER BY "count" DESC', render(compiled.statement, "qmark")[0])
        self.assertEqual(len(distinct.rows), 4)
        compiled, revenue = self._run(QuerySpec("orders", group_by=["customers_via_customer_id.region"], measures=[Measure("sum", "amount", "revenue")], order=[Order("revenue", "desc")]))
        self.assertEqual(compiled.columns, ("customers_via_customer_id.region", "revenue"))
        self.assertEqual(revenue.rows[0], ("north", 269.99))

    def test_since_days_and_extra_filters(self) -> None:
        """since_days binds a computed timestamp; extra filters are AND-ed in."""
        spec = QuerySpec("orders", columns=["id"], filters=[Filter("created_at", "since_days", 30)])
        compiled, fetched = self._run(spec)
        self.assertEqual(render(compiled.statement, "qmark")[1], ("2026-08-14 00:00:00", 51))
        self.assertEqual(fetched.rows, ((10,), (11,), (12,)))
        scoped = self._compile(spec, extra_filters=(Filter("status", "eq", "open"),))
        text, params = render(scoped.statement, "qmark")
        self.assertIn('WHERE ("t0"."created_at" >= ?) AND ("t0"."status" = ?)', text)
        self.assertEqual(params, ("2026-08-14 00:00:00", "open", 51))

    def test_other_dialect_goldens(self) -> None:
        """The same spec renders with each dialect's quoting and limit form."""
        spec = QuerySpec("orders", columns=["id", "customers_via_customer_id.name"], filters=[Filter("status", "eq", "open")], limit=3)
        goldens = {
            "mysql": ("SELECT `t0`.`id` AS `id`, `t1`.`name` AS `customers_via_customer_id.name` FROM `orders` AS `t0` LEFT JOIN `customers` AS `t1` ON `t0`.`customer_id` = `t1`.`id` WHERE (`t0`.`status` = %s) ORDER BY `t0`.`id` LIMIT %s", ("open", 4)),
            "mssql": ("SELECT TOP (?) [t0].[id] AS [id], [t1].[name] AS [customers_via_customer_id.name] FROM [orders] AS [t0] LEFT JOIN [customers] AS [t1] ON [t0].[customer_id] = [t1].[id] WHERE ([t0].[status] = ?) ORDER BY [t0].[id]", (4, "open")),
            "postgres": ('SELECT "t0"."id" AS "id", "t1"."name" AS "customers_via_customer_id.name" FROM "orders" AS "t0" LEFT JOIN "customers" AS "t1" ON "t0"."customer_id" = "t1"."id" WHERE ("t0"."status" = %s) ORDER BY "t0"."id" LIMIT %s', ("open", 4)),
        }
        for dialect, expected in goldens.items():
            with self.subTest(dialect=dialect):
                compiled = self._compile(spec, dialect)
                self.assertEqual(render(compiled.statement, load(dialect).default_paramstyle), expected)

    def test_notes_and_refusals(self) -> None:
        """Fan-out is noted, caps and sensitive columns are refused, and no statement contains a star."""
        compiled = self._compile(QuerySpec("customers", columns=["name", "orders_via_customer_id.amount"]))
        self.assertEqual(len(compiled.notes), 1)
        self.assertNotIn("*", render(compiled.statement, "qmark")[0])
        with self.assertRaises(LimitExceededError):
            self._compile(QuerySpec("customers", limit=501))
        with self.assertRaises(LimitExceededError):
            self._compile(QuerySpec("orders", filters=[Filter("id", "eq", i) for i in range(11)]))
        with self.assertRaises(SensitiveColumnError):
            self._compile(QuerySpec("customers", filters=[Filter("email", "starts_with", "a")]))
        with self.assertRaises(UnknownColumnError):
            self._compile(QuerySpec("customers", group_by=["password_hash"], measures=[Measure("count")]))
        with self.assertRaises(LimitExceededError):
            self._compile(QuerySpec("orders", group_by=["status", "customer_id", "id"], measures=[Measure("count")]))


if __name__ == "__main__":
    unittest.main()
