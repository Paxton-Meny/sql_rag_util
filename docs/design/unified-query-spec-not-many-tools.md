# One query tool instead of many read tools

## Decision

Agents read data through one `query` tool that takes a declarative spec: columns, filters, joins by relationship name, group_by, measures, order, limit, and named concepts. Counts, distinct values, aggregates, and relationship traversal are idioms of that spec.

## Alternative weighed

Separate tools: `get_rows`, `count_rows`, `distinct_values`, `aggregate`, `follow_relationship`. Each has a small schema and a narrow purpose.

## Why the alternative lost

Every tool definition is sent on every model call, so five definitions cost more than one on each turn of every conversation. More tools also means more choice points where a model picks the wrong one, and a joined or aggregated question needs several calls where one spec would do. Production text-to-SQL systems converged on a semantic layer for the same reasons: one shape to learn, business rules applied by name, and one statement per question. The cost is a richer schema for the single tool, which the description offsets with idioms and examples.
