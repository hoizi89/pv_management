"""Solcast P50/P10-Gewichtung (Issue #18) inkl. Fallback auf P50."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from conftest import LOCAL_TZ


@pytest.fixture
def solcast(pvm):
    from pv_management import solcast

    return solcast


def test_blend_linear(solcast):
    assert solcast.blend(10.0, 6.0, 0.0) == pytest.approx(10.0)
    assert solcast.blend(10.0, 6.0, 1.0) == pytest.approx(6.0)
    assert solcast.blend(10.0, 6.0, 0.25) == pytest.approx(9.0)
    assert solcast.blend(10.0, 6.0, 0.5) == pytest.approx(8.0)


def test_blend_fallback_and_limits(solcast):
    assert solcast.blend(10.0, None, 1.0) == pytest.approx(10.0)  # kein P10 → P50
    assert solcast.blend(None, 5.0, 0.5) is None
    assert solcast.blend(10.0, 6.0, 7.0) == pytest.approx(6.0)     # auf 0..1 begrenzt
    assert solcast.blend(10.0, 6.0, -1.0) == pytest.approx(10.0)
    assert solcast.blend(10.0, 6.0, None) == pytest.approx(10.0)


def test_row_estimate(solcast):
    row = {"pv_estimate": 4.0, "pv_estimate10": 2.0, "pv_estimate90": 5.0}
    assert solcast.row_estimate(row, 0.5) == pytest.approx(3.0)
    assert solcast.row_estimate({"pv_estimate": 4.0}, 1.0) == pytest.approx(4.0)


def test_day_total_from_attributes(solcast):
    attrs = {"estimate": 20.0, "estimate10": 12.0, "estimate90": 24.0}
    assert solcast.day_total(20.0, attrs, 0.0) == pytest.approx(20.0)
    assert solcast.day_total(20.0, attrs, 1.0) == pytest.approx(12.0)
    assert solcast.day_total(20.0, attrs, 0.5) == pytest.approx(16.0)
    # State (hier absichtlich P10 konfiguriert) wird nicht als P50 missverstanden
    assert solcast.day_total(12.0, attrs, 0.0) == pytest.approx(20.0)


def test_day_total_from_rows_ratio(solcast):
    rows = [
        {"period_start": "2026-09-30T10:00:00+02:00", "pv_estimate": 3.0, "pv_estimate10": 1.5},
        {"period_start": "2026-09-30T11:00:00+02:00", "pv_estimate": 5.0, "pv_estimate10": 2.5},
    ]
    assert solcast.day_total(16.0, {"detailedHourly": rows}, 1.0) == pytest.approx(8.0)


def test_day_total_without_p10_falls_back(solcast):
    rows = [{"period_start": "2026-09-30T10:00:00+02:00", "pv_estimate": 3.0}]
    assert solcast.day_total(16.0, {"detailedHourly": rows}, 1.0) == pytest.approx(16.0)
    assert solcast.day_total(16.0, {}, 0.7) == pytest.approx(16.0)
    assert solcast.day_estimates(16.0, {})[1] is None


def test_hours_of_day_weighted(solcast):
    rows = [
        {"period_start": "2026-09-30T10:00:00+02:00", "pv_estimate": 4.0, "pv_estimate10": 2.0},
        {"period_start": "2026-09-30T11:00:00+02:00", "pv_estimate": 6.0},  # ohne P10
    ]
    hours = solcast.hours_of_day(rows, date(2026, 9, 30), lambda d: d.astimezone(LOCAL_TZ), weight=0.5)
    assert hours[10] == pytest.approx(3.0)
    assert hours[11] == pytest.approx(6.0)
    plain = solcast.hours_of_day(rows, date(2026, 9, 30), lambda d: d.astimezone(LOCAL_TZ))
    assert plain[10] == pytest.approx(4.0)


def test_controller_applies_weight(make_ctrl, fixed_now):
    ctrl = make_ctrl(options={
        "solcast_forecast_entity": "sensor.solcast_today",
        "solcast_p10_weight": 1.0,
        "auto_charge_pv_threshold": 10.0,
    })

    class S:
        state = "14.0"
        attributes = {"estimate": 14.0, "estimate10": 8.0}

    ctrl._solcast_forecast_today = 14.0
    ctrl._load_solcast_forecast(S())
    assert ctrl.solcast_forecast_today == pytest.approx(8.0)
    assert ctrl.solcast_forecast_today_p50 == pytest.approx(14.0)
    assert ctrl.solcast_forecast_today_p10 == pytest.approx(8.0)
    assert ctrl._check_pv_condition() is True       # 8 < 10 → wenig PV erwartet

    ctrl.entry.options = dict(ctrl.entry.options, solcast_p10_weight=0.0)
    ctrl._load_options()
    assert ctrl.solcast_forecast_today == pytest.approx(14.0)  # Default = bisheriges Verhalten
    assert ctrl._check_pv_condition() is False


def test_controller_next_pv_peak_weighted(make_ctrl, fixed_now):
    fixed_now(datetime(2026, 9, 30, 8, 0, tzinfo=LOCAL_TZ))
    ctrl = make_ctrl(options={"solcast_forecast_entity": "sensor.s", "solcast_p10_weight": 1.0})
    ctrl._solcast_hourly_forecast = [
        {"period_start": "2026-09-30T11:00:00+02:00", "pv_estimate": 6.0, "pv_estimate10": 1.5},
        {"period_start": "2026-09-30T12:00:00+02:00", "pv_estimate": 5.0, "pv_estimate10": 4.0},
    ]
    peak = ctrl.next_pv_peak
    assert peak["hour"] == 12 and peak["power_kw"] == pytest.approx(4.0)
