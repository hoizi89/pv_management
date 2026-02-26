from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, DATA_CTRL, CONF_NAME

_LOGGER = logging.getLogger(__name__)


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


class ResetButton(BaseButton):
    """Button zum Neu-Initialisieren aus Sensor-Daten."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Neu initialisieren", icon="mdi:restart")

    async def async_press(self) -> None:
        """Initialisiert die Werte neu aus den aktuellen Sensor-Totals."""
        _LOGGER.info("Reset-Button gedrückt: Initialisiere neu aus Sensor-Daten")
        # Erst zurücksetzen
        self.ctrl._total_self_consumption_kwh = 0.0
        self.ctrl._total_feed_in_kwh = 0.0
        self.ctrl._accumulated_savings_self = 0.0
        self.ctrl._accumulated_earnings_feed = 0.0
        self.ctrl._first_seen_date = None
        # Dann aus Sensoren initialisieren
        self.ctrl._initialize_from_sensors()
        # Last-Werte setzen für korrektes Delta-Tracking
        self.ctrl._last_pv_production_kwh = self.ctrl._pv_production_kwh
        self.ctrl._last_grid_export_kwh = self.ctrl._grid_export_kwh
        self.ctrl._notify_entities()


class ResetGridImportButton(ButtonEntity):
    """
    Button zum Zurücksetzen aller Strompreis-Tracking-Werte.

    Setzt zurück:
    - Gesamte Netzbezug-Kosten (€)
    - Getrackte kWh für Durchschnittsberechnung
    - Tägliche Werte
    - Monatliche Werte
    """

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._attr_name = f"{name} Strompreis-Tracking zurücksetzen"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_reset_grid_import_button"
        self._attr_icon = "mdi:cash-remove"
        self._attr_device_info = get_prices_device_info(name)

    async def async_press(self) -> None:
        """Handle button press - setzt alle Strompreis-Werte zurück."""
        _LOGGER.info(
            "Strompreis-Reset-Button gedrückt: Setze alle Werte zurück (war: %.2f kWh, %.2f €)",
            self.ctrl._tracked_grid_import_kwh,
            self.ctrl._total_grid_import_cost
        )
        self.ctrl.reset_grid_import_tracking()


class ResetBenchmarkButton(ButtonEntity):
    """Button zum Zurücksetzen der Benchmark/WP-Tracking-Daten."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._attr_name = f"{name} Benchmark zurücksetzen"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_reset_benchmark_button"
        self._attr_icon = "mdi:chart-line-stacked"
        self._attr_device_info = get_benchmark_device_info(name)

    async def async_press(self) -> None:
        """Setzt Benchmark- und WP-Tracking zurück."""
        _LOGGER.info("Benchmark-Reset: WP-Tracking und Benchmark-Daten zurückgesetzt")
        self.ctrl.reset_benchmark_tracking()


class ResetPVStringsButton(ButtonEntity):
    """Button zum Zurücksetzen der PV-String-Tracking-Daten und Peaks."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._attr_name = f"{name} PV-Strings zurücksetzen"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_reset_pv_strings_button"
        self._attr_icon = "mdi:solar-panel"
        self._attr_device_info = get_pv_strings_device_info(name)

    async def async_press(self) -> None:
        """Setzt PV-String-Tracking und Peaks zurück."""
        _LOGGER.info("PV-Strings-Reset: Tracking und Peaks zurückgesetzt")
        self.ctrl.reset_pv_strings_tracking()
