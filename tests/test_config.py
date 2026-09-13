"""Tests for configuration and limits."""

from __future__ import annotations

import unittest

from sql_rag_util.config import Config, Limits
from sql_rag_util.exceptions import ConfigurationError


class LimitsTest(unittest.TestCase):
    """Limits validate on construction."""

    def test_defaults_are_consistent(self) -> None:
        """Default limits construct and keep max_rows under the hard cap."""
        limits = Limits()
        self.assertLessEqual(limits.max_rows, limits.hard_max_rows)

    def test_rejects_non_positive_and_wrong_types(self) -> None:
        """Zero, negatives, booleans, and strings are refused with the field name."""
        for value in (0, -1, True, "5"):
            with self.subTest(value=value):
                with self.assertRaises(ConfigurationError) as ctx:
                    Limits(max_rows=value)  # type: ignore[arg-type]
                self.assertIn("max_rows", str(ctx.exception))

    def test_rejects_max_rows_over_hard_cap(self) -> None:
        """max_rows above hard_max_rows is an error."""
        with self.assertRaises(ConfigurationError):
            Limits(max_rows=600, hard_max_rows=500)


class ConfigTest(unittest.TestCase):
    """Config validates its hooks."""

    def test_defaults(self) -> None:
        """Writes are off, diagnosis is on, SQL is not revealed."""
        config = Config()
        self.assertFalse(config.allow_metadata_writes)
        self.assertTrue(config.diagnose_empty_results)
        self.assertFalse(config.reveal_sql)

    def test_hooks_must_be_callable(self) -> None:
        """Non-callable hooks are refused."""
        with self.assertRaises(ConfigurationError):
            Config(scope="tenant = 1")  # type: ignore[arg-type]
        with self.assertRaises(ConfigurationError):
            Config(on_statement=object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
