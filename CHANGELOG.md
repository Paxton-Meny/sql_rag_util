# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Hidden columns are now absent from the catalog agents resolve against. Naming one raises `UnknownColumnError`, exactly as a missing column does, instead of `SensitiveColumnError`. Breaking for callers that matched the old error type.

### Fixed

- Hidden column names no longer leak through "did you mean" suggestions, the metadata toolkit, foreign key targets on cards, or default ordering.
- A column flagged `fulltext` can no longer also be `sensitive` or `hidden`.
- Metadata toolkit edits can no longer write structure into a file. Text fields must be one line without control or direction characters, list entries cannot contain commas, description lines cannot start with `#`, and every save renders, parses back, and refuses to write unless the result is identical. A failed refresh after a write restores the previous file.
- An edit is refused with the new `MetadataConflictError` when the metadata files changed on disk since they were loaded. The engine reloads them, so a retry applies on top of the developer's change instead of overwriting it.
- Duplicate column, relationship, concept, and measure names in a table file are format errors, and a failed `SqlRag.refresh()` leaves the engine unchanged.
- `python -m sql_rag_util.mcp --sqlite PATH` opens the file read-only through a percent-encoded URI. Before, a `#` or `?` in the path dropped `mode=ro` and could open, or create, a different writable file. A missing file now exits 2, and a file that cannot be served exits 1, both with a one-line error and no traceback.
- The MCP server reports the package version by default instead of `0.0.0`, and answers a failure while handling a request with the JSON-RPC internal error code `-32603` instead of `-32600`.
- Results are always strict JSON. NaN and infinite floats and decimals become `"NaN"`, `"Infinity"`, and `"-Infinity"` instead of invalid JSON, a decimal infinity or signaling NaN no longer raises out of dispatch, and huge integral decimals become text. The MCP server refuses `NaN` and `Infinity` in requests and answers a response that cannot be encoded with `-32603` instead of stopping.
- A driver failure while opening or closing a cursor is now an `ExecutionError` like any other, a failure to close after a failed statement no longer hides the original error, and cursors that return mappings yield value tuples instead of key tuples.

## [0.1.0] - 2026-09-13

First release. Standard library only, Python 3.11 or newer.

### Added

- `SqlRag` facade over a PEP 249 connection: dialect detection, catalog introspection, metadata annotation, scope filters, tool listing by tier, dispatch with JSON and compact envelopes, and a system-prompt instructions block.
- Four dialects: SQLite, MySQL and MariaDB, SQL Server, PostgreSQL. Each owns quoting, a bound limit form, introspection statements, type kinds, and the fuzzy predicates it can serve.
- Statement model of fragments plus binds with one renderer for every paramstyle, so identifiers are never rewritten and values are always parameters.
- Query spec and compiler: one bounded SELECT per request with whitelisted operators and aggregates, joins by relationship name, kind gates, caps, primary-key ordering, and honest truncation.
- Five agent tools: `get_context`, `query`, `describe_table`, `list_tables`, `search_rows`, with descriptions, examples, and schemas derived from argument dataclasses.
- Metadata format version 1 with a strict parser, canonical writer, contained store, and annotation: purposes, column meaning and flags, renamed and declared relationships, concepts, measures, glossary, provenance.
- Metadata toolkit tools for agents, validated against the catalog and attributed with the date.
- Schema retrieval: tokenizer, BM25 with weighted fields, opt-in value index with a fingerprint-keyed cache, optional embedding hook, reciprocal rank fusion, token-budgeted schema cards, and empty-result diagnosis.
- Row search: per-word matching across searchable columns with contains, Soundex, Levenshtein, trigram, and full-text strategies by capability; word-aware SQLite functions registered on request.
- Adapters for Anthropic, OpenAI strict mode, and MCP, plus a standard-library MCP stdio server with a SQLite entry point.
- Documentation: architecture, threat model, metadata format, tool reference, context cost, and twenty-five design notes. Benchmark and cost caps.

[Unreleased]: https://github.com/Paxton-Meny/sql_rag_util/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Paxton-Meny/sql_rag_util/releases/tag/v0.1.0
