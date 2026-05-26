from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later

from .const import (
    DOMAIN, DATA_CTRL, CONF_NAME,
    SURPLUS_RATIOS, SURPLUS_HYSTERESIS_RATIO,
    SURPLUS_ON_DELAY, SURPLUS_OFF_DELAY,
)

_LOGGER = logging.getLogger(__name__)


def get_battery_device_info(name: str) -> DeviceInfo:
    """DeviceInfo für das Batterie-Gerät."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{name}_battery")},
        name=f"{name} Batterie",
        manufacturer="Custom",
        model="PV Management - Batterie",
        via_device=(DOMAIN, name),
    )


def get_pv_surplus_device_info(name: str) -> DeviceInfo:
    """DeviceInfo für das PV-Überschuss-Gerät."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{name}_pv_surplus")},
        name=f"{name} PV-Überschuss",
        manufacturer="Custom",
        model="PV Management - PV-Überschuss",
        via_device=(DOMAIN, name),
    )


LEVEL_LABELS = {"low": "Low", "medium": "Medium", "high": "High"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Binary Sensoren."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Management")

    entities = [
        AutoChargeBinarySensor(ctrl, name),
        DischargeBinarySensor(ctrl, name),
        PVSurplusBinarySensor(ctrl, name, "low"),
        PVSurplusBinarySensor(ctrl, name, "medium"),
        PVSurplusBinarySensor(ctrl, name, "high"),
    ]

    async_add_entities(entities)


class AutoChargeBinarySensor(BinarySensorEntity):
    """
    Binary Sensor der anzeigt ob jetzt geladen werden sollte.

    Kann in Automatisierungen verwendet werden um die Batterie zu steuern:

    automation:
      trigger:
        - platform: state
          entity_id: binary_sensor.pv_management_auto_charge_empfehlung
          to: "on"
      action:
        - service: your_inverter.start_charging
    """

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._attr_name = f"{name} Auto-Charge Empfehlung"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_auto_charge_recommendation"
        self._attr_device_info = get_battery_device_info(name)
        self._removed = False

    async def async_added_to_hass(self):
        self._removed = False
        self.ctrl.register_entity_listener(self._on_ctrl_update)

    async def async_will_remove_from_hass(self):
        self._removed = True
        self.ctrl.unregister_entity_listener(self._on_ctrl_update)

    @callback
    def _on_ctrl_update(self):
        if not self._removed and self.hass:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """True wenn jetzt geladen werden sollte."""
        return self.ctrl.should_auto_charge

    @property
    def icon(self) -> str:
        """Icon basierend auf Status."""
        if self.is_on:
            return "mdi:battery-charging-high"
        elif not self.ctrl.auto_charge_enabled:
            return "mdi:battery-off"
        else:
            return "mdi:battery-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Detaillierte Infos für Debugging und Dashboards."""
        forecast = self.ctrl.solcast_forecast_today if self.ctrl.has_solcast_integration else self.ctrl.pv_forecast
        price_diff = self.ctrl.epex_price_diff_today

        # Berechne geschätzte Ladekosten und potentielle Ersparnis
        charge_cost_estimate = None
        potential_savings = None
        if self.ctrl.should_auto_charge and price_diff:
            # Geschätzte Ladekosten für 1 Stunde
            charge_kwh = self.ctrl.auto_charge_power / 1000
            charge_cost_estimate = charge_kwh * self.ctrl.current_electricity_price
            # Potentielle Ersparnis (mit 85% Effizienz)
            potential_savings = charge_kwh * (price_diff / 100) * 0.85

        return {
            # === STATUS ===
            "auto_charge_aktiviert": self.ctrl.auto_charge_enabled,
            "ladevorgang_aktiv": self.ctrl._is_auto_charging,  # Hysterese-Status
            "sollte_laden": self.ctrl.should_auto_charge,
            "grund": self.ctrl.auto_charge_reason,

            # === WINTER-ONLY ===
            "nur_winter_aktiv": self.ctrl.auto_charge_winter_only,
            "ist_winter": self.ctrl.is_winter,
            "winter_monate": "Oktober bis März",

            # === AKTUELLE WERTE ===
            "aktuelle_pv_prognose_kwh": round(forecast, 1),
            "aktueller_preis_quantile": round(self.ctrl.epex_quantile, 2) if self.ctrl.has_epex_integration else None,
            "aktueller_preis_ct": round(self.ctrl.current_electricity_price * 100, 1),
            "aktueller_batterie_soc": round(self.ctrl.battery_soc, 0) if self.ctrl.battery_soc_entity else None,
            "preisdifferenz_heute_ct": price_diff,

            # === SCHWELLWERTE (zum Vergleich) ===
            "schwelle_pv_prognose_kwh": self.ctrl.auto_charge_pv_threshold,
            "schwelle_preis_quantile": self.ctrl.auto_charge_price_quantile,
            "schwelle_min_soc": self.ctrl.auto_charge_min_soc,
            "schwelle_ziel_soc": self.ctrl.auto_charge_target_soc,
            "schwelle_min_preisdifferenz_ct": self.ctrl.auto_charge_min_price_diff,

            # === BEDINGUNGEN (✓/✗) ===
            "bedingung_winter_erfuellt": not self.ctrl.auto_charge_winter_only or self.ctrl.is_winter,
            "bedingung_pv_erfuellt": self.ctrl._check_pv_condition(),
            "bedingung_preis_erfuellt": self.ctrl._check_price_condition(),
            "bedingung_soc_erfuellt": self.ctrl._check_soc_condition(),
            "bedingung_preisdiff_erfuellt": self.ctrl._check_price_diff_condition(),

            # === KOSTENRECHNUNG ===
            "ladeleistung_w": self.ctrl.auto_charge_power,
            "geschaetzte_ladekosten_1h_eur": round(charge_cost_estimate, 2) if charge_cost_estimate else None,
            "potentielle_ersparnis_1h_eur": round(potential_savings, 2) if potential_savings else None,

            # === INTEGRATION STATUS ===
            "epex_integration": self.ctrl.has_epex_integration,
            "solcast_integration": self.ctrl.has_solcast_integration,
            "batterie_sensor_konfiguriert": bool(self.ctrl.battery_soc_entity),

            # === STATISTIKEN ===
            **self.ctrl.auto_charge_stats,
        }


class DischargeBinarySensor(BinarySensorEntity):
    """
    Binary Sensor der anzeigt ob die Batterie jetzt entladen werden sollte.

    Zeigt an ob der Strom teuer genug ist, um die Batterie zu entladen.
    Wenn ON: Batterie kann bis discharge_allow_soc entladen werden (z.B. 20%)
    Wenn OFF: Batterie wird auf discharge_hold_soc gehalten (z.B. 80%)

    automation:
      trigger:
        - platform: state
          entity_id: binary_sensor.pv_management_entladung_empfehlung
      action:
        - service: number.set_value
          target:
            entity_id: number.goodwe_entladungstiefe_netzbetrieb
          data:
            value: "{{ 20 if trigger.to_state.state == 'on' else 80 }}"
    """

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._attr_name = f"{name} Entladung Empfehlung"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_discharge_recommendation"
        self._attr_device_info = get_battery_device_info(name)
        self._removed = False

    async def async_added_to_hass(self):
        self._removed = False
        self.ctrl.register_entity_listener(self._on_ctrl_update)

    async def async_will_remove_from_hass(self):
        self._removed = True
        self.ctrl.unregister_entity_listener(self._on_ctrl_update)

    @callback
    def _on_ctrl_update(self):
        if not self._removed and self.hass:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """True wenn jetzt entladen werden sollte (teurer Strom)."""
        return self.ctrl.should_discharge

    @property
    def icon(self) -> str:
        """Icon basierend auf Status."""
        if self.is_on:
            return "mdi:battery-arrow-down"  # Entladen erlaubt
        elif not self.ctrl.discharge_enabled:
            return "mdi:battery-off-outline"
        else:
            return "mdi:battery-lock"  # Batterie wird gehalten

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Detaillierte Infos für Debugging und Dashboards."""
        target_soc = self.ctrl.discharge_target_soc
        return {
            # === STATUS ===
            "entlade_steuerung_aktiviert": self.ctrl.discharge_enabled,
            "sollte_entladen": self.ctrl.should_discharge,
            "grund": self.ctrl.discharge_reason,
            "ziel_entladungstiefe": target_soc,  # None wenn deaktiviert

            # === WINTER/SOMMER ===
            "nur_winter_aktiv": self.ctrl.discharge_winter_only,
            "ist_winter": self.ctrl.is_winter,
            "sommer_modus": self.ctrl.discharge_is_summer_mode,
            "winter_monate": "Oktober bis März",

            # === AKTUELLE WERTE ===
            "aktueller_preis_quantile": round(self.ctrl.epex_quantile, 2) if self.ctrl.has_epex_integration else None,
            "aktueller_preis_ct": round(self.ctrl.current_electricity_price * 100, 1),
            "aktueller_batterie_soc": round(self.ctrl.battery_soc, 0) if self.ctrl.battery_soc_entity else None,

            # === SCHWELLWERTE ===
            "schwelle_preis_quantile": self.ctrl.discharge_price_quantile,
            "halten_soc": self.ctrl.discharge_hold_soc,
            "entladen_bis_soc": self.ctrl.discharge_allow_soc,
            "sommer_soc": self.ctrl.discharge_summer_soc,

            # === INTEGRATION STATUS ===
            "epex_integration": self.ctrl.has_epex_integration,
        }


class PVSurplusBinarySensor(BinarySensorEntity):
    """Binary Sensor für PV-Überschuss-Stufen (low/medium/high).

    Auto-derived Schwelle = SURPLUS_RATIOS[level] * pv_peak_power.
    Hysterese: ON bei surplus >= threshold, OFF bei surplus < threshold * (1 - HYSTERESIS_RATIO).
    Anti-Flacker: ON erst nach SURPLUS_ON_DELAY s stabilem Überschuss, OFF erst nach SURPLUS_OFF_DELAY s.

    Für PV-aware Verbraucher (WP-Kühlung, Waschmaschine, Geschirrspüler, EV).
    """

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, ctrl, name: str, level: str):
        self.ctrl = ctrl
        self._level = level
        self._ratio = SURPLUS_RATIOS[level]
        label = LEVEL_LABELS[level]
        self._attr_name = f"{name} PV-Überschuss {label}"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_pv_surplus_{level}"
        self._attr_device_info = get_pv_surplus_device_info(name)
        self._removed = False
        # State machine
        self._committed_state: bool = False
        self._pending_target: bool | None = None
        self._pending_cancel = None

    async def async_added_to_hass(self):
        self._removed = False
        self.ctrl.register_entity_listener(self._on_ctrl_update)
        # Initial state ohne Delay (beim Start direkt commit)
        self._committed_state = self._compute_desired_state()

    async def async_will_remove_from_hass(self):
        self._removed = True
        self.ctrl.unregister_entity_listener(self._on_ctrl_update)
        self._cancel_pending()

    @callback
    def _on_ctrl_update(self):
        if self._removed or not self.hass:
            return
        self._evaluate()

    def _cancel_pending(self):
        if self._pending_cancel:
            self._pending_cancel()
        self._pending_cancel = None
        self._pending_target = None

    def _compute_desired_state(self) -> bool:
        """Raw desired state mit Hysterese."""
        if not self.ctrl.house_power_entity:
            return False  # Ohne Hausstrom-Sensor keine Überschussberechnung
        if self.ctrl.pv_peak_power <= 0:
            return False  # Schutz vor Division/Schwelle 0
        surplus = self.ctrl.current_pv_surplus_w
        threshold_on = self.ctrl.pv_peak_power * self._ratio
        threshold_off = threshold_on * (1.0 - SURPLUS_HYSTERESIS_RATIO)
        if self._committed_state:
            return surplus >= threshold_off
        return surplus >= threshold_on

    def _evaluate(self):
        desired = self._compute_desired_state()
        if desired == self._committed_state:
            # Stabilisiert — etwaige Transition abbrechen
            self._cancel_pending()
            return
        if self._pending_target == desired:
            # Schon geplant, weiter laufen lassen
            return
        # Richtung gewechselt oder neu: alte Transition abbrechen, neue starten
        self._cancel_pending()
        delay = SURPLUS_ON_DELAY if desired else SURPLUS_OFF_DELAY
        self._pending_target = desired
        self._pending_cancel = async_call_later(self.hass, delay, self._commit_pending)

    @callback
    def _commit_pending(self, _now=None):
        self._pending_cancel = None
        if self._removed or self._pending_target is None:
            return
        # Re-check beim Commit: nur übernehmen wenn noch immer gewünscht
        if self._compute_desired_state() == self._pending_target:
            self._committed_state = self._pending_target
            if self.hass:
                self.async_write_ha_state()
        self._pending_target = None

    @property
    def is_on(self) -> bool:
        return self._committed_state

    @property
    def icon(self) -> str:
        if self.is_on:
            return "mdi:solar-power-variant"
        return "mdi:solar-power-variant-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        threshold_on = self.ctrl.pv_peak_power * self._ratio
        threshold_off = threshold_on * (1.0 - SURPLUS_HYSTERESIS_RATIO)
        pending = (
            "ein" if self._pending_target is True
            else "aus" if self._pending_target is False
            else None
        )
        return {
            "stufe": self._level,
            "aktueller_ueberschuss_w": round(self.ctrl.current_pv_surplus_w, 0),
            "pv_leistung_w": round(self.ctrl.pv_power, 0),
            "hausverbrauch_w": round(self.ctrl.house_power, 0),
            "shiftable_load_w": round(self.ctrl.shiftable_load_power, 0),
            "effektiver_hausverbrauch_w": round(self.ctrl.effective_house_power, 0),
            "schwelle_ein_w": round(threshold_on, 0),
            "schwelle_aus_w": round(threshold_off, 0),
            "anteil_peak": SURPLUS_RATIOS[self._level],
            "pv_peak_w": round(self.ctrl.pv_peak_power, 0),
            "pv_peak_quelle": self.ctrl.pv_peak_power_source,
            "on_delay_s": SURPLUS_ON_DELAY,
            "off_delay_s": SURPLUS_OFF_DELAY,
            "hauspower_sensor_konfiguriert": bool(self.ctrl.house_power_entity),
            "shiftable_load_konfiguriert": bool(self.ctrl.shiftable_load_entity),
            "uebergang_ausstehend": pending,
        }
