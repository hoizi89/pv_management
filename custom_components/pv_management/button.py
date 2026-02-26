from __future__ import annotations

import logging
import time

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, DATA_CTRL, CONF_NAME

_LOGGER = logging.getLogger(__name__)

CONFIRM_WINDOW_SECONDS = 5


def get_prices_device_info(name: str) -> DeviceInfo:
    """DeviceInfo für das Strompreise-Gerät."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{name}_prices")},
        name=f"{name} Strompreise",
        manufacturer="Custom",
        model="PV Management - Strompreise",
        via_device=(DOMAIN, name),
    )


def get_benchmark_device_info(name: str) -> DeviceInfo:
    """DeviceInfo für das Benchmark-Gerät."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{name}_benchmark")},
        name=f"{name} Benchmark",
        manufacturer="Custom",
        model="PV Management - Benchmark",
        via_device=(DOMAIN, name),
    )


def get_pv_strings_device_info(name: str) -> DeviceInfo:
    """DeviceInfo für das PV-Strings-Gerät."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{name}_pv_strings")},
        name=f"{name} PV-Strings",
        manufacturer="Custom",
        model="PV Management - PV-Strings",
        via_device=(DOMAIN, name),
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Buttons."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Management")
    entities = [
        ResetButton(ctrl, name),
        ResetGridImportButton(ctrl, name),
    ]
    if ctrl.benchmark_enabled:
        entities.append(ResetBenchmarkButton(ctrl, name))
    if ctrl.pv_strings:
        entities.append(ResetPVStringsButton(ctrl, name))
    async_add_entities(entities)


class BaseButton(ButtonEntity):
    """Basis-Klasse für Buttons."""

    _attr_should_poll = False

    def __init__(self, ctrl, name: str, key: str, icon: str | None = None):
        self.ctrl = ctrl
        self._attr_name = f"{name} {key}"
        self._attr_unique_id = f"{DOMAIN}_{name}_{key}".lower().replace(" ", "_")
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            manufacturer="Custom",
            model="PV Management",
        )


class ConfirmResetButton(ButtonEntity):
    """Button mit Doppelklick-Bestätigung für destruktive Aktionen.

    Erster Klick: Warnung als Persistent Notification (5s Fenster).
    Zweiter Klick innerhalb 5s: Reset wird ausgeführt.
    """

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._base_name = name
        self._first_press_time: float = 0.0

    async def async_press(self) -> None:
        now = time.monotonic()
        elapsed = now - self._first_press_time

        if elapsed <= CONFIRM_WINDOW_SECONDS:
            # Zweiter Klick — Reset ausführen
            self._first_press_time = 0.0
            self.hass.components.persistent_notification.async_dismiss(
                notification_id=f"{self._attr_unique_id}_confirm"
            )
            _LOGGER.info("Reset bestätigt: %s", self._attr_name)
            await self._execute_reset()
            self.hass.components.persistent_notification.async_create(
                message=f"**{self._attr_name}** wurde zurückgesetzt.",
                title="Reset durchgeführt",
                notification_id=f"{self._attr_unique_id}_done",
            )
        else:
            # Erster Klick — Warnung anzeigen
            self._first_press_time = now
            self.hass.components.persistent_notification.async_create(
                message=f"**{self._attr_name}**: Innerhalb von {CONFIRM_WINDOW_SECONDS} Sekunden erneut drücken um zurückzusetzen. Alle Daten gehen verloren!",
                title="Zurücksetzen bestätigen",
                notification_id=f"{self._attr_unique_id}_confirm",
            )
            _LOGGER.warning("Reset angefordert: %s — erneut drücken zum Bestätigen", self._attr_name)

    async def _execute_reset(self) -> None:
        raise NotImplementedError


class ResetButton(BaseButton):
    """Button zum Neu-Initialisieren aus Sensor-Daten."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Neu initialisieren", icon="mdi:restart")
        self._first_press_time: float = 0.0

    async def async_press(self) -> None:
        now = time.monotonic()
        elapsed = now - self._first_press_time

        if elapsed <= CONFIRM_WINDOW_SECONDS:
            self._first_press_time = 0.0
            self.hass.components.persistent_notification.async_dismiss(
                notification_id=f"{self._attr_unique_id}_confirm"
            )
            _LOGGER.info("Reset-Button bestätigt: Initialisiere neu aus Sensor-Daten")
            self.ctrl._total_self_consumption_kwh = 0.0
            self.ctrl._total_feed_in_kwh = 0.0
            self.ctrl._accumulated_savings_self = 0.0
            self.ctrl._accumulated_earnings_feed = 0.0
            self.ctrl._first_seen_date = None
            self.ctrl._initialize_from_sensors()
            self.ctrl._last_pv_production_kwh = self.ctrl._pv_production_kwh
            self.ctrl._last_grid_export_kwh = self.ctrl._grid_export_kwh
            self.ctrl._notify_entities()
            self.hass.components.persistent_notification.async_create(
                message="Amortisation wurde neu initialisiert.",
                title="Reset durchgeführt",
                notification_id=f"{self._attr_unique_id}_done",
            )
        else:
            self._first_press_time = now
            self.hass.components.persistent_notification.async_create(
                message=f"**Neu initialisieren**: Innerhalb von {CONFIRM_WINDOW_SECONDS} Sekunden erneut drücken. Alle Amortisationsdaten werden zurückgesetzt!",
                title="Zurücksetzen bestätigen",
                notification_id=f"{self._attr_unique_id}_confirm",
            )
            _LOGGER.warning("Neu-Initialisierung angefordert — erneut drücken zum Bestätigen")


class ResetGridImportButton(ConfirmResetButton):
    """Button zum Zurücksetzen aller Strompreis-Tracking-Werte."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name)
        self._attr_name = f"{name} Strompreis-Tracking zurücksetzen"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_reset_grid_import_button"
        self._attr_icon = "mdi:cash-remove"
        self._attr_device_info = get_prices_device_info(name)

    async def _execute_reset(self) -> None:
        _LOGGER.info(
            "Strompreis-Reset bestätigt: Setze alle Werte zurück (war: %.2f kWh, %.2f €)",
            self.ctrl._tracked_grid_import_kwh,
            self.ctrl._total_grid_import_cost,
        )
        self.ctrl.reset_grid_import_tracking()


class ResetBenchmarkButton(ConfirmResetButton):
    """Button zum Zurücksetzen der Benchmark/WP-Tracking-Daten."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name)
        self._attr_name = f"{name} Benchmark zurücksetzen"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_reset_benchmark_button"
        self._attr_icon = "mdi:chart-line-stacked"
        self._attr_device_info = get_benchmark_device_info(name)

    async def _execute_reset(self) -> None:
        _LOGGER.info("Benchmark-Reset bestätigt: WP-Tracking und Benchmark-Daten zurückgesetzt")
        self.ctrl.reset_benchmark_tracking()


class ResetPVStringsButton(ConfirmResetButton):
    """Button zum Zurücksetzen der PV-String-Tracking-Daten und Peaks."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name)
        self._attr_name = f"{name} PV-Strings zurücksetzen"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_reset_pv_strings_button"
        self._attr_icon = "mdi:solar-panel"
        self._attr_device_info = get_pv_strings_device_info(name)

    async def _execute_reset(self) -> None:
        _LOGGER.info("PV-Strings-Reset bestätigt: Tracking und Peaks zurückgesetzt")
        self.ctrl.reset_pv_strings_tracking()
