# No statement timeouts in the first release

## Decision

The package sets no timeout on statements. Each driver's own timeout mechanism is documented for the caller.

## Alternative weighed

Emit a per-statement timeout for each dialect.

## Why the alternative lost

PostgreSQL needs session state inside a transaction, MySQL uses an optimizer hint MariaDB lacks, SQL Server has no statement syntax for it, and SQLite uses a progress handler. Each conflicts with the rule that the package never changes session state; the caps on rows and joins bound the work instead.
