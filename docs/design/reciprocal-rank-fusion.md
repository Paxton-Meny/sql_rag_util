# Rankings are fused by reciprocal rank

## Decision

Lexical, value-hit, and embedding rankings are combined with reciprocal rank fusion, with a higher weight on value hits.

## Alternative weighed

Normalize each source's scores and add them.

## Why the alternative lost

BM25 scores, cosine similarities, and match qualities live on unrelated scales, and any normalization needs tuning per database. Rank fusion needs none and rewards tables several sources agree on.
