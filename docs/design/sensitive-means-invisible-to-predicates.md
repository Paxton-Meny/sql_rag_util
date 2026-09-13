# Sensitive columns are invisible to predicates

## Decision

A column flagged `sensitive` cannot appear in any position of a statement: not selected, filtered, ordered, grouped, searched, indexed, or sampled. `describe_table` still shows its name with the flag so the agent does not invent it.

## Alternative weighed

Exclude sensitive columns from results only, and allow them in filters so an agent can look up a row by, say, email.

## Why the alternative lost

A filter on a secret is an oracle. `password_hash starts_with "a"` followed by `starts_with "ab"` recovers the value in a few dozen calls, and an equality filter confirms a guess in one. Lookups by a sensitive value belong to the developer, who can expose them through a scope filter or a concept that the agent cannot read. The cost is that agents cannot search by email unless the developer marks the column searchable instead of sensitive, which is the developer's call to make.
