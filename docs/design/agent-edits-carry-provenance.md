# Agent edits carry provenance

## Decision

Every column entry written through the toolkit gets `source: agent, <date>`; developer entries carry no source line.

## Alternative weighed

Treat agent and developer entries alike.

## Why the alternative lost

A developer reviewing the metadata needs to know which lines a model inferred. The line is part of the format, round-trips, and costs nothing when absent.
