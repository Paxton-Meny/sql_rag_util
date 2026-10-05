# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Hidden columns are now absent from the catalog agents resolve against. Naming one raises `UnknownColumnError`, exactly as a missing column does, instead of `SensitiveColumnError`. Breaking for callers that matched the old error type.

### Fixed

- Hidden column names no longer leak through "did you mean" suggestions, the metadata toolkit, foreign key targets on cards, or default ordering.
- A column flagged `fulltext` can no longer also be `sensitive` or `hidden`.

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
