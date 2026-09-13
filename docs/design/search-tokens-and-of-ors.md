# Search words are AND-ed, columns and strategies OR-ed

## Decision

A term is split into words; each word is OR-ed across the searchable columns and the chosen strategies, and the words are AND-ed by default. SQLite functions compare a word against each word of the column value.

## Alternative weighed

Bind the whole term once per column.

## Why the alternative lost

Soundex of a full name never equals Soundex of one of its words, so a misspelled full name against first and last name columns could not match. Per-word matching is what makes the stated use case work, and the SQLite functions extend it to single full-name columns.
