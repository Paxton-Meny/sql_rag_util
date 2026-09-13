"""Turn an agent's search term into bounded tokens."""

from __future__ import annotations

from sql_rag_util.exceptions import LimitExceededError, QuerySpecError

__all__ = ["tokenize_term"]

_MAX_TOKEN_CHARS = 100


def tokenize_term(term: str, *, max_tokens: int) -> tuple[str, ...]:
    """Split ``term`` on whitespace into at most ``max_tokens`` non-empty tokens.

    Raises
    ------
    QuerySpecError
        When the term is empty or a token is unreasonably long.
    LimitExceededError
        When there are more tokens than allowed.
    """
    if not isinstance(term, str):
        raise QuerySpecError("term must be a string")
    tokens = tuple(dict.fromkeys(t for t in term.split() if t))
    if not tokens:
        raise QuerySpecError("term must contain at least one word")
    if len(tokens) > max_tokens:
        raise LimitExceededError(f"term has {len(tokens)} words; at most {max_tokens} are searched")
    if any(len(t) > _MAX_TOKEN_CHARS for t in tokens):
        raise QuerySpecError(f"a search word may have at most {_MAX_TOKEN_CHARS} characters")
    return tokens
