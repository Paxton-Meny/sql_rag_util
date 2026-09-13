# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The search_rows tool: word-level matching across searchable columns with contains plus the fuzzy strategies the connection supports; word-aware SQLite functions.
- Retrieval tokenizer (case, underscore, plural folding, stopwords) and a BM25 index with weighted fields.
- Dialect fuzzy predicates: Soundex on all four, DIFFERENCE and FREETEXT on SQL Server, levenshtein_less_equal, similarity, and difference on PostgreSQL, registered functions on SQLite.
- Search primitives: term tokenizing, American Soundex, bounded Levenshtein, and explicit SQLite function registration.
- SqlRag.instructions() workflow block and the agent tool reference in docs/agent-tools.md.
- The query tool: concepts, named measures, scope filters, shaped rows, notes, optional revealed SQL.
- Schema cards and the describe_table and list_tables tools.
- SqlRag engine facade: detection, introspection, metadata annotation, scope filters, tool listing by tier, dispatch; result shaping to JSON scalars and tab-separated text.
- Argument building from JSON, the tool registry with tiers and mutation gating, and the dispatcher with JSON and compact envelopes.
- Tool specs with tiers and JSON Schema derivation from argument dataclasses; every query spec field now carries the description agents read.
- Catalog annotation: metadata validated against the catalog, relationship renames and declared relationships applied, column policy, concepts and measures, schema version hash.
- Metadata store with root containment, whole-directory load, and atomic saves.
- Canonical metadata writer and an atomic text write helper; fixtures round-trip byte for byte.
- Per-file metadata parsers for tables, project, relationships, and glossary, with JSON concepts and measures validated through the query spec.
- Metadata model and the document layer of the strict parser (title, header, sections, bullets) with located errors.
- Query compiler: one bounded SELECT per spec with default primary-key ordering, aggregate idioms, extra filters, and agent notes.
- Join planning through relationship paths with depth cap and fan-out detection; measure expressions with kind gates.
- Column policy (hidden and sensitive) and filter predicates with kind gates, bound IN lists, LIKE escaping, and Python-computed since_days bounds.
- Query spec: Filter, Measure, Order, and QuerySpec with operator and aggregate whitelists validated on construction.
- Name resolution for tables, columns, and relationships with close-match suggestions.
- Catalog introspection: tables, columns, keys, implied key targets, capabilities, and a structural fingerprint.
- Relationship derivation from foreign keys with collision-free naming.
- Executor: the single execution site, fetching limit plus one, closing cursors, never committing, firing the audit hook.
- PostgreSQL dialect: ILIKE matching, udt-aware kinds, information_schema introspection, extension probe.
- SQL Server dialect: bracket quoting, bound TOP, INFORMATION_SCHEMA introspection with partition row estimates.
- MySQL and MariaDB dialect: backtick quoting, COLUMN_TYPE kinds, information_schema introspection.
- SQLite dialect: declared-type and affinity kinds, bound pragma table-valued introspection, function probe.
- Driver detection and a lazy dialect registry with aliases.
- Dialect contract and capability names.
- Statement model (fragments plus binds) and a renderer for every PEP 249 paramstyle.
- Config and Limits with validation, the scope hook, and the statement audit hook.
- Catalog model: frozen TableRef, ColumnInfo, TableInfo, ForeignKeyInfo, Relationship, Catalog, and ColumnKind.
- Exceptions module: one base class, agent-correctable suggestions, located metadata errors.
- Architecture overview and threat model under `docs/`.
- Metadata format specification, version 1, and the first design notes under `docs/design/`.
- Repository scaffolding: license, contribution guide, security policy, issue and pull request templates, pre-commit gate, package and test skeleton.

[Unreleased]: https://github.com/Paxton-Meny/sql_rag_util/commits/main
