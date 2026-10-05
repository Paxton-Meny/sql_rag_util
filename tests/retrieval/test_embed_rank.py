"""Tests for the embedding hook, its cache, and rank fusion."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Sequence

from sql_rag_util.exceptions import ConfigurationError
from sql_rag_util.retrieval.cache import JsonCache
from sql_rag_util.retrieval.embed import EmbeddingIndex, build_embedding_index
from sql_rag_util.retrieval.rank import reciprocal_rank_fusion


def _embed(texts: Sequence[str]) -> list[list[float]]:
    table = {"orders": [1.0, 0.0], "customers": [0.0, 1.0], "shipments": [0.7, 0.7]}
    return [table.get(t, [0.0, 0.0]) for t in texts]


class EmbeddingTest(unittest.TestCase):
    """Vectors are unit-normalized, cached by version, and searched by cosine."""

    def test_build_and_search(self) -> None:
        """The closest document ranks first and the cache avoids a second embed call."""
        calls: list[list[str]] = []

        def counting(texts: Sequence[str]) -> list[list[float]]:
            calls.append(list(texts))
            return _embed(texts)

        docs = [("orders", "orders"), ("customers", "customers"), ("shipments", "shipments")]
        with tempfile.TemporaryDirectory() as tmp:
            cache = JsonCache(tmp)
            index = build_embedding_index(counting, docs, "v1", cache=cache)
            self.assertEqual(index.search([1.0, 0.1])[0][0], "orders")
            self.assertEqual([i for i, _ in index.search([0.5, 0.5], limit=1)], ["shipments"])
            again = build_embedding_index(counting, docs, "v1", cache=cache)
            self.assertEqual(again, index)
            self.assertEqual(len(calls), 1)
            build_embedding_index(counting, docs, "v2", cache=cache)
            self.assertEqual(len(calls), 2)
        self.assertEqual(build_embedding_index(counting, [], "v"), EmbeddingIndex())

    def test_errors(self) -> None:
        """A wrong vector count or a changed dimension is a configuration error."""
        with self.assertRaises(ConfigurationError):
            build_embedding_index(lambda texts: [[1.0]], [("a", "a"), ("b", "b")], "v")
        index = EmbeddingIndex(("a",), ((1.0, 0.0),))
        with self.assertRaises(ConfigurationError):
            index.search([1.0, 0.0, 0.0])
        self.assertIsNone(EmbeddingIndex.from_json({"ids": ["a"], "vectors": []}))


class FusionTest(unittest.TestCase):
    """Reciprocal rank fusion rewards ids that rank well in several lists."""

    def test_fusion(self) -> None:
        """An id present in both lists beats one that leads only one list; weights shift the balance."""
        fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d"]])
        self.assertEqual([i for i, _ in fused][:2], ["b", "a"])
        weighted = reciprocal_rank_fusion([["a", "b"], ["b", "a"]], weights=[1.0, 3.0])
        self.assertEqual(weighted[0][0], "b")
        self.assertEqual(reciprocal_rank_fusion([]), ())


if __name__ == "__main__":
    unittest.main()
