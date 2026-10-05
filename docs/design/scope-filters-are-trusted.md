# Scope filters are trusted

## Decision

Predicates from `Config.scope` resolve against the full catalog, hidden columns included, and skip the column policy, so they may filter on hidden and sensitive columns and reach them through relationship paths. Every other predicate keeps the policy: the agent's own filters, and concepts, because agents read concepts on cards and can write them through `edit_concept`. A scope that does not resolve or does not fit its column is reported as one `ConfigurationError` that names no column, with the cause chained for the developer, because the agent receives the error.

## Alternative weighed

Hold scope filters to the same policy as the agent's filters, and tell developers to leave tenant and owner columns unflagged.

## Why the alternative lost

The policy exists so an agent cannot probe a secret with a sequence of filters. A scope filter is written by the developer, applied to every statement, and invisible to the agent, which can neither see nor vary its predicate, so there is nothing to probe. Refusing it made the most common isolation pattern, scoping every query to the signed-in tenant through a column the agent should not see, impossible without exposing that column. The rule the developer must keep is that scope values come from the application's own session, never from text the agent supplied.
