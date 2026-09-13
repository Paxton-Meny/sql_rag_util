# SQL Server full-text uses FREETEXT

## Decision

The full-text strategy emits `FREETEXT(column, ?)`.

## Alternative weighed

`CONTAINS(column, ?)`.

## Why the alternative lost

CONTAINS interprets its argument as a query language with AND, OR, NEAR, and quoting, so a bound value would still be executed as syntax. FREETEXT treats the value as words to match. Full-text is enabled per column by the `fulltext` flag rather than detected, since the index cannot be verified cheaply.
