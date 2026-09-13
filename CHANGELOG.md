# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
