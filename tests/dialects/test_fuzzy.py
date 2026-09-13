"""Golden SQL for every dialect's fuzzy predicates."""

from __future__ import annotations

import sqlite3
import unittest

from sql_rag_util.dialects import load
from sql_rag_util.exceptions import CapabilityError
from sql_rag_util.search.sqlite_functions import register_sqlite_functions
from sql_rag_util.sql.render import render


class FuzzyPredicateTest(unittest.TestCase):
    """Each supported predicate binds its text and thresholds; unsupported ones refuse."""

    def test_goldens(self) -> None:
        """Rendered predicates per dialect."""
        cases = {
            ("sqlite", "soundex_match"): ('soundex("c") = soundex(?)', ("jon",)),
            ("sqlite", "levenshtein_within"): ('levenshtein("c", ?) <= ?', ("jon", 2)),
            ("mysql", "soundex_match"): ("SOUNDEX(`c`) = SOUNDEX(%s)", ("jon",)),
            ("mssql", "soundex_match"): ("SOUNDEX([c]) = SOUNDEX(?)", ("jon",)),
            ("mssql", "difference_at_least"): ("DIFFERENCE([c], ?) >= ?", ("jon", 3)),
            ("mssql", "fulltext"): ("FREETEXT([c], ?)", ("jon",)),
            ("postgres", "soundex_match"): ('soundex("c") = soundex(%s)', ("jon",)),
            ("postgres", "difference_at_least"): ('difference("c", %s) >= %s', ("jon", 3)),
            ("postgres", "levenshtein_within"): ('levenshtein_less_equal("c", %s, %s) <= %s', ("jon", 2, 2)),
            ("postgres", "trigram_at_least"): ('similarity("c", %s) >= %s', ("jon", 0.3)),
        }
        arguments = {"soundex_match": ("jon",), "fulltext": ("jon",), "difference_at_least": ("jon", 3), "levenshtein_within": ("jon", 2), "trigram_at_least": ("jon", 0.3)}
        for (name, method), expected in cases.items():
            with self.subTest(dialect=name, method=method):
                dialect = load(name)
                column = dialect.quote("c")
                statement = getattr(dialect, method)(column, *arguments[method])
                self.assertEqual(render(statement, dialect.default_paramstyle), expected)

    def test_refusals(self) -> None:
        """Predicates a dialect lacks raise CapabilityError."""
        for name, method, args in (("mysql", "trigram_at_least", ("x", 0.3)), ("sqlite", "fulltext", ("x",)), ("mssql", "levenshtein_within", ("x", 1)), ("postgres", "fulltext", ("x",))):
            with self.subTest(dialect=name, method=method):
                with self.assertRaises(CapabilityError):
                    getattr(load(name), method)('"c"', *args)

    def test_sqlite_predicates_run_live(self) -> None:
        """Registered functions make the SQLite predicates executable."""
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        register_sqlite_functions(conn)
        conn.execute("CREATE TABLE p (n TEXT)")
        conn.executemany("INSERT INTO p VALUES (?)", [("Smith",), ("Jones",)])
        dialect = load("sqlite")
        text, params = render(dialect.soundex_match('"n"', "Smyth"), "qmark")
        self.assertEqual(conn.execute(f"SELECT n FROM p WHERE {text}", params).fetchall(), [("Smith",)])
        text, params = render(dialect.levenshtein_within('"n"', "Jonas", 2), "qmark")
        self.assertEqual(conn.execute(f"SELECT n FROM p WHERE {text}", params).fetchall(), [("Jones",)])


if __name__ == "__main__":
    unittest.main()
