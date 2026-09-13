"""Tests for the document layer of the metadata parser."""

from __future__ import annotations

import unittest

from sql_rag_util.exceptions import MetadataFormatError
from sql_rag_util.metadata.document import bullets, json_sub, list_value, only_subs, prose, split_document

VALID = """# orders

format: 1
purpose: One row per order.
synonyms: purchase, sale

## Description

Prose here.

## Columns

- id: Surrogate key.
- status [searchable, sensitive]: State.
  - values: open, paid
  - synonyms: state,
    stage
- notes: Long text
  that continues.
"""


class SplitDocumentTest(unittest.TestCase):
    """Title, header, and sections are separated and every common rule is enforced."""

    def test_valid_document(self) -> None:
        """Header keys keep their line numbers and sections keep their lines."""
        doc = split_document(VALID, "tables/orders.md")
        self.assertEqual(doc.title, "orders")
        self.assertEqual(doc.header["purpose"], ("One row per order.", 4))
        self.assertEqual(set(doc.sections), {"Description", "Columns"})
        self.assertEqual(prose(doc.sections["Description"][1]), "Prose here.")

    def test_rejections_name_the_line(self) -> None:
        """Each violated rule raises with the offending line."""
        cases = {
            "orders\n\nformat: 1\n": 1,
            "# orders\nformat: 1\n": 3,
            "# orders\n\nformat: 2\n": 3,
            "# orders\n\nformat: 1\nbad line\n": 4,
            "# orders\n\nformat: 1\npurpose: a\npurpose: b\n": 5,
            "# orders\n\nformat: 1\n\nstray text\n": 5,
            "# orders\n\nformat: 1\n\n## A\n\n## A\n": 7,
            "# orders\n\nformat: 1\n\tx\n": 4,
        }
        for text, line in cases.items():
            with self.subTest(text=text):
                with self.assertRaises(MetadataFormatError) as ctx:
                    split_document(text, "f.md")
                self.assertEqual(ctx.exception.line, line)
        with self.assertRaises(MetadataFormatError):
            split_document("# a\r\n\r\nformat: 1\r\n", "f.md")


class BulletsTest(unittest.TestCase):
    """Bullets carry flags, sub-bullets, and continuation lines."""

    def test_bullets_and_helpers(self) -> None:
        """Flags split, sub-bullets attach to the last bullet, continuations extend the last item."""
        doc = split_document(VALID, "tables/orders.md")
        parsed = bullets(doc, doc.sections["Columns"][1])
        self.assertEqual([b.name for b in parsed], ["id", "status", "notes"])
        self.assertEqual(parsed[1].flags, ("searchable", "sensitive"))
        self.assertEqual(list_value(parsed[1].subs["values"][0]), ("open", "paid"))
        self.assertEqual(list_value(parsed[1].subs["synonyms"][0]), ("state", "stage"))
        self.assertEqual(parsed[2].text, "Long text that continues.")
        only_subs(doc, parsed[1], ("values", "synonyms"))
        with self.assertRaises(MetadataFormatError) as ctx:
            only_subs(doc, parsed[1], ("values",))
        self.assertEqual(ctx.exception.line, 16)

    def test_bullet_rejections(self) -> None:
        """Stray lines, duplicate sub-bullets, and bad JSON are refused with lines."""
        doc = split_document("# t\n\nformat: 1\n\n## Columns\n\nnot a bullet\n", "f.md")
        with self.assertRaises(MetadataFormatError) as ctx:
            bullets(doc, doc.sections["Columns"][1])
        self.assertEqual(ctx.exception.line, 7)
        doc = split_document("# t\n\nformat: 1\n\n## Columns\n\n- a: x\n  - values: 1\n  - values: 2\n", "f.md")
        with self.assertRaises(MetadataFormatError) as ctx:
            bullets(doc, doc.sections["Columns"][1])
        self.assertEqual(ctx.exception.line, 9)
        doc = split_document("# t\n\nformat: 1\n\n## Concepts\n\n- a: x\n  - where: [oops\n", "f.md")
        bullet = bullets(doc, doc.sections["Concepts"][1])[0]
        with self.assertRaises(MetadataFormatError) as ctx:
            json_sub(doc, bullet, "where")
        self.assertEqual(ctx.exception.line, 8)
        with self.assertRaises(MetadataFormatError):
            json_sub(doc, bullet, "expr")


if __name__ == "__main__":
    unittest.main()
