"""Test-Setup ohne laufendes Home Assistant.

Ist ``homeassistant`` nicht installiert, werden schlanke Stubs der wenigen
benutzten Module registriert. Damit lassen sich der Controller und die reinen
Rechenmodule (calc.py, solcast.py) direkt importieren und testen.
"""

from __future__ import annotations

import enum
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

try:
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("Europe/Vienna")
except Exception:  # pragma: no cover - Fallback ohne tzdata
    LOCAL_TZ = timezone(timedelta(hours=1))


def _install_ha_stubs() -> None:
    def module(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    ha = module("homeassistant")
    ha.__path__ = []

    const = module("homeassistant.const")
    const.STATE_UNAVAILABLE = "unavailable"
    const.STATE_UNKNOWN = "unknown"
    const.EVENT_STATE_CHANGED = "state_changed"
    const.MATCH_ALL = "*"

    class Platform(str, enum.Enum):
        SENSOR = "sensor"
        BUTTON = "button"
        SWITCH = "switch"
        BINARY_SENSOR = "binary_sensor"

    const.Platform = Platform

    core = module("homeassistant.core")
    core.HomeAssistant = object
    core.Event = object
    core.callback = lambda func: func

    config_entries = module("homeassistant.config_entries")
    config_entries.ConfigEntry = object

    util = module("homeassistant.util")
    util.__path__ = []
    dt = module("homeassistant.util.dt")

    def now():
        return datetime.now(LOCAL_TZ)

    def utcnow():
        return datetime.now(timezone.utc)

    def as_local(value: datetime) -> datetime:
        return value.astimezone(LOCAL_TZ)

    def parse_datetime(value: str):
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    dt.now = now
    dt.utcnow = utcnow
    dt.as_local = as_local
    dt.parse_datetime = parse_datetime
    util.dt = dt

    helpers = module("homeassistant.helpers")
    helpers.__path__ = []
    event = module("homeassistant.helpers.event")

    def _cancel_factory(*_args, **_kwargs):
        return lambda: None

    event.async_call_later = _cancel_factory
    event.async_track_time_change = _cancel_factory
    event.async_track_time_interval = _cancel_factory
    event.async_track_state_change_event = _cancel_factory
    helpers.event = event


try:  # echtes HA verwenden, falls installiert
    import homeassistant.util.dt  # noqa: F401
    import homeassistant.helpers.event  # noqa: F401
except ImportError:
    _install_ha_stubs()


# --------------------------------------------------------------------------- Fakes


class FakeState:
    def __init__(self, state, attributes=None):
        self.state = str(state)
        self.attributes = attributes or {}


class FakeStates:
    def __init__(self):
        self._states: dict[str, FakeState] = {}

    def get(self, entity_id):
        return self._states.get(entity_id)

    def set(self, entity_id, state, attributes=None):
        self._states[entity_id] = FakeState(state, attributes)


class FakeBus:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type, data):
        self.events.append((event_type, data))


class FakeServices:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    async def async_call(self, domain, service, data):
        self.calls.append((domain, service, data))


class FakeHass:
    def __init__(self):
        self.states = FakeStates()
        self.bus = FakeBus()
        self.services = FakeServices()

    def async_create_task(self, coro):
        # Coroutine synchron "ausführen" (async_call hat kein await)
        try:
            coro.send(None)
        except StopIteration:
            pass


class FakeEntry:
    def __init__(self, data=None, options=None):
        self.data = data or {}
        self.options = options or {}
        self.entry_id = "test"


@pytest.fixture
def pvm():
    import pv_management

    return pv_management


@pytest.fixture
def make_ctrl(pvm):
    """Erzeugt einen Controller mit Fake-HA; Optionen per kwargs."""

    def _make(options=None, data=None, states=None):
        hass = FakeHass()
        for entity_id, (state, attrs) in (states or {}).items():
            hass.states.set(entity_id, state, attrs)
        base = {
            "name": "Test",
            "pv_production_entity": "sensor.pv",
            "grid_export_entity": "sensor.export",
            "grid_import_entity": "sensor.import",
        }
        base.update(data or {})
        entry = FakeEntry(base, options or {})
        ctrl = pvm.PVManagementController(hass, entry)
        return ctrl

    return _make


@pytest.fixture
def fixed_now(pvm, monkeypatch):
    """Setzt die HA-Zeit (dt_util.now) auf einen festen Zeitpunkt."""

    def _set(value: datetime):
        monkeypatch.setattr(pvm.dt_util, "now", lambda: value)
        return value

    return _set
