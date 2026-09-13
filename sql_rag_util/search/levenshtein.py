"""Edit distance with an optional bound, for SQLite registration and value matching."""

from __future__ import annotations

__all__ = ["levenshtein"]


def levenshtein(a: str | None, b: str | None, *, max_distance: int | None = None) -> int | None:
    """Return the edit distance between ``a`` and ``b``.

    With ``max_distance`` the search stops early and returns ``max_distance + 1``
    once the distance is known to exceed the bound. ``None`` inputs give ``None``.
    """
    if a is None or b is None:
        return None
    if len(a) < len(b):
        a, b = b, a
    if max_distance is not None and len(a) - len(b) > max_distance:
        return max_distance + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if max_distance is not None and min(current) > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]
