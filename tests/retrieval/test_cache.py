"""Tests for the fingerprint-keyed JSON cache."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from sql_rag_util.exceptions import MetadataPathError
from sql_rag_util.retrieval.cache import JsonCache


class JsonCacheTest(unittest.TestCase):
    """Only a well-formed file with the current fingerprint is ever served."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = pathlib.Path(tmp.name) / "cache"
        self.cache = JsonCache(self.directory)

    def test_round_trip_and_stale_fingerprint(self) -> None:
        """A saved payload loads back under its fingerprint and nowhere else."""
        path = self.cache.save("values", "abc", {"orders.status": ["open"]})
        self.assertEqual(path, self.directory.resolve() / "values.json")
        self.assertEqual(self.cache.load("values", "abc"), {"orders.status": ["open"]})
        self.assertIsNone(self.cache.load("values", "def"))
        self.assertIsNone(self.cache.load("embeddings", "abc"))

    def test_damaged_files_are_ignored(self) -> None:
        """Truncated JSON, invalid UTF-8, and the wrong document shape all read as a miss."""
        self.directory.mkdir()
        damaged = {
            "truncated": b'{"fingerprint": "abc", "payload": [',
            "binary": b"\xff\xfe\x00",
            "listed": b'["abc"]',
            "unkeyed": b'{"payload": 1}',
        }
        for name, content in damaged.items():
            with self.subTest(name=name):
                (self.directory / f"{name}.json").write_bytes(content)
                self.assertIsNone(self.cache.load(name, "abc"))

    def test_names_cannot_leave_the_directory(self) -> None:
        """Cache names are identifiers, so no name reaches a path outside the directory."""
        for name in ("../escape", "a/b", "", "values.json"):
            with self.subTest(name=name):
                with self.assertRaises(MetadataPathError):
                    self.cache.save(name, "abc", 1)


if __name__ == "__main__":
    unittest.main()
