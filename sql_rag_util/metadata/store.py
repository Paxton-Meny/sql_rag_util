"""Read and write the metadata directory without ever leaving it."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from sql_rag_util.atomic import atomic_write_text
from sql_rag_util.exceptions import MetadataFormatError, MetadataPathError
from sql_rag_util.metadata.model import Metadata, ProjectMeta
from sql_rag_util.metadata.parser import parse_glossary, parse_project, parse_relationships, parse_table
from sql_rag_util.metadata.writer import render_glossary, render_project, render_relationships, render_table

if TYPE_CHECKING:
    import os

    from sql_rag_util.metadata.model import DeclaredRelationship, GlossaryEntry, TableMeta

__all__ = ["MetadataStore"]

_STEM = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
_PROJECT = "project.md"
_RELATIONSHIPS = "relationships.md"
_GLOSSARY = "glossary.md"
_TABLES = "tables"


class MetadataStore:
    """Files under one root directory.

    Parameters
    ----------
    root
        The metadata directory. It need not exist until the first write.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        """Return the resolved root directory."""
        return self._root

    def path(self, *parts: str) -> Path:
        """Return ``root/parts`` after proving it stays inside the root."""
        candidate = self._root.joinpath(*parts)
        resolved = candidate.resolve()
        if resolved != self._root and not resolved.is_relative_to(self._root):
            raise MetadataPathError(f"{candidate} escapes the metadata root")
        return resolved

    def table_path(self, stem: str) -> Path:
        """Return the path of the table file for ``stem`` after validating the stem."""
        if not _STEM.match(stem):
            raise MetadataFormatError(f"table file stem {stem!r} is not a table name", path=f"{_TABLES}/{stem}.md")
        return self.path(_TABLES, f"{stem}.md")

    def _relative(self, path: Path) -> str:
        return str(path.relative_to(self._root))

    def load(self) -> Metadata:
        """Parse every file present. A missing file contributes nothing."""
        project = ProjectMeta()
        if (path := self.path(_PROJECT)).is_file():
            project = parse_project(path.read_text(encoding="utf-8"), self._relative(path))
        tables = []
        tables_dir = self.path(_TABLES)
        if tables_dir.is_dir():
            for path in sorted(p for p in tables_dir.iterdir() if p.suffix == ".md"):
                stem = path.name[: -len(".md")]
                if not _STEM.match(stem):
                    raise MetadataFormatError("file name is not a table name", path=self._relative(path))
                tables.append(parse_table(self.path(_TABLES, path.name).read_text(encoding="utf-8"), self._relative(path), stem))
        relationships: tuple[DeclaredRelationship, ...] = ()
        if (path := self.path(_RELATIONSHIPS)).is_file():
            relationships = parse_relationships(path.read_text(encoding="utf-8"), self._relative(path))
        glossary: tuple[GlossaryEntry, ...] = ()
        if (path := self.path(_GLOSSARY)).is_file():
            glossary = parse_glossary(path.read_text(encoding="utf-8"), self._relative(path))
        return Metadata(project, tuple(tables), relationships, glossary)

    def save_table(self, meta: TableMeta) -> Path:
        """Write ``meta`` canonically and return its path."""
        path = self.table_path(meta.table)
        atomic_write_text(path, render_table(meta))
        return path

    def remove_table(self, stem: str) -> bool:
        """Delete the table file for ``stem``; return whether it existed."""
        path = self.table_path(stem)
        existed = path.is_file()
        path.unlink(missing_ok=True)
        return existed

    def save_project(self, meta: ProjectMeta) -> Path:
        """Write ``project.md`` canonically."""
        path = self.path(_PROJECT)
        atomic_write_text(path, render_project(meta))
        return path

    def save_relationships(self, relationships: tuple[DeclaredRelationship, ...]) -> Path:
        """Write ``relationships.md`` canonically."""
        path = self.path(_RELATIONSHIPS)
        atomic_write_text(path, render_relationships(relationships))
        return path

    def save_glossary(self, entries: tuple[GlossaryEntry, ...]) -> Path:
        """Write ``glossary.md`` canonically."""
        path = self.path(_GLOSSARY)
        atomic_write_text(path, render_glossary(entries))
        return path
