"""Tests for filter predicates."""

from __future__ import annotations

import datetime as dt
import unittest

from sql_rag_util.dialects import load
from sql_rag_util.exceptions import LimitExceededError, QuerySpecError, SensitiveColumnError
from sql_rag_util.query.filters import build_predicate, since_bound
from sql_rag_util.query.policy import ColumnPolicy
from sql_rag_util.query.spec import Filter
from sql_rag_util.schema.model import ColumnInfo, ColumnKind, TableRef
from sql_rag_util.sql.render import render

TEXT = ColumnInfo("name", "TEXT", ColumnKind.TEXT, True)
NUMBER = ColumnInfo("amount", "NUMERIC", ColumnKind.DECIMAL, True)
FLAG = ColumnInfo("paid", "BOOLEAN", ColumnKind.BOOLEAN, True)
WHEN = ColumnInfo("created_at", "DATETIME", ColumnKind.DATETIME, True)
DAY = ColumnInfo("day", "DATE", ColumnKind.DATE, True)
BLOB = ColumnInfo("data", "BLOB", ColumnKind.BINARY, True)
NOW = dt.datetime(2026, 9, 13, 12, 0, 0, tzinfo=dt.timezone.utc)


class BuildPredicateTest(unittest.TestCase):
    """Operators map to bound predicates and kind gates hold."""

    def setUp(self) -> None:
        self.dialect = load("sqlite")

    def _render(self, column: ColumnInfo, flt: Filter, *, max_in: int = 100) -> tuple[str, tuple]:
        return render(build_predicate(self.dialect, '"c"', column, flt, max_in_values=max_in, now=NOW), "qmark")

    def test_comparisons_and_lists(self) -> None:
        """Every value is bound; IN expands to one placeholder per value."""
        self.assertEqual(self._render(NUMBER, Filter("amount", "gte", 10)), ('"c" >= ?', (10,)))
        self.assertEqual(self._render(TEXT, Filter("name", "ne", "x")), ('"c" <> ?', ("x",)))
        self.assertEqual(self._render(TEXT, Filter("name", "in", ["a", "b"])), ('"c" IN (?, ?)', ("a", "b")))
        self.assertEqual(self._render(NUMBER, Filter("amount", "not_in", [1])), ('"c" NOT IN (?)', (1,)))
        self.assertEqual(self._render(NUMBER, Filter("amount", "between", [1, 5])), ('"c" BETWEEN ? AND ?', (1, 5)))
        self.assertEqual(self._render(FLAG, Filter("paid", "eq", True)), ('"c" = ?', (True,)))
        self.assertEqual(self._render(TEXT, Filter("name", "is_null")), ('"c" IS NULL', ()))
        self.assertEqual(self._render(TEXT, Filter("name", "not_null")), ('"c" IS NOT NULL', ()))

    def test_text_predicates_escape_and_bind(self) -> None:
        """contains and starts_with go through the dialect with escaping."""
        self.assertEqual(self._render(TEXT, Filter("name", "contains", "50%")), ('"c" LIKE ? ESCAPE \'!\'', ("%50!%%",)))
        self.assertEqual(self._render(TEXT, Filter("name", "starts_with", "Ac")), ('"c" LIKE ? ESCAPE \'!\'', ("Ac%",)))

    def test_since_days_is_computed_in_python(self) -> None:
        """The bound is ISO text shaped by kind, so no dialect date arithmetic is emitted."""
        self.assertEqual(self._render(WHEN, Filter("created_at", "since_days", 30)), ('"c" >= ?', ("2026-08-14 12:00:00",)))
        self.assertEqual(self._render(DAY, Filter("day", "since_days", 1)), ('"c" >= ?', ("2026-09-12",)))
        self.assertEqual(since_bound(ColumnKind.DATETIME, 0, now=NOW), "2026-09-13 12:00:00")

    def test_kind_gates_and_value_types(self) -> None:
        """Wrong value types and operators for a kind are refused."""
        cases = [
            (NUMBER, Filter("amount", "eq", "10")), (TEXT, Filter("name", "eq", 3)), (FLAG, Filter("paid", "eq", 1)),
            (NUMBER, Filter("amount", "contains", "1")), (BLOB, Filter("data", "gt", "x")), (BLOB, Filter("data", "between", ["a", "b"])),
            (TEXT, Filter("name", "since_days", 3)), (NUMBER, Filter("amount", "in", [1, "2"])),
        ]
        for column, flt in cases:
            with self.subTest(column=column.name, op=flt.op):
                with self.assertRaises(QuerySpecError):
                    self._render(column, flt)
        with self.assertRaises(LimitExceededError):
            self._render(NUMBER, Filter("amount", "in", [1, 2, 3]), max_in=2)


class ColumnPolicyTest(unittest.TestCase):
    """Hidden columns vanish; sensitive columns are named but refused."""

    def test_policy(self) -> None:
        """Visibility and usability follow the flags."""
        ref = TableRef(None, "customers")
        policy = ColumnPolicy(hidden={ref: frozenset({"notes"})}, sensitive={ref: frozenset({"email"})})
        columns = (TEXT, ColumnInfo("email", "TEXT", ColumnKind.TEXT, True), ColumnInfo("notes", "TEXT", ColumnKind.TEXT, True))
        self.assertEqual([c.name for c in policy.visible(ref, columns)], ["name", "email"])
        self.assertEqual([c.name for c in policy.selectable(ref, columns)], ["name"])
        policy.check_usable(ref, "name")
        for column in ("email", "notes"):
            with self.subTest(column=column):
                with self.assertRaises(SensitiveColumnError):
                    policy.check_usable(ref, column)
        self.assertIn("does not exist", str(self._error(policy, ref, "notes")))

    @staticmethod
    def _error(policy: ColumnPolicy, ref: TableRef, column: str) -> Exception:
        try:
            policy.check_usable(ref, column)
        except SensitiveColumnError as exc:
            return exc
        raise AssertionError("expected an error")


if __name__ == "__main__":
    unittest.main()
