# Explicit column lists, never SELECT *

## Decision

Every select list is built from the catalog minus hidden and sensitive columns, and binary columns are left out of default selections.

## Alternative weighed

`SELECT *` for the default column set.

## Why the alternative lost

A column marked sensitive after the metadata was written, or added to the database later, would leak through a wildcard. Naming columns also gives the result deterministic column order and names an agent can rely on.
