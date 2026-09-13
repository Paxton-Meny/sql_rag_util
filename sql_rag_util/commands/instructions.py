"""The system-prompt block that teaches an agent the workflow."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sql_rag_util.engine import SqlRag

__all__ = ["instructions"]

_TEMPLATE = """You can read a SQL database through tools; you never write SQL yourself.

Workflow for a question:
1. Call get_context with the question when it is available; otherwise list_tables. It returns the tables that matter as schema cards, plus known column values that match words in the question.
2. Call describe_table only for a table whose card you have not seen or whose column values you need before filtering.
3. Call query with one spec: table, columns or measures, filters, and dotted paths through relationships for joins. Count with measures [{{fn: count}}]; list distinct values with group_by; apply concepts and named measures by name.
4. Read notes and truncated on every result. If a query returns 0 rows, check the value against the card's known values or find the row with search_rows, then retry once. If it was truncated, narrow with filters instead of raising the limit.
5. Cite what you found from the rows you received. Do not infer rows you did not see.

Facts about this database: dialect {dialect}; {tables} tables; schema_version {version}. A changed schema_version means cards you saw earlier may be stale.{project}
"""


def instructions(engine: SqlRag) -> str:
    """Return the workflow block for ``engine``, ready for a system prompt."""
    description = engine.annotated.metadata.project.description
    project = f"\nAbout the data: {description}" if description else ""
    return _TEMPLATE.format(dialect=engine.dialect.name, tables=len(engine.catalog.tables), version=engine.schema_version, project=project)
