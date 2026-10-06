# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-10-06

Security and robustness release ahead of the repository going public. Upgrade from 0.1.0, which has the security issues listed below. Standard library only, Python 3.11 to 3.14.

### Security

- Hidden columns could be discovered: a near-miss name suggested them ("did you mean password_hash?"), naming one raised a different error from a missing column, and the metadata toolkit could edit them. They are now absent from the catalog agents resolve against, so naming one fails exactly as a missing column does.
- Metadata toolkit edits could write structure into a file. A newline in agent text could plant a header key, a section, or a second, unflagged entry for a column that a later edit kept in place of the flagged one, stripping `sensitive` or `hidden`; a failed reload left the broken file on disk. Text fields must now be one line without control or direction characters, list entries cannot contain commas, description lines cannot start with `#`, every save must parse back identically before it is written, and a failed reload restores the previous file.
- An agent edit could overwrite a change the developer had just made on disk, such as a newly added `hidden` flag. Such an edit is now refused with the new `MetadataConflictError`, and the engine reloads so a retry applies on top of the developer's change.
- `python -m sql_rag_util.mcp --sqlite PATH` built its database URI without escaping, so a `#` or `?` in the path dropped `mode=ro` and could open, or create, a different, writable file. The path is now percent-encoded, a missing file exits 2, and a file that cannot be served exits 1, each with a one-line error.

### Added

- `pip install` from a checkout, an sdist, or a git URL, including editable installs, through an in-tree build backend that uses the standard library only, so installing downloads nothing. Wheels and sdists are reproducible, and `buildsys/sql_rag_util_build.py` builds both.
- `SqlRag(..., tools=(...))` serves the developer's own `ToolSpec` tools beside the built-in ones through `dispatch`, the Anthropic, OpenAI, and MCP adapters, and the MCP server, under the same tier and write rules. A taken name raises `ToolSpecError` before the database is read.
- `sql_rag_util.dbapi` with `Connection` and `Cursor` protocols naming the part of PEP 249 the package uses, and `Catalog.require` for lookups that must succeed.
- Project metadata in the PEP 639 form: an SPDX `license` expression with `license-files`, keywords, classifiers, and documentation, changelog, and issue links; a `py.typed` marker so type checkers read the package's annotations.
- Documentation: an SDK page for tool authors, a Deployment section in the threat model (read-only database user, statement timeouts, scope values, cache), and design notes on hidden columns, trusted scope filters, the build backend, and CI.

### Changed

- Hidden columns raise `UnknownColumnError` where 0.1.0 raised `SensitiveColumnError`. Breaking for callers that matched the old error type.
- Developer scope filters may use hidden and sensitive columns, including through relationship paths, as the design notes promised; before, they were refused like the agent's own filters. A broken scope reports one generic `ConfigurationError` that names no column.
- A column flagged `fulltext` can no longer also be `sensitive` or `hidden`, and duplicate column, relationship, concept, and measure names in a table file are format errors.
- Every signature is fully annotated without inline type-checker suppressions; `register_sqlite_functions` is typed to take a `sqlite3.Connection`.

### Removed

- `SqlRag.raw_catalog`, which nothing used.

### Fixed

- Results are always strict JSON. NaN and infinite floats and decimals become `"NaN"`, `"Infinity"`, and `"-Infinity"`, a decimal infinity or signaling NaN no longer raises out of dispatch, and huge integral decimals become text. The MCP server refuses `NaN` and `Infinity` in requests and answers a response it cannot encode with `-32603` instead of stopping.
- The MCP server reports the package version by default instead of `0.0.0`, and answers a failure while handling a request with `-32603` instead of `-32600`.
- A driver failure while opening or closing a cursor is an `ExecutionError` like any other, a failure to close after a failed statement no longer hides the original error, and cursors that return mappings yield value tuples instead of key tuples.
- Metadata and cache writes keep the file's permissions instead of narrowing them to owner-only, and always write LF line endings, which the metadata parser requires, including on Windows.
- A failed `SqlRag.refresh()` leaves the engine as it was.

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

[Unreleased]: https://github.com/Paxton-Meny/sql_rag_util/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Paxton-Meny/sql_rag_util/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Paxton-Meny/sql_rag_util/releases/tag/v0.1.0
