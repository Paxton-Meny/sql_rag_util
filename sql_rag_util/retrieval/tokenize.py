"""Turn identifiers, prose, and questions into comparable tokens."""

from __future__ import annotations

import re

__all__ = ["tokenize", "STOPWORDS"]

STOPWORDS: frozenset[str] = frozenset(
    "a an and are as at be by for from how in is it of on or that the this to was what when where which who with".split()
)
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_WORD = re.compile(r"[^a-z0-9]+")
_MIN_LENGTH = 2


def _singular(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def tokenize(text: str) -> tuple[str, ...]:
    """Split ``text`` on case changes, underscores, and punctuation; fold, singularize, drop stopwords."""
    spaced = _CAMEL.sub(" ", text)
    tokens = []
    for raw in _NON_WORD.split(spaced.lower()):
        if len(raw) < _MIN_LENGTH or raw in STOPWORDS:
            continue
        tokens.append(_singular(raw))
    return tuple(tokens)
