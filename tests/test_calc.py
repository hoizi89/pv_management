"""Reine Rechenfunktionen: Einheiten, last_reset, Helper-Offset, Delta-Grenze."""

from __future__ import annotations

from datetime import datetime

import pytest

from conftest import LOCAL_TZ


@pytest.fixture
def calc(pvm):
    from pv_management import calc

    return calc


# ------------------------------------------------------------------ Einheiten


@pytest.mark.parametrize(
    "value, configured, uom, expected",
    [
        (25.0, "eur", "ct/kWh", 0.25),
        (-5.0, "eur", "ct/kWh", -0.05),          # negativer Spotpreis in Cent
        (0.8, "eur", "ct/kWh", 0.008),           # Cent-Wert <= 1
        (-0.05, "cent", "€/kWh", -0.05),         # Sensor-Einheit schlägt Konfiguration
        (0.12, "eur", "EUR/kWh", 0.12),
        (120.0, "eur", "EUR/MWh", 0.12),
        (-20.0, "eur", "€/MWh", -0.02),
        (12.0, "eur", "öre/kWh", 0.12),
    ],
)
def test_price_with_unit_of_measurement(calc, value, configured, uom, expected):
    assert calc.price_to_eur_per_kwh(value, configured, uom, auto_detect=True) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value, configured, expected",
    [
        (0.8, "cent", 0.008),     # konfigurierte Einheit Cent wird respektiert (≤ 1)
        (-0.5, "cent", -0.005),   # negativ + Cent
        (-3.0, "cent", -0.03),
        (25.0, "eur", 0.25),      # Altverhalten: Euro konfiguriert, |x| > 1 → Cent
        (-5.0, "eur", -0.05),     # negativ, früher -5 €/kWh!
        (0.25, "eur", 0.25),
        (-0.04, "eur", -0.04),
    ],
)
def test_price_without_uom(calc, value, configured, expected):
    assert calc.price_to_eur_per_kwh(value, configured, None, auto_detect=True) == pytest.approx(expected)


def test_price_manual_config_never_guesses(calc):
    # Konfigurierter Fixpreis: kein Auto-Detect
    assert calc.price_to_eur_per_kwh(30.0, "cent") == pytest.approx(0.30)
    assert calc.price_to_eur_per_kwh(1.5, "eur") == pytest.approx(1.5)


def test_price_unit_label(calc):
    assert calc.price_unit_label(-5, "eur", "ct/kWh", True) == "cent"
    assert calc.price_unit_label(100, "eur", "EUR/MWh", True) == "euro_per_mwh"
    assert calc.price_unit_label(0.2, "eur", None, True) == "euro"


def test_controller_uses_sensor_unit_for_negative_prices(make_ctrl):
    ctrl = make_ctrl(options={"electricity_price_entity": "sensor.p"},
                     states={"sensor.p": ("-5", {"unit_of_measurement": "ct/kWh"})})
    assert ctrl.current_electricity_price == pytest.approx(-0.05)
    ctrl.hass.states.set("sensor.p", "0.8", {})
    ctrl.electricity_price_unit = "cent"
    assert ctrl.current_electricity_price == pytest.approx(0.008)


@pytest.mark.parametrize(
    "entry, expected",
    [
        ({"price_per_kwh": 0.0}, 0.0),                 # 0 ist gültig (kein or-Fallthrough)
        ({"price_per_kwh": -0.03, "price": 99}, -0.03),
        ({"price_eur_per_mwh": -20.0}, -0.02),
        ({"price_ct_per_kwh": -4.0}, -0.04),
        ({"price": -0.02}, -0.02),                     # €/kWh, negativ
        ({"price": -150.0}, -0.15),                    # €/MWh, negativ
        ({"price": -5.0}, -0.05),                      # ct/kWh, negativ
        ({"foo": 1}, None),
    ],
)
def test_forecast_entry_price(calc, entry, expected):
    result = calc.forecast_entry_price_eur(entry)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


# ------------------------------------------------------------------ last_reset


def test_start_of_day_and_month(calc):
    now = datetime(2026, 9, 30, 17, 45, 12, 999, tzinfo=LOCAL_TZ)
    assert calc.start_of_day(now) == datetime(2026, 9, 30, 0, 0, tzinfo=LOCAL_TZ)
    assert calc.start_of_month(now) == datetime(2026, 9, 1, 0, 0, tzinfo=LOCAL_TZ)


def test_start_of_day_on_dst_change(calc):
    # 25.10.2026: Umstellung Sommer→Winterzeit in Wien
    now = datetime(2026, 10, 25, 20, 0, tzinfo=LOCAL_TZ)
    start = calc.start_of_day(now)
    assert (start.year, start.month, start.day, start.hour, start.minute) == (2026, 10, 25, 0, 0)
    assert start.utcoffset() != now.utcoffset()  # Mitternacht war noch Sommerzeit


def test_daily_sensor_last_reset_follows_local_day(make_ctrl, fixed_now):
    ctrl = make_ctrl()
    fixed_now(datetime(2026, 9, 30, 23, 59, tzinfo=LOCAL_TZ))
    assert ctrl.daily_last_reset == datetime(2026, 9, 30, tzinfo=LOCAL_TZ)
    fixed_now(datetime(2026, 10, 1, 0, 0, 5, tzinfo=LOCAL_TZ))
    assert ctrl.daily_last_reset == datetime(2026, 10, 1, tzinfo=LOCAL_TZ)


def test_midnight_rollover_resets_daily_values(make_ctrl, fixed_now):
    ctrl = make_ctrl()
    fixed_now(datetime(2026, 9, 30, 22, 0, tzinfo=LOCAL_TZ))
    ctrl._roll_periods()
    ctrl._daily_grid_import_kwh = 12.0
    ctrl._daily_grid_import_cost = 3.0
    fixed_now(datetime(2026, 10, 1, 0, 0, 5, tzinfo=LOCAL_TZ))
    ctrl._on_midnight()
    assert ctrl.daily_grid_import_kwh == 0.0
    assert ctrl.daily_grid_import_cost == 0.0


# ------------------------------------------------------------------ Helper / Deltas


def test_helper_offset_formula(calc):
    offset = calc.helper_offset(1000.0, accumulated=300.0, yearly_costs=100.0)
    assert offset == pytest.approx(800.0)
    assert calc.total_savings(250.0, 50.0, offset, 100.0) == pytest.approx(1000.0)
    # Helper ist die Wahrheit – auch wenn er unter den eigenen Akkumulatoren liegt
    assert calc.helper_offset(100.0, 300.0, 0.0) == pytest.approx(-200.0)


def test_clamp(calc):
    assert calc.clamp(15000, 0, 10000) == 10000
    assert calc.clamp(-5, "0", None) == 0
    assert calc.clamp(5, "x", "y") == 5


def test_max_plausible_delta(calc):
    assert calc.max_plausible_delta_kwh(None, 30) == calc.MAX_DELTA_KWH
    assert calc.max_plausible_delta_kwh(0, 30) == calc.MAX_DELTA_KWH
    assert calc.max_plausible_delta_kwh(10, 30) == pytest.approx(50 + 300)
