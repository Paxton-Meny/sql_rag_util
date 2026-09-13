"""American Soundex, from the published definition.

Letters map to digits; adjacent letters with the same digit are coded once;
letters separated by H or W are treated as adjacent; letters separated by a
vowel are coded separately. The result is the first letter plus three
digits, zero padded.
"""

from __future__ import annotations

__all__ = ["soundex"]

_CODES = {
    **dict.fromkeys("BFPV", "1"),
    **dict.fromkeys("CGJKQSXZ", "2"),
    **dict.fromkeys("DT", "3"),
    "L": "4",
    **dict.fromkeys("MN", "5"),
    "R": "6",
}
_SEPARATORS = frozenset("HW")
_LENGTH = 4


def soundex(text: str | None) -> str | None:
    """Return the Soundex code of ``text``, or ``None`` for empty input."""
    if text is None:
        return None
    letters = [c for c in text.upper() if "A" <= c <= "Z"]
    if not letters:
        return None
    code = letters[0]
    previous = _CODES.get(letters[0], "")
    for letter in letters[1:]:
        digit = _CODES.get(letter, "")
        if digit and digit != previous:
            code += digit
        if letter not in _SEPARATORS:
            previous = digit
        if len(code) == _LENGTH:
            break
    return code.ljust(_LENGTH, "0")
