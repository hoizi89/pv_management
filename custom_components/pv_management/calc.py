"""Reine Rechenlogik fuer PV Management.

Bewusst frei von Home-Assistant-Imports, damit die Funktionen ohne laufendes
HA getestet werden koennen (siehe tests/). Der Controller in __init__.py ruft
diese Funktionen auf, statt die Formeln selbst zu duplizieren.
"""

from __future__ import annotations

from datetime import datetime


def total_savings(
    accumulated_self: float,
    accumulated_feed: float,
    offset: float,
    yearly_costs: float,
) -> float:
    """Gesamtersparnis = Eigenverbrauch-Ersparnis + Einspeise-Erloes + Offset - Jahreskosten."""
    return accumulated_self + accumulated_feed + offset - yearly_costs


def helper_offset(helper_value: float, accumulated: float, yearly_costs: float) -> float:
    """Offset, mit dem ``total_savings`` exakt dem Helper-Wert entspricht.

    Der Helper speichert die *Gesamtersparnis* (also bereits abzueglich der
    Jahreskosten). ``total_savings`` zieht die Jahreskosten selbst noch einmal
    ab - deshalb muessen sie hier wieder dazugezaehlt werden, sonst schrumpft
    die Ersparnis bei jedem Neustart um die bis dahin aufgelaufenen Kosten.

    Bei ``restore_from_helper`` ist der Helper die Wahrheit, darum wird der
    Offset nicht auf >= 0 geklemmt.
    """
    return helper_value - accumulated + yearly_costs


def start_of_day(now: datetime) -> datetime:
    """Beginn des lokalen Tages von ``now`` (Zeitzone von ``now`` bleibt erhalten).

    Wird als ``last_reset`` fuer taeglich zurueckgesetzte TOTAL-Sensoren genutzt.
    """
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def start_of_month(now: datetime) -> datetime:
    """Beginn des lokalen Monats von ``now``."""
    return start_of_day(now).replace(day=1)


# Obergrenze fuer ein einzelnes Energie-Delta im laufenden Betrieb (kWh)
MAX_DELTA_KWH = 50.0


def max_plausible_delta_kwh(
    gap_hours: float | None,
    power_kw: float,
    base: float = MAX_DELTA_KWH,
) -> float:
    """Obergrenze fuer ein Energie-Delta, das ohne Re-Baseline verbucht wird.

    Im laufenden Betrieb gilt ``base``. Nach einem Neustart mit persistierten
    Zaehlerstaenden enthaelt das erste Delta die komplette Energie der
    HA-Downtime - dann darf es um ``power_kw * gap_hours`` groesser sein,
    sonst wuerde die Downtime-Energie verworfen.
    """
    if not gap_hours or gap_hours <= 0:
        return base
    return base + max(power_kw, 0.0) * gap_hours
