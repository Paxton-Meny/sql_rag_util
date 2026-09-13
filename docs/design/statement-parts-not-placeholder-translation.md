# Statements are parts, not text with placeholders

## Decision

A `Statement` is a tuple of string fragments and `Bind` values. One renderer walks the parts and emits the driver's paramstyle (`?`, `%s`, `%(p0)s`, `:p0`, `:1`) together with the parameter tuple or dict. Literal `%` in fragments is doubled only for the format styles. Builders never see a paramstyle.

## Alternative weighed

Build SQL text with one canonical placeholder and rewrite it per driver with a scan or regular expression.

## Why the alternative lost

Quoted identifiers may legally contain `?`, `:`, and `%` on PostgreSQL and SQLite, so a textual rewrite can corrupt a validated identifier and requires a second escaping pass for `%`. Keeping binding in one function that never inspects SQL text makes "parameter binding has exactly one implementation" literally true and makes the `%` rule a two-line concern. It also removes the `%` trigram operator trap on PostgreSQL entirely, since the package uses the `similarity()` function form.
