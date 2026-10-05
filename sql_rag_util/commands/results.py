"""Shape fetched rows into JSON scalars and compact text."""

from __future__ import annotations

import datetime as dt
import decimal
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sql_rag_util.config import Limits

__all__ = ["JsonRows", "shape_rows", "table_text", "coerce_cell"]

JsonRows = list[list[object]]
_ELLIPSIS = "…"
_WHITESPACE = str.maketrans({"\t": " ", "\n": " ", "\r": " "})
_MAX_INTEGER_DIGITS = 1000


def _non_finite(is_nan: bool, negative: bool) -> str:
    return "NaN" if is_nan else "-Infinity" if negative else "Infinity"


def coerce_cell(value: object, max_chars: int) -> tuple[object, bool]:
    """Return a JSON scalar for ``value`` and whether it was truncated.

    Every result is valid strict JSON: NaN and infinities, which JSON cannot
    represent, become the strings ``"NaN"``, ``"Infinity"``, and
    ``"-Infinity"``, and decimals too large for a number become their text.
    """
    if value is None or isinstance(value, (bool, int)):
        return value, False
    if isinstance(value, float):
        return (value if math.isfinite(value) else _non_finite(math.isnan(value), value < 0)), False
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            return _non_finite(value.is_nan(), value.is_signed()), False
        if value == value.to_integral_value():
            return (int(value) if value.adjusted() < _MAX_INTEGER_DIGITS else str(value)), False
        number = float(value)
        return (number if math.isfinite(number) else str(value)), False
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ", timespec="seconds"), False
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat(), False
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(value)} bytes>", False
    text = value if isinstance(value, str) else str(value)
    if len(text) > max_chars:
        return text[:max_chars] + _ELLIPSIS, True
    return text, False


def shape_rows(rows: Sequence[Sequence[object]], limits: Limits) -> tuple[JsonRows, int]:
    """Return JSON-ready rows and the number of truncated cells."""
    out: JsonRows = []
    truncated = 0
    for row in rows:
        shaped = []
        for value in row:
            cell, cut = coerce_cell(value, limits.max_cell_chars)
            truncated += cut
            shaped.append(cell)
        out.append(shaped)
    return out, truncated


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).translate(_WHITESPACE)


def table_text(columns: Sequence[str], rows: JsonRows) -> str:
    """Return a header line and one tab-separated line per row."""
    lines = ["\t".join(columns)]
    lines.extend("\t".join(_cell_text(v) for v in row) for row in rows)
    return "\n".join(lines)
