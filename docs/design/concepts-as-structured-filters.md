# Concepts are structured filters, not prose

## Decision

A business rule such as active orders is stored as a JSON list of the same filter objects the query tool accepts, validated against the catalog, and applied by name.

## Alternative weighed

Describe the rule in prose and let the agent translate it each time.

## Why the alternative lost

Prose is re-interpreted on every call and drifts; a filter list executes the same way every time and fails at metadata load if the schema changes. It also keeps the rule expressible only in what the query layer already permits.
