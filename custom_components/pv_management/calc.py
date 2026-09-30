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


# --- Preis-Einheiten ------------------------------------------------------------

# Wert von const.PRICE_UNIT_CENT (const.py importiert HA, darum hier dupliziert)
PRICE_UNIT_CENT = "cent"

# Waehrungs-Untereinheiten (1/100 der Hauptwaehrung)
_SUBUNITS = {"ct", "cent", "cents", "c", "¢", "eurocent", "eurct", "rp", "öre", "ore", "øre", "p"}

_DIVISOR_LABELS = {
    1.0: "euro",
    100.0: "cent",
    1000.0: "euro_per_mwh",
    100000.0: "cent_per_mwh",
}


def uom_price_divisor(uom: str | None) -> float | None:
    """Divisor nach €/kWh aus der unit_of_measurement eines Preis-Sensors.

    ``None`` wenn die Einheit fehlt oder nicht als Preis pro kWh/MWh erkennbar ist.
    """
    if not uom or not isinstance(uom, str):
        return None
    unit = uom.strip().lower().replace(" ", "")
    if unit.endswith("/kwh"):
        energy = 1.0
    elif unit.endswith("/mwh"):
        energy = 1000.0
    else:
        return None
    currency = unit.rsplit("/", 1)[0]
    if not currency:
        return None
    return (100.0 if currency in _SUBUNITS else 1.0) * energy


def price_divisor(
    value: float,
    configured_unit: str | None,
    uom: str | None = None,
    auto_detect: bool = False,
) -> float:
    """Divisor, mit dem ``value`` in €/kWh umgerechnet wird.

    Reihenfolge:
    1. Einheit des Sensors (unit_of_measurement), wenn eindeutig.
    2. Konfigurierte Einheit "Cent" wird immer respektiert - auch fuer Werte
       <= 1 ct oder negative Spotpreise.
    3. Nur bei konfiguriertem Euro (Default) und ``auto_detect``: Betrag > 1
       gilt als Cent (Altverhalten, jetzt mit abs() - negative Cent-Preise wie
       -5 ct werden nicht mehr als -5 €/kWh gelesen).
    """
    divisor = uom_price_divisor(uom)
    if divisor is not None:
        return divisor
    if configured_unit == PRICE_UNIT_CENT:
        return 100.0
    if auto_detect and abs(value) > 1.0:
        return 100.0
    return 1.0


def price_to_eur_per_kwh(
    value: float,
    configured_unit: str | None,
    uom: str | None = None,
    auto_detect: bool = False,
) -> float:
    """Rechnet einen Preis in €/kWh um (siehe ``price_divisor``)."""
    return value / price_divisor(value, configured_unit, uom, auto_detect)


def price_unit_label(
    value: float,
    configured_unit: str | None,
    uom: str | None = None,
    auto_detect: bool = False,
) -> str:
    """Erkannte Einheit als Text (fuer Diagnose-Attribute)."""
    return _DIVISOR_LABELS.get(price_divisor(value, configured_unit, uom, auto_detect), "unknown")


def forecast_entry_price_eur(entry: dict) -> float | None:
    """Preis eines Prognose-Eintrags (EPEX/Awattar/...) in €/kWh.

    Explizit benannte Felder werden eindeutig umgerechnet; bei generischen
    Feldern entscheidet der Betrag (negativ-sicher): >10 = €/MWh, <1 = €/kWh,
    sonst ct/kWh. Ein Preis von 0 ist gueltig (kein ``or``-Fallthrough).
    """
    if not isinstance(entry, dict):
        return None
    for key, divisor in (
        ("price_eur_per_mwh", 1000.0),
        ("price_per_kwh", 1.0),
        ("price_eur_per_kwh", 1.0),
        ("price_ct_per_kwh", 100.0),
    ):
        raw = entry.get(key)
        if raw is not None:
            try:
                return float(raw) / divisor
            except (TypeError, ValueError):
                return None
    for key in ("price", "total_price", "marketprice"):
        raw = entry.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if abs(value) > 10:
            return value / 1000.0
        if abs(value) < 1:
            return value
        return value / 100.0
    return None
