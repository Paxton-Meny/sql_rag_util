# No statement timeouts in the first release

## Decision

The package sets no timeout on statements. A caller who needs one sets it on the connection or the database before passing it in: `statement_timeout` on a PostgreSQL role or session, `max_execution_time` on MySQL (`max_statement_time` on MariaDB), the query timeout of the SQL Server driver (`timeout` on a pyodbc connection or in pymssql's `connect`), or a progress handler on a SQLite connection.

## Alternative weighed

Emit a per-statement timeout for each dialect.

## Why the alternative lost

PostgreSQL needs session state inside a transaction, MySQL uses an optimizer hint MariaDB lacks, SQL Server has no statement syntax for it, and SQLite uses a progress handler. Each conflicts with the rule that the package never changes session state; the caps on rows and joins bound the work instead.
