from __future__ import annotations

import logging
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, DATA_CTRL, CONF_NAME,
    CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
    CONF_ELECTRICITY_PRICE_ENTITY, CONF_FEED_IN_TARIFF_ENTITY,
    CONF_BATTERY_SOC_ENTITY, CONF_PV_POWER_ENTITY, CONF_PV_FORECAST_ENTITY,
    RECOMMENDATION_GREEN, RECOMMENDATION_YELLOW, RECOMMENDATION_RED,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Sensoren."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Management")

    entities = [
        # === Haupt-Sensoren (Übersicht) ===
        AmortisationPercentSensor(ctrl, name),
        TotalSavingsSensor(ctrl, name),  # Dieser speichert persistent!
        RemainingCostSensor(ctrl, name),
        StatusSensor(ctrl, name),

        # === EMPFEHLUNG (AMPEL) ===
        ConsumptionRecommendationSensor(ctrl, name),

        # === Energie-Sensoren ===
        SelfConsumptionSensor(ctrl, name),
        FeedInSensor(ctrl, name),
        PVProductionSensor(ctrl, name),

        # === Finanz-Sensoren ===
        SavingsSelfConsumptionSensor(ctrl, name),
        EarningsFeedInSensor(ctrl, name),

        # === Effizienz-Sensoren ===
        SelfConsumptionRatioSensor(ctrl, name),
        AutarkyRateSensor(ctrl, name),

        # === Statistik-Sensoren ===
        AverageDailySavingsSensor(ctrl, name),
        AverageMonthlySavingsSensor(ctrl, name),
        AverageYearlySavingsSensor(ctrl, name),
        DaysSinceInstallationSensor(ctrl, name),

        # === Prognose-Sensoren ===
        EstimatedRemainingDaysSensor(ctrl, name),
        EstimatedPaybackDateSensor(ctrl, name),

        # === Umwelt-Sensoren ===
        CO2SavedSensor(ctrl, name),

        # === Konfigurations-Sensoren (Diagnose) ===
        CurrentElectricityPriceSensor(ctrl, name),
        CurrentFeedInTariffSensor(ctrl, name),
        InstallationCostSensor(ctrl, name),
        ConfigurationDiagnosticSensor(ctrl, name, entry),
    ]

    async_add_entities(entities)


class BaseEntity(SensorEntity):
    """Basis-Klasse für alle Sensoren."""

    _attr_should_poll = False

    def __init__(
        self,
        ctrl,
        name: str,
        key: str,
        unit=None,
        icon=None,
        state_class=None,
        device_class=None,
        entity_category=None,
    ):
        self.ctrl = ctrl
        self._attr_name = f"{name} {key}"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_{key.lower().replace(' ', '_')}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_state_class = state_class
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            manufacturer="Custom",
            model="PV Management",
        )
        self._removed = False

    async def async_added_to_hass(self):
        self._removed = False
        self.ctrl.register_entity_listener(self._on_ctrl_update)

    async def async_will_remove_from_hass(self):
        """Entfernt den Listener wenn die Entity entladen wird."""
        self._removed = True
        self.ctrl.unregister_entity_listener(self._on_ctrl_update)

    @callback
    def _on_ctrl_update(self):
        if not self._removed and self.hass:
            self.async_write_ha_state()


# =============================================================================
# HAUPT-SENSOREN
# =============================================================================


class AmortisationPercentSensor(BaseEntity):
    """Amortisation in Prozent - Hauptindikator."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amortisation",
            unit="%",
            icon="mdi:percent-circle",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.amortisation_percent, 2)

    @property
    def extra_state_attributes(self):
        return {
            "total_savings": f"{self.ctrl.total_savings:.2f}€",
            "installation_cost": f"{self.ctrl.installation_cost:.2f}€",
            "remaining": f"{self.ctrl.remaining_cost:.2f}€",
            "is_amortised": self.ctrl.is_amortised,
        }


class TotalSavingsSensor(BaseEntity, RestoreEntity):
    """
    Gesamtersparnis in Euro.

    WICHTIG: Dieser Sensor speichert die inkrementell berechneten Werte
    persistent, damit sie über Neustarts erhalten bleiben!
    """

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Gesamtersparnis",
            unit="€",
            icon="mdi:cash-plus",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
        )

    async def async_added_to_hass(self):
        """Wiederherstellen des gespeicherten Zustands."""
        await super().async_added_to_hass()

        # Versuche letzten Zustand zu laden
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            # Lade die extra_state_attributes für die vollständigen Daten
            attrs = last_state.attributes or {}

            restore_data = {
                "total_self_consumption_kwh": attrs.get("tracked_self_consumption_kwh", 0.0),
                "total_feed_in_kwh": attrs.get("tracked_feed_in_kwh", 0.0),
                "accumulated_savings_self": attrs.get("accumulated_savings_self", 0.0),
                "accumulated_earnings_feed": attrs.get("accumulated_earnings_feed", 0.0),
                "first_seen_date": attrs.get("first_seen_date"),
            }

            self.ctrl.restore_state(restore_data)
            _LOGGER.info("TotalSavingsSensor: Zustand wiederhergestellt")

    @property
    def native_value(self) -> float:
        return round(self.ctrl.total_savings, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """
        Speichert alle wichtigen Werte als Attribute.
        Diese werden von RestoreEntity wiederhergestellt.
        """
        return {
            "savings_self_consumption": f"{self.ctrl.savings_self_consumption:.2f}€",
            "earnings_feed_in": f"{self.ctrl.earnings_feed_in:.2f}€",
            # Inkrementell berechnete Werte (werden restored)
            "tracked_self_consumption_kwh": round(self.ctrl._total_self_consumption_kwh, 4),
            "tracked_feed_in_kwh": round(self.ctrl._total_feed_in_kwh, 4),
            "accumulated_savings_self": round(self.ctrl._accumulated_savings_self, 4),
            "accumulated_earnings_feed": round(self.ctrl._accumulated_earnings_feed, 4),
            "first_seen_date": self.ctrl._first_seen_date.isoformat() if self.ctrl._first_seen_date else None,
            # Info
            "calculation_method": "incremental (dynamic prices supported)",
        }


class RemainingCostSensor(BaseEntity):
    """Verbleibender Betrag bis Amortisation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Restbetrag",
            unit="€",
            icon="mdi:cash-minus",
            # state_class muss None sein für device_class=MONETARY (nicht MEASUREMENT)
            state_class=None,
            device_class=SensorDeviceClass.MONETARY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.remaining_cost, 2)

    @property
    def icon(self) -> str:
        if self.ctrl.is_amortised:
            return "mdi:cash-check"
        return "mdi:cash-minus"


class StatusSensor(BaseEntity):
    """Status-Text (z.B. '45.2% amortisiert' oder 'Amortisiert!')."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Status",
            icon="mdi:solar-power-variant",
        )

    @property
    def native_value(self) -> str:
        return self.ctrl.status_text

    @property
    def icon(self) -> str:
        if self.ctrl.is_amortised:
            return "mdi:party-popper"
        elif self.ctrl.amortisation_percent >= 75:
            return "mdi:trending-up"
        elif self.ctrl.amortisation_percent >= 50:
            return "mdi:solar-power-variant"
        else:
            return "mdi:solar-panel"

    @property
    def extra_state_attributes(self):
        attrs = {
            "percent": f"{self.ctrl.amortisation_percent:.1f}%",
            "total_savings": f"{self.ctrl.total_savings:.2f}€",
            "remaining": f"{self.ctrl.remaining_cost:.2f}€",
        }
        if self.ctrl.is_amortised:
            profit = self.ctrl.total_savings - self.ctrl.installation_cost
            attrs["profit"] = f"{profit:.2f}€"
        return attrs


# =============================================================================
# ENERGIE-SENSOREN
# =============================================================================


class SelfConsumptionSensor(BaseEntity):
    """Eigenverbrauch in kWh (inkrementell berechnet)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Eigenverbrauch",
            unit="kWh",
            icon="mdi:home-lightning-bolt",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.ENERGY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.self_consumption_kwh, 2)

class FeedInSensor(BaseEntity):
    """Netzeinspeisung in kWh (inkrementell berechnet)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Einspeisung",
            unit="kWh",
            icon="mdi:transmission-tower-export",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.ENERGY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.feed_in_kwh, 2)


class PVProductionSensor(BaseEntity):
    """PV-Produktion in kWh (gespiegelt vom Input-Sensor)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "PV Produktion",
            unit="kWh",
            icon="mdi:solar-power",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.ENERGY,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.pv_production_kwh, 2)


# =============================================================================
# FINANZ-SENSOREN
# =============================================================================


class SavingsSelfConsumptionSensor(BaseEntity):
    """Ersparnis durch Eigenverbrauch (inkrementell berechnet)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ersparnis Eigenverbrauch",
            unit="€",
            icon="mdi:piggy-bank",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.savings_self_consumption, 2)

    @property
    def extra_state_attributes(self):
        return {
            "self_consumption_kwh": f"{self.ctrl.self_consumption_kwh:.2f} kWh",
            "current_price": f"{self.ctrl.current_electricity_price:.4f} €/kWh",
            "accumulated_savings": f"{self.ctrl._accumulated_savings_self:.2f}€",
            "calculation": "incremental (each kWh × price at that time)",
        }


class EarningsFeedInSensor(BaseEntity):
    """Einnahmen durch Einspeisung (inkrementell berechnet)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Einnahmen Einspeisung",
            unit="€",
            icon="mdi:cash-plus",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.earnings_feed_in, 2)

    @property
    def extra_state_attributes(self):
        return {
            "feed_in_kwh": f"{self.ctrl.feed_in_kwh:.2f} kWh",
            "current_tariff": f"{self.ctrl.current_feed_in_tariff:.4f} €/kWh",
            "accumulated_earnings": f"{self.ctrl._accumulated_earnings_feed:.2f}€",
            "calculation": "incremental (each kWh × tariff at that time)",
        }


# =============================================================================
# EFFIZIENZ-SENSOREN
# =============================================================================


class SelfConsumptionRatioSensor(BaseEntity):
    """Eigenverbrauchsquote in Prozent."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Eigenverbrauchsquote",
            unit="%",
            icon="mdi:home-percent",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.self_consumption_ratio, 1)

    @property
    def extra_state_attributes(self):
        return {
            "description": "Anteil der PV-Produktion der selbst verbraucht wird",
        }


class AutarkyRateSensor(BaseEntity):
    """Autarkiegrad in Prozent."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Autarkiegrad",
            unit="%",
            icon="mdi:home-battery",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float | None:
        rate = self.ctrl.autarky_rate
        if rate is None:
            return None
        return round(rate, 1)

    @property
    def extra_state_attributes(self):
        return {
            "description": "Anteil des Verbrauchs der durch PV gedeckt wird",
            "hinweis": "Benötigt konfigurierten Verbrauchs-Sensor" if self.ctrl.autarky_rate is None else None,
        }


# =============================================================================
# STATISTIK-SENSOREN
# =============================================================================


class AverageDailySavingsSensor(BaseEntity):
    """Durchschnittliche tägliche Ersparnis."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ersparnis pro Tag",
            unit="€/Tag",
            icon="mdi:calendar-today",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.average_daily_savings, 2)


class AverageMonthlySavingsSensor(BaseEntity):
    """Durchschnittliche monatliche Ersparnis."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ersparnis pro Monat",
            unit="€/Monat",
            icon="mdi:calendar-month",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.average_monthly_savings, 2)


class AverageYearlySavingsSensor(BaseEntity):
    """Durchschnittliche jährliche Ersparnis."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ersparnis pro Jahr",
            unit="€/Jahr",
            icon="mdi:calendar",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.average_yearly_savings, 2)


class DaysSinceInstallationSensor(BaseEntity):
    """Tage seit Installation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Tage seit Installation",
            unit="Tage",
            icon="mdi:calendar-clock",
            state_class=SensorStateClass.TOTAL_INCREASING,
        )

    @property
    def native_value(self) -> int:
        return self.ctrl.days_since_installation


# =============================================================================
# PROGNOSE-SENSOREN
# =============================================================================


class EstimatedRemainingDaysSensor(BaseEntity):
    """Geschätzte verbleibende Tage bis Amortisation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Restlaufzeit",
            unit="Tage",
            icon="mdi:timer-sand",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> int | None:
        return self.ctrl.estimated_remaining_days

    @property
    def extra_state_attributes(self):
        remaining = self.ctrl.estimated_remaining_days
        if remaining is None:
            return {"status": "Berechnung nicht möglich"}

        years = remaining // 365
        months = (remaining % 365) // 30
        days = remaining % 30

        parts = []
        if years > 0:
            parts.append(f"{years} Jahr{'e' if years > 1 else ''}")
        if months > 0:
            parts.append(f"{months} Monat{'e' if months > 1 else ''}")
        if days > 0 or not parts:
            parts.append(f"{days} Tag{'e' if days != 1 else ''}")

        return {
            "formatted": ", ".join(parts),
            "years": years,
            "months": months,
            "days": days,
        }


class EstimatedPaybackDateSensor(BaseEntity):
    """Geschätztes Amortisationsdatum."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amortisationsdatum",
            icon="mdi:calendar-check",
            device_class=SensorDeviceClass.DATE,
        )

    @property
    def native_value(self) -> date | None:
        return self.ctrl.estimated_payback_date

    @property
    def icon(self) -> str:
        if self.ctrl.is_amortised:
            return "mdi:calendar-check"
        return "mdi:calendar-question"


# =============================================================================
# UMWELT-SENSOREN
# =============================================================================


class CO2SavedSensor(BaseEntity):
    """Eingesparte CO2-Emissionen."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "CO2 Ersparnis",
            unit="kg",
            icon="mdi:molecule-co2",
            state_class=SensorStateClass.TOTAL_INCREASING,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.co2_saved_kg, 1)

    @property
    def extra_state_attributes(self):
        kg = self.ctrl.co2_saved_kg
        return {
            "tonnes": f"{kg / 1000:.2f} t",
            "trees_equivalent": int(kg / 21),
            "car_km_equivalent": int(kg / 0.12),
        }


# =============================================================================
# KONFIGURATIONS-SENSOREN (DIAGNOSE)
# =============================================================================


class CurrentElectricityPriceSensor(BaseEntity):
    """Aktueller Strompreis."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Strompreis",
            unit="€/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.current_electricity_price, 4)

    @property
    def extra_state_attributes(self):
        raw = self.ctrl._last_known_electricity_price
        return {
            "source": self.ctrl.electricity_price_source,
            "sensor_available": self.ctrl._price_sensor_available,
            "raw_sensor_value": f"{raw:.4f}" if raw else None,
            "auto_detected_unit": "cent" if raw and raw > 1.0 else "euro" if raw else None,
            "config_fallback": f"{self.ctrl.electricity_price:.4f}",
            "config_unit": self.ctrl.electricity_price_unit,
        }


class CurrentFeedInTariffSensor(BaseEntity):
    """Aktuelle Einspeisevergütung."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Einspeisevergütung",
            unit="€/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.current_feed_in_tariff, 4)

    @property
    def extra_state_attributes(self):
        raw = self.ctrl._last_known_feed_in_tariff
        return {
            "source": self.ctrl.feed_in_tariff_source,
            "sensor_available": self.ctrl._tariff_sensor_available,
            "raw_sensor_value": f"{raw:.4f}" if raw else None,
            "auto_detected_unit": "cent" if raw and raw > 1.0 else "euro" if raw else None,
            "config_fallback": f"{self.ctrl.feed_in_tariff:.4f}",
            "config_unit": self.ctrl.feed_in_tariff_unit,
        }


class InstallationCostSensor(BaseEntity):
    """Anschaffungskosten der PV-Anlage."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Anschaffungskosten",
            unit="€",
            icon="mdi:cash",
            device_class=SensorDeviceClass.MONETARY,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.installation_cost, 2)


class ConfigurationDiagnosticSensor(BaseEntity):
    """Diagnose-Sensor zeigt alle konfigurierten Sensoren und deren Status."""

    def __init__(self, ctrl, name: str, entry: ConfigEntry):
        super().__init__(
            ctrl,
            name,
            "Konfiguration",
            icon="mdi:cog",
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._entry = entry

    def _get_entity_status(self, entity_id: str | None) -> dict[str, Any]:
        """Holt Status einer Entity."""
        if not entity_id:
            return {"configured": False, "entity_id": None, "state": None, "status": "nicht konfiguriert"}

        state = self.hass.states.get(entity_id)
        if state is None:
            return {
                "configured": True,
                "entity_id": entity_id,
                "state": None,
                "status": "nicht gefunden",
            }
        elif state.state in ("unavailable", "unknown"):
            return {
                "configured": True,
                "entity_id": entity_id,
                "state": state.state,
                "status": "nicht verfügbar",
            }
        else:
            return {
                "configured": True,
                "entity_id": entity_id,
                "state": state.state,
                "status": "OK",
            }

    @property
    def native_value(self) -> str:
        """Zeigt Gesamtstatus der Konfiguration."""
        issues = 0

        # Prüfe alle konfigurierten Sensoren
        entities_to_check = [
            self.ctrl.pv_production_entity,
            self.ctrl.grid_export_entity,
        ]

        for entity_id in entities_to_check:
            if entity_id:
                status = self._get_entity_status(entity_id)
                if status["status"] != "OK":
                    issues += 1

        if issues == 0:
            return "OK"
        else:
            return f"{issues} Problem{'e' if issues > 1 else ''}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Zeigt alle konfigurierten Sensoren und deren Status."""
        pv_status = self._get_entity_status(self.ctrl.pv_production_entity)
        export_status = self._get_entity_status(self.ctrl.grid_export_entity)
        import_status = self._get_entity_status(self.ctrl.grid_import_entity)
        consumption_status = self._get_entity_status(self.ctrl.consumption_entity)
        price_status = self._get_entity_status(self.ctrl.electricity_price_entity)
        tariff_status = self._get_entity_status(self.ctrl.feed_in_tariff_entity)

        return {
            # === SENSOR-KONFIGURATION ===
            "pv_production_entity": pv_status["entity_id"],
            "pv_production_status": pv_status["status"],
            "pv_production_value": pv_status["state"],

            "grid_export_entity": export_status["entity_id"],
            "grid_export_status": export_status["status"],
            "grid_export_value": export_status["state"],

            "grid_import_entity": import_status["entity_id"],
            "grid_import_status": import_status["status"],
            "grid_import_value": import_status["state"],

            "consumption_entity": consumption_status["entity_id"],
            "consumption_status": consumption_status["status"],
            "consumption_value": consumption_status["state"],

            # Preissensoren (optional)
            "electricity_price_entity": price_status["entity_id"],
            "electricity_price_status": price_status["status"],
            "electricity_price_value": price_status["state"],
            "electricity_price_source": "sensor" if self.ctrl.electricity_price_entity else "config",

            "feed_in_tariff_entity": tariff_status["entity_id"],
            "feed_in_tariff_status": tariff_status["status"],
            "feed_in_tariff_value": tariff_status["state"],
            "feed_in_tariff_source": "sensor" if self.ctrl.feed_in_tariff_entity else "config",

            # === AKKUMULIERTE WERTE (diese werden gespeichert) ===
            "tracked_self_consumption_kwh": round(self.ctrl._total_self_consumption_kwh, 4),
            "tracked_feed_in_kwh": round(self.ctrl._total_feed_in_kwh, 4),
            "accumulated_savings_self_eur": round(self.ctrl._accumulated_savings_self, 4),
            "accumulated_earnings_feed_eur": round(self.ctrl._accumulated_earnings_feed, 4),

            # === LETZTE SENSOR-WERTE (für Delta-Berechnung) ===
            "last_pv_production_kwh": self.ctrl._last_pv_production_kwh,
            "last_grid_export_kwh": self.ctrl._last_grid_export_kwh,

            # === AKTUELLE SENSOR-WERTE ===
            "current_pv_production_kwh": round(self.ctrl._pv_production_kwh, 4),
            "current_grid_export_kwh": round(self.ctrl._grid_export_kwh, 4),
            "current_grid_import_kwh": round(self.ctrl._grid_import_kwh, 4),
            "current_consumption_kwh": round(self.ctrl._consumption_kwh, 4),

            # === BERECHNETE WERTE ===
            "total_self_consumption_kwh": round(self.ctrl.self_consumption_kwh, 4),
            "total_feed_in_kwh": round(self.ctrl.feed_in_kwh, 4),
            "total_savings_eur": round(self.ctrl.total_savings, 4),

            # === PREISE ===
            "current_electricity_price_eur": round(self.ctrl.current_electricity_price, 4),
            "current_feed_in_tariff_eur": round(self.ctrl.current_feed_in_tariff, 4),

            # === META ===
            "tracking_active": self.ctrl._first_seen_date is not None,
            "first_seen_date": self.ctrl._first_seen_date.isoformat() if self.ctrl._first_seen_date else None,
            "days_tracked": self.ctrl.days_since_installation,
            "data_restored": self.ctrl._restored,
            "calculation_method": "incremental",
        }

    @property
    def icon(self) -> str:
        """Icon basierend auf Status."""
        if self.native_value == "OK":
            return "mdi:check-circle"
        else:
            return "mdi:alert-circle"


# =============================================================================
# EMPFEHLUNGS-SENSOR (AMPEL)
# =============================================================================


class ConsumptionRecommendationSensor(BaseEntity):
    """
    Stromverbrauch-Empfehlung als Ampel.

    Zeigt an, ob jetzt ein guter Zeitpunkt ist, Strom zu verbrauchen.
    Basiert auf: PV-Leistung, Batterie, Strompreis, Tageszeit, Prognose.
    """

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Verbrauchsempfehlung",
            icon="mdi:traffic-light",
        )

    @property
    def native_value(self) -> str:
        """Zeigt Empfehlungstext."""
        return self.ctrl.consumption_recommendation_text

    @property
    def icon(self) -> str:
        """Icon als Ampel-Farbe."""
        rec = self.ctrl.consumption_recommendation
        if rec == RECOMMENDATION_GREEN:
            return "mdi:checkbox-marked-circle"  # Grüner Haken
        elif rec == RECOMMENDATION_RED:
            return "mdi:close-circle"  # Rotes X
        else:
            return "mdi:minus-circle"  # Gelber Strich

    def _calculate_score_breakdown(self) -> dict[str, Any]:
        """Berechnet detaillierte Score-Aufschlüsselung."""
        from datetime import datetime

        breakdown = {}
        total_score = 0
        reasons_positive = []
        reasons_negative = []

        # === PV-Leistung ===
        pv_power = self.ctrl.pv_power
        pv_threshold = self.ctrl.pv_power_high

        if pv_power >= pv_threshold:
            pv_score = 3
            reasons_positive.append(f"Hohe PV-Leistung ({pv_power:.0f}W)")
        elif pv_power >= pv_threshold * 0.5:
            pv_score = 1
            reasons_positive.append(f"Mittlere PV-Leistung ({pv_power:.0f}W)")
        elif pv_power < 100:
            pv_score = -1
            reasons_negative.append(f"Kaum PV-Leistung ({pv_power:.0f}W)")
        else:
            pv_score = 0

        breakdown["pv_leistung"] = {
            "wert": f"{pv_power:.0f} W",
            "schwelle_hoch": f"{pv_threshold:.0f} W",
            "punkte": pv_score,
            "bewertung": "+++" if pv_score >= 3 else "++" if pv_score >= 1 else "--" if pv_score < 0 else "o"
        }
        total_score += pv_score

        # === Batterie ===
        if self.ctrl.battery_soc_entity:
            battery_soc = self.ctrl.battery_soc
            soc_high = self.ctrl.battery_soc_high
            soc_low = self.ctrl.battery_soc_low

            if battery_soc >= soc_high:
                bat_score = 2
                reasons_positive.append(f"Batterie voll ({battery_soc:.0f}%)")
            elif battery_soc <= soc_low:
                bat_score = -2
                reasons_negative.append(f"Batterie leer ({battery_soc:.0f}%)")
            else:
                bat_score = 0

            breakdown["batterie"] = {
                "wert": f"{battery_soc:.0f}%",
                "schwelle_voll": f"{soc_high:.0f}%",
                "schwelle_leer": f"{soc_low:.0f}%",
                "punkte": bat_score,
                "bewertung": "++" if bat_score >= 2 else "--" if bat_score <= -2 else "o"
            }
            total_score += bat_score

        # === Strompreis ===
        price = self.ctrl.current_electricity_price
        price_low = self.ctrl.price_low_threshold
        price_high = self.ctrl.price_high_threshold

        if price <= price_low:
            price_score = 2
            reasons_positive.append(f"Günstiger Strom ({price:.2f}€/kWh)")
        elif price >= price_high:
            price_score = -2
            reasons_negative.append(f"Teurer Strom ({price:.2f}€/kWh)")
        else:
            price_score = 0

        breakdown["strompreis"] = {
            "wert": f"{price:.4f} €/kWh",
            "quelle": self.ctrl.electricity_price_source,
            "schwelle_guenstig": f"{price_low:.2f} €/kWh",
            "schwelle_teuer": f"{price_high:.2f} €/kWh",
            "punkte": price_score,
            "bewertung": "++" if price_score >= 2 else "--" if price_score <= -2 else "o"
        }
        total_score += price_score

        # === Tageszeit ===
        hour = datetime.now().hour

        if 10 <= hour <= 15:
            time_score = 1
            reasons_positive.append(f"Gute Tageszeit ({hour}:00)")
        elif hour < 6 or hour > 21:
            time_score = -1
            reasons_negative.append(f"Nachtzeit ({hour}:00)")
        else:
            time_score = 0

        breakdown["tageszeit"] = {
            "wert": f"{hour}:00 Uhr",
            "kernzeit": "10:00 - 15:00",
            "punkte": time_score,
            "bewertung": "+" if time_score >= 1 else "-" if time_score <= -1 else "o"
        }
        total_score += time_score

        # === PV-Prognose ===
        if self.ctrl.pv_forecast_entity and self.ctrl.pv_forecast > 0:
            forecast = self.ctrl.pv_forecast

            if forecast >= 10:
                forecast_score = 1
                reasons_positive.append(f"Gute PV-Prognose ({forecast:.1f} kWh)")
            elif forecast < 3:
                forecast_score = -1
                reasons_negative.append(f"Schlechte PV-Prognose ({forecast:.1f} kWh)")
            else:
                forecast_score = 0

            breakdown["pv_prognose"] = {
                "wert": f"{forecast:.1f} kWh",
                "schwelle_gut": "≥10 kWh",
                "schwelle_schlecht": "<3 kWh",
                "punkte": forecast_score,
                "bewertung": "+" if forecast_score >= 1 else "-" if forecast_score <= -1 else "o"
            }
            total_score += forecast_score

        # === Zusammenfassung ===
        breakdown["gesamt"] = {
            "punkte": total_score,
            "bereich": "grün (≥3)" if total_score >= 3 else "rot (≤-2)" if total_score <= -2 else "gelb",
        }

        return {
            "breakdown": breakdown,
            "gruende_positiv": reasons_positive,
            "gruende_negativ": reasons_negative,
            "total_score": total_score,
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Detaillierte Infos zur Empfehlung mit Score-Aufschlüsselung."""
        rec = self.ctrl.consumption_recommendation
        analysis = self._calculate_score_breakdown()

        attrs = {
            # Hauptinfo
            "ampel": rec,
            "gesamt_score": analysis["total_score"],
            "bewertung": self._get_score_explanation(analysis["total_score"]),

            # Gründe (für einfache Anzeige)
            "gruende_positiv": ", ".join(analysis["gruende_positiv"]) if analysis["gruende_positiv"] else "Keine",
            "gruende_negativ": ", ".join(analysis["gruende_negativ"]) if analysis["gruende_negativ"] else "Keine",

            # Detaillierte Aufschlüsselung
            "score_details": analysis["breakdown"],

            # Konfiguration (zum Nachvollziehen)
            "config": {
                "pv_power_schwelle": f"{self.ctrl.pv_power_high:.0f} W",
                "preis_guenstig": f"{self.ctrl.price_low_threshold:.2f} €/kWh",
                "preis_teuer": f"{self.ctrl.price_high_threshold:.2f} €/kWh",
                "batterie_voll": f"{self.ctrl.battery_soc_high:.0f}%" if self.ctrl.battery_soc_entity else "N/A",
                "batterie_leer": f"{self.ctrl.battery_soc_low:.0f}%" if self.ctrl.battery_soc_entity else "N/A",
            },
        }

        return attrs

    def _get_score_explanation(self, score: int) -> str:
        """Erklärt den Score."""
        if score >= 5:
            return "Idealer Zeitpunkt!"
        elif score >= 3:
            return "Guter Zeitpunkt"
        elif score >= 1:
            return "Akzeptabel"
        elif score >= -1:
            return "Neutral"
        elif score >= -3:
            return "Eher ungünstig"
        else:
            return "Schlechter Zeitpunkt"

    @property
    def available(self) -> bool:
        """Sensor ist immer verfügbar."""
        return True
