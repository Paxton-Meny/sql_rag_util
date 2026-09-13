"""Tests for the value index and the JSON cache."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from sql_rag_util.config import StatementEvent
from sql_rag_util.dialects import load
from sql_rag_util.exceptions import MetadataPathError
from sql_rag_util.executor import Executor
from sql_rag_util.metadata.annotate import annotate
from sql_rag_util.metadata.store import MetadataStore
from sql_rag_util.retrieval.cache import JsonCache
from sql_rag_util.retrieval.values import ValueIndex, build_value_index
from sql_rag_util.schema.introspect import introspect
from tests.support.fixture import build_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


class ValueIndexTest(unittest.TestCase):
    """Indexing reads bounded distinct values and matching links question words to columns."""

    def setUp(self) -> None:
        self.conn = build_fixture()
        self.addCleanup(self.conn.close)
        self.events: list[StatementEvent] = []
        self.executor = Executor(self.conn, "qmark", on_statement=self.events.append)
        self.dialect = load("sqlite")
        self.annotated = annotate(introspect(self.executor, self.dialect), MetadataStore(FIXTURES).load(), self.dialect)

    def test_build_respects_policy_and_caps(self) -> None:
        """Sensitive and hidden columns are skipped; each column costs one bounded statement."""
        self.events.clear()
        index = build_value_index(self.executor, self.dialect, self.annotated)
        columns = {(e.table, e.column) for e in index.entries}
        self.assertIn(("customers", "name"), columns)
        self.assertIn(("orders", "status"), columns)
        self.assertNotIn(("customers", "email"), columns)
        self.assertNotIn(("customers", "password_hash"), columns)
        self.assertNotIn(("orders", "notes"), columns)
        self.assertEqual(index.for_column("orders", "status").values, ("cancelled", "open", "paid", "shipped"))
        self.assertTrue(index.for_column("orders", "status").complete)
        self.assertEqual(len(self.events), len(index.entries))
        self.assertTrue(all(e.command == "value_index" for e in self.events))
        self.assertIn("GROUP BY", self.events[0].sql)

    def test_match(self) -> None:
        """Exact words, phrases, prefixes, and one-letter typos link to columns, best first."""
        index = build_value_index(self.executor, self.dialect, self.annotated)
        hits = index.match("Which open orders does Acme Corp have in the nort region, and any shiped ones?")
        found = {(h.column, h.value): (h.matched, h.quality) for h in hits}
        self.assertEqual(found[("name", "Acme Corp")], ("Acme Corp", 4))
        self.assertEqual(found[("status", "open")], ("open", 3))
        self.assertEqual(found[("region", "north")], ("nort", 2))
        self.assertEqual(found[("status", "shipped")], ("shiped", 1))
        self.assertEqual(hits[0].value, "Acme Corp")
        self.assertEqual(index.match("nothing here"), ())

    def test_cache_round_trip_and_containment(self) -> None:
        """The cache serves a matching version, ignores a stale one, and refuses bad names."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = JsonCache(tmp)
            first = build_value_index(self.executor, self.dialect, self.annotated, cache=cache)
            count = len(self.events)
            again = build_value_index(self.executor, self.dialect, self.annotated, cache=cache)
            self.assertEqual(first, again)
            self.assertEqual(len(self.events), count)
            self.assertIsNone(cache.load("values", "other-version"))
            self.assertEqual(ValueIndex.from_json(cache.load("values", self.annotated.version)), first)
            self.assertEqual(ValueIndex.from_json("junk"), ValueIndex())
            with self.assertRaises(MetadataPathError):
                cache.load("../escape", "v")

    def test_disabled_index_is_empty(self) -> None:
        """Without value_index on, nothing is read."""
        plain = annotate(self.annotated.catalog, self.annotated.metadata.__class__(), self.dialect)
        self.events.clear()
        self.assertEqual(build_value_index(self.executor, self.dialect, plain), ValueIndex())
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
