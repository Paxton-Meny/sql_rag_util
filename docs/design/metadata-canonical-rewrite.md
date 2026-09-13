# Metadata edits rewrite the file canonically

## Decision

An edit loads the file, replaces the entry in the model, and writes the whole file in canonical form atomically.

## Alternative weighed

Edit the Markdown text in place.

## Why the alternative lost

In-place edits must reproduce every formatting choice and fail on files written by hand. Parse, replace, render keeps one writer, and the byte-exact round-trip test proves it loses nothing.
