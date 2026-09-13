"""Tests for term tokenizing, Soundex, Levenshtein, and SQLite registration."""

from __future__ import annotations

import sqlite3
import unittest

from sql_rag_util.exceptions import LimitExceededError, QuerySpecError
from sql_rag_util.search.levenshtein import levenshtein
from sql_rag_util.search.soundex import soundex
from sql_rag_util.search.sqlite_functions import register_sqlite_functions
from sql_rag_util.search.term import tokenize_term


class TermTest(unittest.TestCase):
    """Terms split into unique tokens under a cap."""

    def test_tokenize(self) -> None:
        """Whitespace splits, duplicates collapse, caps and empties are refused."""
        self.assertEqual(tokenize_term("  Jon   Smyth Jon ", max_tokens=5), ("Jon", "Smyth"))
        with self.assertRaises(QuerySpecError):
            tokenize_term("   ", max_tokens=5)
        with self.assertRaises(LimitExceededError):
            tokenize_term("a b c", max_tokens=2)
        with self.assertRaises(QuerySpecError):
            tokenize_term("x" * 101, max_tokens=5)


class SoundexTest(unittest.TestCase):
    """The published examples code correctly."""

    def test_examples(self) -> None:
        """Standard reference codes, including the H/W and vowel rules."""
        cases = {
            "Robert": "R163", "Rupert": "R163", "Rubin": "R150", "Ashcraft": "A261", "Ashcroft": "A261",
            "Tymczak": "T522", "Pfister": "P236", "Honeyman": "H555", "Lee": "L000", "Gutierrez": "G362",
            "Jackson": "J250", "jon": "J500", "John": "J500",
        }
        for word, code in cases.items():
            with self.subTest(word=word):
                self.assertEqual(soundex(word), code)
        self.assertIsNone(soundex(""))
        self.assertIsNone(soundex("123"))
        self.assertIsNone(soundex(None))


class LevenshteinTest(unittest.TestCase):
    """Distances and bounds."""

    def test_distances(self) -> None:
        """Known distances, symmetry, empties, and early exit past the bound."""
        self.assertEqual(levenshtein("kitten", "sitting"), 3)
        self.assertEqual(levenshtein("sitting", "kitten"), 3)
        self.assertEqual(levenshtein("", "abc"), 3)
        self.assertEqual(levenshtein("same", "same"), 0)
        self.assertEqual(levenshtein("Smyth", "Smith", max_distance=2), 1)
        self.assertEqual(levenshtein("abcdefgh", "xyz", max_distance=2), 3)
        self.assertEqual(levenshtein("abcd", "wxyz", max_distance=2), 3)
        self.assertIsNone(levenshtein(None, "a"))


class RegistrationTest(unittest.TestCase):
    """Registered functions run inside SQLite and show up in the function list."""

    def test_register(self) -> None:
        """The word-aware functions are callable from SQL after registration."""
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        register_sqlite_functions(conn)
        self.assertEqual(conn.execute("SELECT sqlrag_soundex_any('Jon Smyth', 'Smith')").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT sqlrag_soundex_any('Jon Smyth', 'Zed')").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT sqlrag_levenshtein_min('Jon Smyth', 'john')").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT sqlrag_levenshtein_min(NULL, 'x') > 100").fetchone()[0], 1)
        names = {r[0] for r in conn.execute("SELECT name FROM pragma_function_list WHERE name IN ('sqlrag_soundex_any', 'sqlrag_levenshtein_min')")}
        self.assertEqual(names, {"sqlrag_soundex_any", "sqlrag_levenshtein_min"})


if __name__ == "__main__":
    unittest.main()
