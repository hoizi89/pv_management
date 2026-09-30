"""Persistenz: Zählerstände über Neustart, Monatsbericht."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from conftest import LOCAL_TZ


def _running(ctrl, pv=1000.0, export=400.0, imp=2000.0):
    ctrl._pv_production_kwh = pv
    ctrl._grid_export_kwh = export
    ctrl._grid_import_kwh = imp
    ctrl._restored = True
    ctrl._process_energy_update()
    ctrl._process_energy_update()


def _saved_state(ctrl):
    data = {
        "total_self_consumption_kwh": ctrl._total_self_consumption_kwh,
        "total_feed_in_kwh": ctrl._total_feed_in_kwh,
        "accumulated_savings_self": ctrl._accumulated_savings_self,
        "accumulated_earnings_feed": ctrl._accumulated_earnings_feed,
    }
    data.update(ctrl.get_persist_extra())
    return data


def test_downtime_energy_is_booked_after_restart(make_ctrl, fixed_now):
    t0 = fixed_now(datetime(2026, 7, 1, 8, 0, tzinfo=LOCAL_TZ))
    ctrl = make_ctrl(data={"electricity_price": 0.30})
    _running(ctrl)
    saved = _saved_state(ctrl)

    # 10 h HA-Downtime, in der 80 kWh selbst verbraucht wurden (> alte 50-kWh-Grenze)
    fixed_now(t0 + timedelta(hours=10))
    ctrl2 = make_ctrl(data={"electricity_price": 0.30})
    ctrl2.restore_state(saved)
    assert ctrl2._last_pv_production_kwh == pytest.approx(1000.0)
    assert ctrl2._baseline_pv_production_kwh == pytest.approx(1000.0)
    ctrl2._pv_production_kwh = 1080.0
    ctrl2._grid_export_kwh = 400.0
    ctrl2._grid_import_kwh = 2000.0
    ctrl2._process_energy_update()
    assert ctrl2.self_consumption_kwh == pytest.approx(80.0)
    assert ctrl2.savings_self_consumption == pytest.approx(80 * 0.30)

    # Danach gilt wieder die normale Grenze
    ctrl2._pv_production_kwh += 500.0
    ctrl2._process_energy_update()
    assert ctrl2.self_consumption_kwh == pytest.approx(80.0)  # re-baselined, verworfen


def test_changed_sensor_discards_counters(make_ctrl, fixed_now):
    fixed_now(datetime(2026, 7, 1, 8, 0, tzinfo=LOCAL_TZ))
    ctrl = make_ctrl()
    _running(ctrl)
    saved = _saved_state(ctrl)
    ctrl2 = make_ctrl(data={"pv_production_entity": "sensor.new_pv"})
    ctrl2.restore_state(saved)
    assert ctrl2._last_pv_production_kwh is None
    assert ctrl2._baseline_pv_production_kwh is None


def test_legacy_restore_without_counters(make_ctrl):
    """Alte gespeicherte Daten (< 4.6.0) laden weiterhin."""
    ctrl = make_ctrl()
    ctrl.restore_state({
        "total_self_consumption_kwh": 123.0,
        "accumulated_savings_self": 45.6,
        "monthly_reset_month": 9, "monthly_reset_year": 2026,
    })
    assert ctrl.self_consumption_kwh == pytest.approx(123.0)
    assert ctrl._last_pv_production_kwh is None


def test_monthly_report_uses_closed_month(make_ctrl, fixed_now):
    fixed_now(datetime(2026, 9, 30, 20, 0, tzinfo=LOCAL_TZ))
    ctrl = make_ctrl()
    ctrl._roll_periods()
    ctrl._monthly_grid_import_kwh = 210.0
    ctrl._monthly_grid_import_cost = 52.5

    # 1. Oktober: erster Import des Monats kommt VOR dem Bericht
    fixed_now(datetime(2026, 10, 1, 0, 0, 5, tzinfo=LOCAL_TZ))
    ctrl._roll_periods()
    ctrl._monthly_grid_import_kwh += 0.4
    ctrl._check_monthly_summary()

    reports = [d for t, d in ctrl.hass.bus.events if d.get("type") == "monthly_summary"]
    assert len(reports) == 1
    assert reports[0]["grid_import_kwh"] == pytest.approx(210.0)
    assert reports[0]["month"] == "September 2026"

    ctrl._check_monthly_summary()
    assert len([d for t, d in ctrl.hass.bus.events if d.get("type") == "monthly_summary"]) == 1


def test_monthly_report_after_restart_on_first(make_ctrl, fixed_now):
    """Neustart am 1.: Vormonatswerte aus dem Restore, kein doppelter Bericht."""
    fixed_now(datetime(2026, 10, 1, 7, 0, tzinfo=LOCAL_TZ))
    saved = {
        "monthly_grid_import_kwh": 180.0,
        "monthly_grid_import_cost": 40.0,
        "monthly_reset_month": 9,
        "monthly_reset_year": 2026,
    }
    ctrl = make_ctrl()
    ctrl.restore_state(saved)
    assert ctrl.monthly_grid_import_kwh == 0.0
    ctrl._check_monthly_summary()
    reports = [d for t, d in ctrl.hass.bus.events if d.get("type") == "monthly_summary"]
    assert len(reports) == 1 and reports[0]["grid_import_kwh"] == pytest.approx(180.0)

    # Zweiter Neustart am selben Tag: gesendeter Monat ist persistiert
    saved2 = dict(saved)
    saved2["monthly_summary_sent"] = ctrl.get_persist_extra()["monthly_summary_sent"]
    ctrl2 = make_ctrl()
    ctrl2.restore_state(saved2)
    ctrl2._check_monthly_summary()
    assert not [d for t, d in ctrl2.hass.bus.events if d.get("type") == "monthly_summary"]


def test_restored_same_month_keeps_tracking_period(make_ctrl, fixed_now):
    fixed_now(datetime(2026, 9, 15, 7, 0, tzinfo=LOCAL_TZ))
    ctrl = make_ctrl()
    ctrl.restore_state({
        "monthly_grid_import_kwh": 90.0,
        "monthly_reset_month": 9,
        "monthly_reset_year": 2026,
    })
    ctrl._roll_periods()  # darf die Werte nicht nullen
    assert ctrl.monthly_grid_import_kwh == pytest.approx(90.0)
    assert ctrl.monthly_tracking_period == (2026, 9)
