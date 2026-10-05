# Hidden columns are absent from the agent's catalog

## Decision

`annotate` validates metadata against the full introspected catalog, then builds the catalog agents resolve against with every hidden column removed. A table that loses a primary key column loses its primary key. Foreign keys through a hidden column are dropped. Relationships stay, because join conditions are internal and cards show only the relationship's name, target, and cardinality. Asking for a hidden column raises the same `UnknownColumnError`, with the same message and suggestions, as asking for a column that does not exist. A table whose columns are all hidden is a metadata error.

## Alternative weighed

Keep one catalog and filter at each call site: resolve against visible columns in the join planner and the edit tools, skip hidden names in suggestions, and check foreign key targets in cards.

## Why the alternative lost

Version 0.1.0 did exactly that, and every leak was a call site that forgot: typo suggestions named hidden columns, a distinct error type confirmed they existed, `edit_column` could address them, and default ordering could use them. Each new tool would have to remember the same filters. Removing the columns from the structure agents resolve against closes the whole class at once, and makes "hidden columns do not exist to the agent" true by construction rather than by care.

## Limits

Metadata concepts resolve through the same agent catalog, so they cannot use a hidden column, because agents can write concepts through the toolkit. Developer scope filters are the exception: they resolve against the full catalog, so a tenant column can be hidden and still scope every query. See `scope-filters-are-trusted.md`.
