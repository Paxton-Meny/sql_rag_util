# Filters are objects, not triples

## Decision

A filter is `{"column", "op", "value"}`.

## Alternative weighed

A three-element array, which is a few tokens shorter.

## Why the alternative lost

Positional arrays need `prefixItems`, which strict tool schemas do not accept everywhere. Objects with named keys are readable by every framework and by people, and the difference is a handful of tokens per filter.
