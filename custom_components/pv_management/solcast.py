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
    weight: float = 0.0,
) -> list[Optional[float]]:
    """The expected output for each hour of ``day``, 00:00 to 23:00, in kW.

    With ``key="pv_estimate"`` and a ``weight`` > 0 the value is the P50/P10
    blend (see ``blend``); rows without ``pv_estimate10`` fall back to P50.

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
        if key == "pv_estimate" and weight:
            kw = row_estimate(row, weight)
            if kw is None:
                continue
        else:
            try:
                kw = float(row.get(key))
            except (TypeError, ValueError):
                continue
        values.setdefault(local.hour, []).append(kw)

    out: list[Optional[float]] = [None] * 24
    for hour, kws in values.items():
        out[hour] = round(sum(kws) / len(kws), 3)
    return out


# --- P50/P10-Gewichtung (Issue #18) -------------------------------------------


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def blend(p50: Optional[float], p10: Optional[float], weight: float) -> Optional[float]:
    """Lineare Mischung aus P50 und P10.

    ``weight`` 0 = 100 % P50 (Standard, bisheriges Verhalten), 1 = 100 % P10,
    dazwischen linear. Fehlt P10, wird sauber P50 verwendet.
    """
    if p50 is None:
        return None
    try:
        w = min(1.0, max(0.0, float(weight or 0.0)))
    except (TypeError, ValueError):
        w = 0.0
    if p10 is None or w == 0.0:
        return p50
    return (1.0 - w) * p50 + w * p10


def row_estimate(row: Any, weight: float) -> Optional[float]:
    """Gewichtete Leistung (kW) einer Solcast-Periode (pv_estimate/pv_estimate10)."""
    if not isinstance(row, dict):
        return None
    return blend(_as_float(row.get("pv_estimate")), _as_float(row.get("pv_estimate10")), weight)


def day_estimates(state_value: Optional[float], attributes: Any) -> tuple[Optional[float], Optional[float]]:
    """(P50, P10) der Tagesprognose in kWh; P10 ist ``None`` ohne P10-Daten.

    P50 kommt aus dem Attribut ``estimate`` (falls vorhanden, sonst der State),
    P10 aus ``estimate10``. Fehlt ``estimate10``, wird P10 aus den Perioden
    (``detailedForecast``/``detailedHourly``) ueber das Verhaeltnis
    Summe(pv_estimate10) / Summe(pv_estimate) abgeleitet.
    """
    attrs = attributes if isinstance(attributes, dict) else {}
    p50 = _as_float(attrs.get("estimate"))
    if p50 is None:
        p50 = _as_float(state_value)
    if p50 is None:
        return None, None

    p10 = _as_float(attrs.get("estimate10"))
    if p10 is None:
        for key in ("detailedForecast", "detailedHourly"):
            rows = attrs.get(key)
            if not isinstance(rows, list) or not rows:
                continue
            sum50 = 0.0
            sum10 = 0.0
            complete = True
            for row in rows:
                if not isinstance(row, dict):
                    continue
                v50 = _as_float(row.get("pv_estimate"))
                if v50 is None:
                    continue
                v10 = _as_float(row.get("pv_estimate10"))
                if v10 is None:
                    complete = False
                    break
                sum50 += v50
                sum10 += v10
            if complete and sum50 > 0:
                p10 = p50 * (sum10 / sum50)
                break
    return p50, p10


def day_total(state_value: Optional[float], attributes: Any, weight: float) -> Optional[float]:
    """Gewichtete Tagesprognose (kWh); ohne P10-Daten -> P50."""
    p50, p10 = day_estimates(state_value, attributes)
    return blend(p50, p10, weight)
