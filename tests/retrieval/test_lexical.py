"""Tests for tokenizing and BM25 ranking."""

from __future__ import annotations

import unittest

from sql_rag_util.retrieval.lexical import Bm25Index, Document
from sql_rag_util.retrieval.tokenize import tokenize


class TokenizeTest(unittest.TestCase):
    """Identifiers and questions produce comparable tokens."""

    def test_tokenize(self) -> None:
        """Camel and snake case split, plurals fold, stopwords and short tokens drop."""
        self.assertEqual(tokenize("customerId"), ("customer", "id"))
        self.assertEqual(tokenize("order_line_items"), ("order", "line", "item"))
        self.assertEqual(tokenize("HTTPServerError"), ("http", "server", "error"))
        self.assertEqual(tokenize("Which orders are open for Acme?"), ("order", "open", "acme"))
        self.assertEqual(tokenize("categories, addresses; a"), ("category", "address"))
        self.assertEqual(tokenize(""), ())


class Bm25Test(unittest.TestCase):
    """Ranking prefers rare matching terms and weighted fields."""

    def setUp(self) -> None:
        self.index = Bm25Index(
            (
                Document("orders", {"name": "orders", "purpose": "One row per customer order.", "columns": "id customer_id status amount created_at"}),
                Document("customers", {"name": "customers", "purpose": "One row per customer account.", "columns": "id name email region"}),
                Document("shipments", {"name": "shipments", "purpose": "Parcels sent for an order.", "columns": "order_id seq carrier"}),
            ),
            weights={"name": 3.0, "purpose": 1.5, "columns": 1.0},
        )

    def test_ranking(self) -> None:
        """The table named by the query ranks first; unrelated queries return nothing."""
        self.assertEqual([i for i, _ in self.index.search("open orders")][0], "orders")
        self.assertEqual([i for i, _ in self.index.search("which carrier shipped it")][0], "shipments")
        self.assertEqual([i for i, _ in self.index.search("customer region")][0], "customers")
        self.assertEqual(self.index.search("zzz"), ())
        self.assertEqual(self.index.search(""), ())
        self.assertEqual(len(self.index.search("order", limit=1)), 1)
        self.assertEqual(len(self.index), 3)

    def test_empty_index(self) -> None:
        """An empty index answers nothing without dividing by zero."""
        self.assertEqual(Bm25Index(()).search("orders"), ())


if __name__ == "__main__":
    unittest.main()
