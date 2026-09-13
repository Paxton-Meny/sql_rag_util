# Default ordering by primary key

## Decision

When a spec gives no order, the compiler orders by the base table's primary key, or its first column without one. Grouped queries order by the first measure descending so the largest groups arrive first.

## Alternative weighed

Let the database return rows in whatever order it likes.

## Why the alternative lost

Unordered results differ between dialects and between runs, and `TOP` without an order is explicitly nondeterministic on SQL Server. An agent that pages or retries needs the same rows back. The cost is one index scan on the key, which the caps keep small.
