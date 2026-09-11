"""Solcast's hourly forecast as the 24 hours of one day.

Kept free of Home Assistant imports so it can be tested on its own; the
caller passes the conversion to local time.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Optional


def _start(value: Any) -> Optional[datetime]:
    """A row's period start, whether Solcast left it as a datetime or a string."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def hours_of_day(
    rows: Any,
    day: date,
    to_local: Callable[[datetime], datetime],
    key: str = "pv_estimate",
) -> list[Optional[float]]:
    """The expected output for each hour of ``day``, 00:00 to 23:00, in kW.

    Rows from another day are skipped, so a list that runs into tomorrow does
    not spill over. An hour the forecast does not cover stays ``None`` rather
    than a zero that would read as a dark hour. Several rows in one hour (half
    hours) are averaged.
    """
    values: dict[int, list[float]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        start = _start(row.get("period_start"))
        if start is None:
            continue
        local = to_local(start) if start.tzinfo is not None else start
        if local.date() != day:
            continue
        try:
            kw = float(row.get(key))
        except (TypeError, ValueError):
            continue
        values.setdefault(local.hour, []).append(kw)

    out: list[Optional[float]] = [None] * 24
    for hour, kws in values.items():
        out[hour] = round(sum(kws) / len(kws), 3)
    return out
