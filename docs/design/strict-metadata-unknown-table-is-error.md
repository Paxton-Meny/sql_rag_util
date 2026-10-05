# A metadata file for a missing table is an error

## Decision

A table file whose table is not in the catalog fails annotation, as does any column, relationship, concept column, or glossary table that does not exist.

## Alternative weighed

Warn and ignore stale entries.

## Why the alternative lost

Stale metadata silently shapes what an agent believes. Failing at load time turns a renamed column into a one-line fix rather than a wrong answer, and retiring a table is the developer deleting its file, or calling `MetadataStore.remove_table` from code.
