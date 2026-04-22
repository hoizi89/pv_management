"""
Load Forecast für PV Management Fixpreis.

Methode: Hour-of-Day × Day-of-Week Profile (24×7 Matrix) über die letzten N Wochen.
Fallbacks:
  <14 Tage Historie → 7-Tage-Mittel
  <3 Tage Historie  → Persistenz (gleiche Stunde gestern/letzte Woche)
  keine Daten       → None (Sensor unavailable, kein Crash)

Der Forecaster ist vollständig optional und wird nur instanziiert wenn
CONF_FORECAST_ENABLED=True. Er blockiert den Event Loop nicht —
Recorder-Abfragen laufen im Executor.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, date
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    FORECAST_REFRESH_SECONDS,
    FORECAST_MIN_DAYS_FULL,
    FORECAST_MIN_DAYS_ANY,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen (pure, einfach testbar ohne HA)
# ---------------------------------------------------------------------------

def _hourly_delta(cum_values: list[tuple[datetime, float]]) -> dict[datetime, float]:
    """
    Wandelt kumulative kWh-Werte (Energiezähler) in Delta pro Stunde um.
    Eingabe: sortierte Liste (start_ts, cumulative_kwh).
    Ausgabe: {stunden-startzeit: delta_kwh} — nicht-negativ, Resets/Rückläufer werden verworfen.
    """
    out: dict[datetime, float] = {}
    prev_val: float | None = None
    for ts, val in cum_values:
        if prev_val is not None:
            delta = val - prev_val
            # Meter-Reset (Zählerstand springt zurück) oder Garbage → überspringen
            if delta >= 0 and delta < 100:  # >100 kWh in einer Stunde = Unsinn
                out[ts] = delta
        prev_val = val
    return out


def _modal_drop(values: list[float]) -> list[float]:
    """
    Entfernt den niedrigsten und den höchsten Wert (je 1). Bei <4 Werten passiert nichts.
    """
    if len(values) < 4:
        return values
    sorted_v = sorted(values)
    return sorted_v[1:-1]


# ---------------------------------------------------------------------------
# LoadForecaster
# ---------------------------------------------------------------------------

class LoadForecaster:
    """
    Pflegt eine 24x7 Matrix historischer Stundenverbräuche und liefert Prognosen.

    Datenquelle: Home Assistant Recorder via `recorder.statistics_during_period`
    mit `period="hour"`. Das gibt uns stündliche "sum"-Werte für Energiezähler
    (monoton steigend). Wir bilden die Differenz pro Stunde → stündlicher Verbrauch.

    Die Matrix wird beim Start einmal gebaut und danach stündlich aktualisiert.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        consumption_entity: str,
        hp_entity: str | None,
        ev_entity: str | None,
        weeks: int,
        modal_drop: bool,
        on_update: Callable[[], None] | None = None,
    ):
        self.hass = hass
        self.consumption_entity = consumption_entity
        self.hp_entity = hp_entity
        self.ev_entity = ev_entity
        self.weeks = weeks
        self.modal_drop = modal_drop
        self._on_update = on_update

        # 24x7 matrix: matrix[hour][weekday] = mean kWh (weekday 0=Mo, 6=So)
        self._matrix: list[list[float | None]] = [[None] * 7 for _ in range(24)]
        # std deviation per cell (for confidence band)
        self._std: list[list[float | None]] = [[None] * 7 for _ in range(24)]
        # Anzahl der Messpunkte je Zelle (Datenbasis)
        self._n: list[list[int]] = [[0] * 7 for _ in range(24)]

        self._method: str = "initializing"
        self._days_of_history: int = 0
        self._last_update: datetime | None = None
        self._last_error: str | None = None

        # 7-day fallback (flat mean)
        self._fallback_7d_mean_per_hour: float | None = None
        # Persistence fallback: {hour_of_day: kwh_vor_einer_woche}
        self._persistence_last_week: dict[int, float] = {}

        self._unsub_interval: Callable[[], None] | None = None
        self._base_load_only: bool = bool(hp_entity or ev_entity)

    # ---- lifecycle -----------------------------------------------------------

    async def async_start(self) -> None:
        """Baut initial die Matrix und plant stündliche Aktualisierungen."""
        try:
            await self._rebuild()
        except Exception as e:  # defensiv — darf Integration nicht killen
            _LOGGER.warning("LoadForecaster: initialer Build fehlgeschlagen: %s", e)
            self._method = "error"
            self._last_error = str(e)

        self._unsub_interval = async_track_time_interval(
            self.hass,
            self._async_scheduled_refresh,
            timedelta(seconds=FORECAST_REFRESH_SECONDS),
        )

    async def async_stop(self) -> None:
        """Stoppt den stündlichen Refresh."""
        if self._unsub_interval is not None:
            try:
                self._unsub_interval()
            except Exception:
                pass
            self._unsub_interval = None

    # ---- forecast API (von Sensoren aufgerufen) ------------------------------

    def forecast_next_hours(self, hours: int, now: datetime | None = None) -> float | None:
        """
        Prognose für die nächsten `hours` Stunden ab jetzt.
        Returns kWh oder None (wenn Datenbasis zu dünn).
        """
        if hours <= 0:
            return 0.0
        anchor = dt_util.as_local(now or dt_util.utcnow())
        total = 0.0
        valid_cells = 0
        for offset in range(hours):
            cell_time = anchor + timedelta(hours=offset)
            v = self._cell_value(cell_time.hour, cell_time.weekday())
            if v is None:
                # letzter Ausweg: fallback_7d oder Persistenz
                v = self._fallback_for_hour(cell_time.hour)
            if v is None:
                return None  # nicht genug Daten für irgendein Cell
            total += v
            valid_cells += 1
        if valid_cells == 0:
            return None
        return round(total, 2)

    def forecast_today_rest(self, now: datetime | None = None) -> float | None:
        """Prognose für die Reststunden des heutigen Tages (bis 23:59)."""
        anchor = dt_util.as_local(now or dt_util.utcnow())
        remaining = 24 - anchor.hour
        return self.forecast_next_hours(remaining, now=anchor)

    def forecast_tomorrow(self, now: datetime | None = None) -> float | None:
        """Prognose für den gesamten nächsten Tag (00:00–23:00)."""
        anchor = dt_util.as_local(now or dt_util.utcnow())
        start_tomorrow = (anchor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.forecast_next_hours(24, now=start_tomorrow)

    def hourly_forecast(self, hours: int = 24, now: datetime | None = None) -> list[float | None]:
        """Liste von Stundenwerten ab jetzt, für Chart-Darstellung."""
        anchor = dt_util.as_local(now or dt_util.utcnow())
        out: list[float | None] = []
        for offset in range(hours):
            t = anchor + timedelta(hours=offset)
            v = self._cell_value(t.hour, t.weekday())
            if v is None:
                v = self._fallback_for_hour(t.hour)
            out.append(round(v, 2) if v is not None else None)
        return out

    def confidence_band(self, hours: int = 24, now: datetime | None = None) -> tuple[float | None, float | None]:
        """Summe ±1σ über N Stunden (für low/high Attribute)."""
        anchor = dt_util.as_local(now or dt_util.utcnow())
        total = 0.0
        variance_sum = 0.0
        ok = True
        for offset in range(hours):
            t = anchor + timedelta(hours=offset)
            m = self._cell_value(t.hour, t.weekday())
            s = self._std[t.hour][t.weekday()]
            if m is None:
                m = self._fallback_for_hour(t.hour)
            if m is None:
                ok = False
                break
            total += m
            if s is not None:
                variance_sum += s * s
        if not ok:
            return (None, None)
        sigma = math.sqrt(variance_sum) if variance_sum > 0 else 0.0
        return (round(max(0.0, total - sigma), 2), round(total + sigma, 2))

    # ---- diagnostic/state ----------------------------------------------------

    @property
    def method(self) -> str:
        return self._method

    @property
    def days_of_history(self) -> int:
        return self._days_of_history

    @property
    def last_update(self) -> datetime | None:
        return self._last_update

    @property
    def base_load_only(self) -> bool:
        return self._base_load_only

    @property
    def last_error(self) -> str | None:
        return self._last_error

    # ---- internal: matrix building ------------------------------------------

    def _cell_value(self, hour: int, weekday: int) -> float | None:
        if self._method == "24x7_profile":
            return self._matrix[hour][weekday]
        if self._method == "fallback_7d_mean":
            return self._fallback_7d_mean_per_hour
        if self._method == "fallback_persistence":
            return self._persistence_last_week.get(hour)
        return None

    def _fallback_for_hour(self, hour: int) -> float | None:
        if self._fallback_7d_mean_per_hour is not None:
            return self._fallback_7d_mean_per_hour
        return self._persistence_last_week.get(hour)

    async def _async_scheduled_refresh(self, _now: datetime) -> None:
        try:
            await self._rebuild()
            if self._on_update is not None:
                self._on_update()
        except Exception as e:
            _LOGGER.warning("LoadForecaster: geplantes Rebuild fehlgeschlagen: %s", e)
            self._last_error = str(e)

    async def _rebuild(self) -> None:
        """Holt Statistics, aktualisiert Matrix + Fallbacks."""
        if not self.consumption_entity:
            self._method = "no_entity"
            return

        end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=self.weeks * 7)

        hourly_consumption = await self._fetch_hourly_delta(
            self.consumption_entity, start, end
        )
        if self.hp_entity:
            hp_hourly = await self._fetch_hourly_delta(self.hp_entity, start, end)
            hourly_consumption = _subtract_hourly(hourly_consumption, hp_hourly)
        if self.ev_entity:
            ev_hourly = await self._fetch_hourly_delta(self.ev_entity, start, end)
            hourly_consumption = _subtract_hourly(hourly_consumption, ev_hourly)

        if not hourly_consumption:
            self._method = "no_data"
            self._days_of_history = 0
            self._last_update = dt_util.utcnow()
            return

        days_span = (max(hourly_consumption) - min(hourly_consumption)).days + 1
        self._days_of_history = max(0, days_span)
        self._last_update = dt_util.utcnow()

        # Fallback-Daten parallel aufbauen
        self._update_fallback_structures(hourly_consumption)

        # Methode entscheiden
        if self._days_of_history >= FORECAST_MIN_DAYS_FULL:
            self._build_24x7_matrix(hourly_consumption)
            self._method = "24x7_profile"
        elif self._days_of_history >= FORECAST_MIN_DAYS_ANY:
            self._method = "fallback_7d_mean"
        elif self._persistence_last_week:
            self._method = "fallback_persistence"
        else:
            self._method = "warming_up"

        self._last_error = None

    def _build_24x7_matrix(self, hourly: dict[datetime, float]) -> None:
        """Baut 24×7 Matrix mit Mittelwert + optional Modal-Drop + Std."""
        buckets: list[list[list[float]]] = [[[] for _ in range(7)] for _ in range(24)]
        for ts, kwh in hourly.items():
            local_ts = dt_util.as_local(ts)
            buckets[local_ts.hour][local_ts.weekday()].append(kwh)

        for h in range(24):
            for d in range(7):
                vals = buckets[h][d]
                if self.modal_drop:
                    vals = _modal_drop(vals)
                if not vals:
                    self._matrix[h][d] = None
                    self._std[h][d] = None
                    self._n[h][d] = 0
                    continue
                mean = sum(vals) / len(vals)
                var = sum((v - mean) ** 2 for v in vals) / len(vals)
                self._matrix[h][d] = mean
                self._std[h][d] = math.sqrt(var)
                self._n[h][d] = len(vals)

    def _update_fallback_structures(self, hourly: dict[datetime, float]) -> None:
        """Füllt 7-Tage-Mittel + Persistenz-Map."""
        now = dt_util.utcnow()
        last7_start = now - timedelta(days=7)
        last7_vals = [v for ts, v in hourly.items() if ts >= last7_start]
        self._fallback_7d_mean_per_hour = (
            sum(last7_vals) / len(last7_vals) if last7_vals else None
        )

        week_ago_from = now - timedelta(days=7, hours=1)
        week_ago_to = now - timedelta(days=6)
        self._persistence_last_week.clear()
        for ts, v in hourly.items():
            if week_ago_from <= ts < week_ago_to + timedelta(hours=24):
                local = dt_util.as_local(ts)
                self._persistence_last_week[local.hour] = v

    # ---- data fetching -------------------------------------------------------

    async def _fetch_hourly_delta(
        self, entity_id: str, start: datetime, end: datetime
    ) -> dict[datetime, float]:
        """Holt stündliche Cumulative Statistics und bildet Deltas."""
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import (
                statistics_during_period,
            )
        except ImportError:
            _LOGGER.debug("Recorder-Komponente nicht verfügbar")
            return {}

        def _run():
            return statistics_during_period(
                self.hass,
                start,
                end,
                {entity_id},
                "hour",
                None,
                {"sum", "state"},
            )

        try:
            raw = await get_instance(self.hass).async_add_executor_job(_run)
        except Exception as e:
            _LOGGER.debug("Recorder-Query für %s fehlgeschlagen: %s", entity_id, e)
            return {}

        series = raw.get(entity_id) if isinstance(raw, dict) else None
        if not series:
            return {}

        # Recorder liefert entweder "sum" (gesamter accumulator) oder "state"
        # (aktueller Zählerstand). Für Energiezähler hat "sum" die Eigenschaft,
        # dass Differenzen direkt die verbrauchte Energie in dem Zeitraum sind.
        cumulative: list[tuple[datetime, float]] = []
        for row in series:
            try:
                ts = row.get("start")
                # Prefer state (absolute reading) — robuster als sum, bricht sauber bei Reset
                val = row.get("state")
                if val is None:
                    val = row.get("sum")
                if ts is None or val is None:
                    continue
                if isinstance(ts, (int, float)):
                    # ts may be Unix timestamp; convert
                    ts = datetime.fromtimestamp(ts, tz=dt_util.UTC)
                cumulative.append((ts, float(val)))
            except (TypeError, ValueError):
                continue

        cumulative.sort(key=lambda x: x[0])
        return _hourly_delta(cumulative)


def _subtract_hourly(a: dict[datetime, float], b: dict[datetime, float]) -> dict[datetime, float]:
    """Zieht b von a ab, nicht-negativ. Fehlende Keys in b = 0."""
    out: dict[datetime, float] = {}
    for ts, va in a.items():
        vb = b.get(ts, 0.0)
        diff = va - vb
        out[ts] = diff if diff > 0 else 0.0
    return out
