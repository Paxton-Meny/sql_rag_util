# LIKE patterns escape with an exclamation mark

## Decision

Substring and prefix predicates escape percent, underscore, and the escape character itself with `!` and say `ESCAPE '!'` in the statement.

## Alternative weighed

Use backslash, the common default.

## Why the alternative lost

A lone backslash inside a string literal is an unterminated escape in MySQL's default mode, so the same statement would break there. A punctuation character that no dialect treats specially works everywhere.
