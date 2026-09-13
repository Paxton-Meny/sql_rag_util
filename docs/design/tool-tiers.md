# Tools are exposed in tiers

## Decision

`minimal` is get_context and query; `standard` adds describe_table, list_tables, and search_rows; `full` adds the toolkit when writes are enabled.

## Alternative weighed

One flat list of every tool.

## Why the alternative lost

Every definition costs tokens on every model call, and frameworks that defer tool loading can start from the two tools that answer most questions. Writers stay invisible unless the developer enabled them, which is a safety property rather than a size one.
