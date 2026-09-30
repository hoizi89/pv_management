"""Ersparnis-Rechnung: Inkrementierung bei dynamischen Preisen, Helper-Restore, Offsets."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from conftest import LOCAL_TZ

PRICE = "sensor.epex_price"


def _ready(ctrl, pv=1000.0, export=400.0, imp=2000.0):
    """Controller in einen laufenden Zustand bringen (Baselines gesetzt)."""
    ctrl._pv_production_kwh = pv
    ctrl._grid_export_kwh = export
    ctrl._grid_import_kwh = imp
    ctrl._restored = True
    ctrl._process_energy_update()  # Init-Guard: _last_* setzen
    ctrl._process_energy_update()  # Baseline-Migration


def _step(ctrl, hass, price, d_pv=0.0, d_export=0.0, d_import=0.0):
    hass.states.set(PRICE, price, {"unit_of_measurement": "€/kWh"})
    ctrl._pv_production_kwh += d_pv
    ctrl._grid_export_kwh += d_export
    ctrl._grid_import_kwh += d_import
    ctrl._process_energy_update()


def test_increment_with_fluctuating_price(make_ctrl):
    """Jedes kWh-Delta wird mit dem DANN gültigen Preis bewertet (Issue #19)."""
    ctrl = make_ctrl(options={"electricity_price_entity": PRICE})
    hass = ctrl.hass
    hass.states.set(PRICE, 0.20, {"unit_of_measurement": "€/kWh"})
    _ready(ctrl)
    assert ctrl.savings_self_consumption == pytest.approx(0.0)

    _step(ctrl, hass, 0.10, d_pv=1.0)            # 1 kWh × 0.10
    _step(ctrl, hass, 0.50, d_pv=2.0)            # 2 kWh × 0.50
    _step(ctrl, hass, -0.05, d_pv=1.0)           # negativer Spotpreis
    expected = 1 * 0.10 + 2 * 0.50 + 1 * -0.05
    assert ctrl.savings_self_consumption == pytest.approx(expected)
    assert ctrl.self_consumption_kwh == pytest.approx(4.0)

    # Preis springt, aber keine neue Energie: Historie bleibt unverändert
    before_total = ctrl.total_savings
    for price in (3.0, -1.0, 0.8):
        _step(ctrl, hass, price)
        assert ctrl.savings_self_consumption == pytest.approx(expected)
        assert ctrl.total_savings == pytest.approx(before_total)


def test_feed_in_uses_tariff_at_that_time(make_ctrl):
    ctrl = make_ctrl(options={"feed_in_tariff_entity": "sensor.tariff"})
    hass = ctrl.hass
    hass.states.set("sensor.tariff", 8.0, {"unit_of_measurement": "ct/kWh"})
    _ready(ctrl)
    ctrl._pv_production_kwh += 3.0
    ctrl._grid_export_kwh += 3.0
    ctrl._process_energy_update()
    hass.states.set("sensor.tariff", 2.0, {"unit_of_measurement": "ct/kWh"})
    ctrl._pv_production_kwh += 1.0
    ctrl._grid_export_kwh += 1.0
    ctrl._process_energy_update()
    assert ctrl.earnings_feed_in == pytest.approx(3 * 0.08 + 1 * 0.02)


def test_feed_in_total_never_decreases(make_ctrl):
    """TOTAL_INCREASING: kurzer Rücksprung des Export-Zählers senkt den Total nicht."""
    ctrl = make_ctrl()
    _ready(ctrl)
    ctrl._grid_export_kwh += 2.0
    ctrl._pv_production_kwh += 2.0
    ctrl._process_energy_update()
    total = ctrl.feed_in_kwh
    ctrl._grid_export_kwh -= 0.3  # Glitch (< Reset-Schwelle)
    ctrl._process_energy_update()
    assert ctrl.feed_in_kwh == pytest.approx(total)
    ctrl._grid_export_kwh += 0.3  # zurück auf alten Stand → kein Doppelzählen
    ctrl._process_energy_update()
    assert ctrl.feed_in_kwh == pytest.approx(total)


def test_initial_history_uses_reference_price_not_spot(make_ctrl):
    """Historie wird EINMALIG mit dem konfigurierten Preis festgeschrieben."""
    ctrl = make_ctrl(
        data={"electricity_price": 0.30, "feed_in_tariff": 0.08},
        options={"electricity_price_entity": PRICE},
        states={
            "sensor.pv": ("5000", {"unit_of_measurement": "kWh"}),
            "sensor.export": ("2000", {"unit_of_measurement": "kWh"}),
            PRICE: ("-0.12", {"unit_of_measurement": "€/kWh"}),  # Mittags negativ
        },
    )
    ctrl._initialize_from_sensors()
    assert ctrl.savings_self_consumption == pytest.approx(3000 * 0.30)
    assert ctrl.earnings_feed_in == pytest.approx(2000 * 0.08)
    frozen = ctrl.total_savings

    # Spotpreis ändert sich den ganzen Tag — festgeschriebener Wert bleibt
    for price in (0.45, 0.02, -0.3):
        ctrl.hass.states.set(PRICE, price, {"unit_of_measurement": "€/kWh"})
        assert ctrl.total_savings == pytest.approx(frozen)


def _install(ctrl, days_ago, fixed_now):
    now = fixed_now(datetime(2026, 9, 30, 12, 0, tzinfo=LOCAL_TZ))
    ctrl.installation_date = (now.date() - timedelta(days=days_ago)).isoformat()
    return now


def test_helper_restore_includes_yearly_costs(make_ctrl, fixed_now):
    ctrl = make_ctrl(data={
        "amortisation_helper": "input_number.amort",
        "restore_from_helper": True,
        "yearly_cost": 365.0,
    })
    _install(ctrl, 100, fixed_now)            # → 100 € Jahreskosten aufgelaufen
    ctrl._accumulated_savings_self = 250.0
    ctrl._accumulated_earnings_feed = 50.0
    ctrl.hass.states.set("input_number.amort", "1000.0", {"min": 0, "max": 100000})

    import asyncio
    assert asyncio.run(ctrl._restore_from_helper()) is True
    assert ctrl.total_savings == pytest.approx(1000.0)

    # "Neustart": gleicher Helper-Wert → wieder exakt 1000, schrumpft nicht
    ctrl2 = make_ctrl(data=dict(ctrl.entry.data))
    _install(ctrl2, 100, fixed_now)
    ctrl2._accumulated_savings_self = 250.0
    ctrl2._accumulated_earnings_feed = 50.0
    ctrl2.hass.states.set("input_number.amort", "1000.0", {})
    asyncio.run(ctrl2._restore_from_helper())
    assert ctrl2.total_savings == pytest.approx(1000.0)


def test_options_save_keeps_helper_offset(make_ctrl, fixed_now):
    """Befund 1: _load_options() darf den Helper-Offset nicht überschreiben."""
    ctrl = make_ctrl(data={
        "amortisation_helper": "input_number.amort",
        "restore_from_helper": True,
    })
    _install(ctrl, 10, fixed_now)
    ctrl.hass.states.set("input_number.amort", "1500", {})
    import asyncio
    asyncio.run(ctrl._restore_from_helper())
    offset = ctrl.savings_offset
    assert offset == pytest.approx(1500.0)

    ctrl.entry.options = {"price_low_threshold": 0.1}  # beliebige Options-Speicherung
    ctrl._load_options()
    assert ctrl.savings_offset == pytest.approx(offset)
    assert ctrl.total_savings == pytest.approx(1500.0)

    # restore_from_helper deaktiviert → konfigurierter Offset gilt wieder
    ctrl.entry.options = {"restore_from_helper": False}
    ctrl._load_options()
    assert ctrl.savings_offset == pytest.approx(0.0)


def test_restore_state_after_helper_restore_recomputes_offset(make_ctrl, fixed_now):
    """Läuft der Helper-Restore vor restore_state, bleibt der Helper die Wahrheit."""
    ctrl = make_ctrl(data={
        "amortisation_helper": "input_number.amort",
        "restore_from_helper": True,
        "yearly_cost": 100.0,
    })
    _install(ctrl, 365, fixed_now)
    ctrl.hass.states.set("input_number.amort", "800", {})
    import asyncio
    asyncio.run(ctrl._restore_from_helper())
    ctrl.restore_state({
        "total_self_consumption_kwh": 1000,
        "accumulated_savings_self": 300.0,
        "accumulated_earnings_feed": 100.0,
    })
    assert ctrl.total_savings == pytest.approx(800.0)


def test_helper_sync_clamped_to_range(make_ctrl):
    ctrl = make_ctrl(data={"amortisation_helper": "input_number.amort"})
    ctrl._restored = True
    ctrl._accumulated_savings_self = 20000.0
    ctrl.hass.states.set("input_number.amort", "9000", {"min": 0, "max": 10000})
    ctrl._sync_to_helper()
    assert ctrl.hass.services.calls[-1][2]["value"] == 10000


def test_stopped_controller_does_not_sync(make_ctrl):
    ctrl = make_ctrl(data={"amortisation_helper": "input_number.amort"})
    ctrl._restored = True
    ctrl._accumulated_savings_self = 50.0
    ctrl.hass.states.set("input_number.amort", "10", {})
    import asyncio
    asyncio.run(ctrl.async_stop())
    ctrl._notify_entities()
    ctrl._sync_to_helper()
    assert ctrl.hass.services.calls == []
