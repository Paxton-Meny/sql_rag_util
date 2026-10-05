"""Tests for canonical rendering: every fixture round-trips byte for byte."""

from __future__ import annotations

import unittest

from sql_rag_util.metadata.model import ProjectMeta
from sql_rag_util.metadata.parser import parse_glossary, parse_project, parse_relationships, parse_table
from sql_rag_util.metadata.writer import render_glossary, render_project, render_relationships, render_table
from tests.support.fixture import FIXTURES



class RoundTripTest(unittest.TestCase):
    """parse then render reproduces each reference file exactly."""

    def test_tables(self) -> None:
        """Both table fixtures are canonical."""
        for stem in ("orders", "customers"):
            with self.subTest(stem=stem):
                text = (FIXTURES / "tables" / f"{stem}.md").read_text()
                self.assertEqual(render_table(parse_table(text, f"tables/{stem}.md", stem)), text)

    def test_other_files(self) -> None:
        """project, relationships, and glossary fixtures are canonical."""
        project = (FIXTURES / "project.md").read_text()
        self.assertEqual(render_project(parse_project(project, "project.md")), project)
        rels = (FIXTURES / "relationships.md").read_text()
        self.assertEqual(render_relationships(parse_relationships(rels, "relationships.md")), rels)
        glossary = (FIXTURES / "glossary.md").read_text()
        self.assertEqual(render_glossary(parse_glossary(glossary, "glossary.md")), glossary)

    def test_defaults_are_omitted(self) -> None:
        """A default project renders as the minimal file, and empties render without sections."""
        self.assertEqual(render_project(ProjectMeta()), "# project\n\nformat: 1\n")
        self.assertEqual(render_relationships(()), "# relationships\n\nformat: 1\n")
        self.assertEqual(render_glossary(()), "# glossary\n\nformat: 1\n")


if __name__ == "__main__":
    unittest.main()
