# SQLite fuzzy functions are registered explicitly

## Decision

`register_sqlite_functions` adds the word-aware Soundex and Levenshtein functions to a connection only when the developer calls it; the function-list probe then reports the capabilities.

## Alternative weighed

Register automatically when a SQLite connection is seen.

## Why the alternative lost

Registering mutates the caller's connection, which the package otherwise never does. An explicit call keeps that side effect visible, and probing rather than assuming keeps the capability set honest.
