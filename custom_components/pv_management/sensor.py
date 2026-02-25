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
    RECOMMENDATION_DARK_GREEN, RECOMMENDATION_GREEN, RECOMMENDATION_YELLOW, RECOMMENDATION_RED,
)

_LOGGER = logging.getLogger(__name__)

# Geräte-Typen für bessere Übersicht
DEVICE_MAIN = "main"            # PV Management (Haupt)
DEVICE_BATTERY = "battery"      # PV Batterie
DEVICE_PRICES = "prices"        # PV Strompreise
DEVICE_BENCHMARK = "benchmark"  # Energie-Benchmark
DEVICE_PV_STRINGS = "pv_strings"


def get_device_info(name: str, device_type: str = DEVICE_MAIN) -> DeviceInfo:
    """Erstellt DeviceInfo für verschiedene Geräte-Typen."""
    if device_type == DEVICE_BATTERY:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_battery")},
            name=f"{name} Batterie",
            manufacturer="Custom",
            model="PV Management - Batterie",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_PRICES:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_prices")},
            name=f"{name} Strompreise",
            manufacturer="Custom",
            model="PV Management - Strompreise",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_BENCHMARK:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_benchmark")},
            name=f"{name} Energie-Benchmark",
            manufacturer="Custom",
            model="PV Management - Energie-Benchmark",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_PV_STRINGS:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_pv_strings")},
            name=f"{name} PV-Strings",
            manufacturer="Custom",
            model="PV Management - PV-Strings",
            via_device=(DOMAIN, name),
        )
    else:  # DEVICE_MAIN
        return DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            manufacturer="Custom",
            model="PV Management",
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Sensoren."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Management")

    entities = [
        # === EMPFEHLUNG (wichtigste für tägliche Nutzung) ===
        ConsumptionRecommendationSensor(ctrl, name),
        NextCheapHourSensor(ctrl, name),

        # === AMORTISATION (Hauptzweck) ===
        AmortisationPercentSensor(ctrl, name),
        TotalSavingsSensor(ctrl, name),  # Dieser speichert persistent!
        RemainingCostSensor(ctrl, name),
        StatusSensor(ctrl, name),
        EstimatedPaybackDateSensor(ctrl, name),
        EstimatedRemainingDaysSensor(ctrl, name),

        # === ENERGIE ===
        SelfConsumptionSensor(ctrl, name),
        FeedInSensor(ctrl, name),
        SelfConsumptionRatioSensor(ctrl, name),
        AutarkyRateSensor(ctrl, name),

        # === FINANZEN ===
        SavingsSelfConsumptionSensor(ctrl, name),
        EarningsFeedInSensor(ctrl, name),

        # === STATISTIK ===
        AverageDailySavingsSensor(ctrl, name),
        AverageMonthlySavingsSensor(ctrl, name),
        AverageYearlySavingsSensor(ctrl, name),
        DaysSinceInstallationSensor(ctrl, name),

        # === UMWELT ===
        CO2SavedSensor(ctrl, name),

        # === DIAGNOSE ===
        CurrentElectricityPriceSensor(ctrl, name),
        CurrentFeedInTariffSensor(ctrl, name),
        PVProductionSensor(ctrl, name),
        InstallationCostSensor(ctrl, name),
        ConfigurationDiagnosticSensor(ctrl, name, entry),

        # === TÄGLICHE STROMKOSTEN ===
        DailyFeedInSensor(ctrl, name),
        DailyGridImportSensor(ctrl, name),
        DailyNetElectricityCostSensor(ctrl, name),

        # === STROMPREIS-DURCHSCHNITT ===
        DailyAveragePriceSensor(ctrl, name),
        MonthlyAveragePriceSensor(ctrl, name),
        AverageElectricityPriceSensor(ctrl, name),
        TotalGridImportCostSensor(ctrl, name),
        SpotVsFixedPriceSensor(ctrl, name),  # NEU: Vergleich Spot vs. Fixpreis

        # === AUTO-CHARGE BATTERIE ===
        AutoChargeReasonSensor(ctrl, name),
        AutoChargePriceDiffSensor(ctrl, name),
        AutoChargePVForecastSensor(ctrl, name),
        AutoChargePriceQuantileSensor(ctrl, name),
        AutoChargeConditionsSensor(ctrl, name),
        AutoChargeDiagnosticSensor(ctrl, name),
    ]

    # === BENCHMARK (optional) ===
    if ctrl.benchmark_enabled:
        entities.extend([
            BenchmarkAvgSensor(ctrl, name),
            BenchmarkOwnSensor(ctrl, name),
            BenchmarkComparisonSensor(ctrl, name),
            BenchmarkCO2Sensor(ctrl, name),
            BenchmarkScoreSensor(ctrl, name),
            BenchmarkRatingSensor(ctrl, name),
        ])
        if ctrl.benchmark_heatpump:
            entities.extend([
                BenchmarkHeatpumpAvgSensor(ctrl, name),
                BenchmarkHeatpumpOwnSensor(ctrl, name),
            ])

    # === PV-STRINGS (optional) ===
    if ctrl.pv_strings:
        for i, (string_name, string_entity) in enumerate(ctrl.pv_strings):
            entities.extend([
                PVStringSensor(ctrl, name, i, string_name, string_entity, "production"),
                PVStringSensor(ctrl, name, i, string_name, string_entity, "daily"),
                PVStringSensor(ctrl, name, i, string_name, string_entity, "percentage"),
            ])

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
        device_type: str = DEVICE_MAIN,
    ):
        self.ctrl = ctrl
        self._base_name = name
        self._attr_name = f"{name} {key}"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_{key.lower().replace(' ', '_')}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_state_class = state_class
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_device_info = get_device_info(name, device_type)
        self._removed = False

    @property
    def available(self) -> bool:
        """Sensor ist erst verfügbar wenn gespeicherte Daten wiederhergestellt sind."""
        return getattr(self.ctrl, "_restored", True)

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


class PVStringSensor(BaseEntity):
    """Generischer Sensor für PV-String Vergleich."""

    def __init__(self, ctrl, name: str, string_index: int, string_name: str, entity_id: str, sensor_type: str):
        self._string_entity_id = entity_id
        self._sensor_type = sensor_type

        if sensor_type == "production":
            key = f"{string_name} Produktion"
            unit = "kWh"
            icon = "mdi:solar-panel"
            state_class = SensorStateClass.TOTAL_INCREASING
        elif sensor_type == "daily":
            key = f"{string_name} Tagesproduktion"
            unit = "kWh/Tag"
            icon = "mdi:weather-sunny"
            state_class = SensorStateClass.MEASUREMENT
        else:  # percentage
            key = f"{string_name} Anteil"
            unit = "%"
            icon = "mdi:chart-pie"
            state_class = SensorStateClass.MEASUREMENT

        super().__init__(ctrl, name, key, unit=unit, icon=icon, state_class=state_class, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        if self._sensor_type == "production":
            val = self.ctrl.get_string_production_kwh(self._string_entity_id)
            return round(val, 2) if val else 0.0
        elif self._sensor_type == "daily":
            val = self.ctrl.get_string_daily_kwh(self._string_entity_id)
            return round(val, 2) if val is not None else None
        else:  # percentage
            val = self.ctrl.get_string_percentage(self._string_entity_id)
            return round(val, 1) if val is not None else None


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

            # Explizite Float-Konvertierung (HA speichert manchmal als String)
            def safe_float(val, default=0.0):
                try:
                    return float(val) if val is not None else default
                except (ValueError, TypeError):
                    return default

            restore_data = {
                "total_self_consumption_kwh": safe_float(attrs.get("tracked_self_consumption_kwh")),
                "total_feed_in_kwh": safe_float(attrs.get("tracked_feed_in_kwh")),
                "accumulated_savings_self": safe_float(attrs.get("accumulated_savings_self")),
                "accumulated_earnings_feed": safe_float(attrs.get("accumulated_earnings_feed")),
                "first_seen_date": attrs.get("first_seen_date"),
                # Strompreis-Tracking
                "tracked_grid_import_kwh": safe_float(attrs.get("tracked_grid_import_kwh")),
                "total_grid_import_cost": safe_float(attrs.get("total_grid_import_cost")),
                # Auto-Charge Statistiken
                "auto_charge_count": safe_float(attrs.get("auto_charge_count")),
                "auto_charge_total_hours": safe_float(attrs.get("auto_charge_total_hours")),
                "auto_charge_total_kwh": safe_float(attrs.get("auto_charge_total_kwh")),
                "auto_charge_estimated_savings": safe_float(attrs.get("auto_charge_estimated_savings")),
            }

            _LOGGER.info(
                "TotalSavingsSensor: Restore data: self=%.2f kWh, feed=%.2f kWh, savings=%.2f€, earnings=%.2f€",
                restore_data["total_self_consumption_kwh"],
                restore_data["total_feed_in_kwh"],
                restore_data["accumulated_savings_self"],
                restore_data["accumulated_earnings_feed"],
            )

            self.ctrl.restore_state(restore_data)
            _LOGGER.info("TotalSavingsSensor: Zustand wiederhergestellt")

            # Explizites State-Update nach Restore
            self.async_write_ha_state()

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
            # Strompreis-Tracking (werden restored)
            "tracked_grid_import_kwh": round(self.ctrl._tracked_grid_import_kwh, 4),
            "total_grid_import_cost": round(self.ctrl._total_grid_import_cost, 4),
            # Auto-Charge Statistiken (werden restored)
            "auto_charge_count": self.ctrl._auto_charge_count,
            "auto_charge_total_hours": round(self.ctrl._auto_charge_total_hours, 2),
            "auto_charge_total_kwh": round(self.ctrl._auto_charge_total_kwh, 2),
            "auto_charge_estimated_savings": round(self.ctrl._auto_charge_estimated_savings, 2),
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

            # === EPEX SPOT INTEGRATION ===
            "epex_price_entity": self.ctrl.epex_price_entity,
            "epex_price_value": f"{self.ctrl.epex_price:.4f}" if self.ctrl.epex_price_entity else None,
            "epex_quantile_entity": self.ctrl.epex_quantile_entity,
            "epex_quantile_value": f"{self.ctrl.epex_quantile:.2f}" if self.ctrl.epex_quantile_entity else None,
            "epex_forecast_entries": len(self.ctrl.epex_price_forecast),

            # === SOLCAST INTEGRATION ===
            "solcast_forecast_entity": self.ctrl.solcast_forecast_entity,
            "solcast_forecast_today": f"{self.ctrl.solcast_forecast_today:.1f}" if self.ctrl.solcast_forecast_entity else None,
            "solcast_hourly_entries": len(self.ctrl.solcast_hourly_forecast),

            # === META ===
            "tracking_active": self.ctrl._first_seen_date is not None,
            "first_seen_date": self.ctrl._first_seen_date.isoformat() if self.ctrl._first_seen_date else None,
            "days_tracked": self.ctrl.days_since_installation,
            "data_restored": self.ctrl._restored,
            "calculation_method": "incremental",
            "has_epex_integration": self.ctrl.has_epex_integration,
            "has_solcast_integration": self.ctrl.has_solcast_integration,
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
        if rec == RECOMMENDATION_DARK_GREEN:
            return "mdi:checkbox-marked-circle-outline"  # Doppelter Haken
        elif rec == RECOMMENDATION_GREEN:
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

        # === PV-Leistung (basierend auf Peak-Leistung, mit Winter-Grundlast-Abzug) ===
        pv_power_raw = self.ctrl.pv_power
        pv_power = self.ctrl.effective_pv_power  # Mit Winter-Grundlast-Abzug
        pv_peak = self.ctrl.pv_peak_power
        winter_base = self.ctrl.winter_base_load
        is_winter = self.ctrl.is_winter
        pv_very_high = pv_peak * 0.6
        pv_high = pv_peak * 0.3
        pv_moderate = pv_peak * 0.1
        pv_low = pv_peak * 0.05
        pv_percent = (pv_power / pv_peak * 100) if pv_peak > 0 else 0

        if pv_power >= pv_very_high:
            pv_score = 4
            reasons_positive.append("Sehr viel PV")
        elif pv_power >= pv_high:
            pv_score = 2
            reasons_positive.append("Viel PV")
        elif pv_power >= pv_moderate:
            pv_score = 1
            reasons_positive.append("Etwas PV")
        elif pv_power < pv_low:
            pv_score = -1
            reasons_negative.append("Kaum PV")
        else:
            pv_score = 0

        breakdown["pv_leistung"] = {
            "wert": f"{pv_power_raw:.0f} W",
            "effektiv": f"{pv_power:.0f} W" if is_winter and winter_base > 0 else None,
            "winter_grundlast": f"{winter_base:.0f} W" if is_winter and winter_base > 0 else None,
            "prozent": f"{pv_percent:.0f}%",
            "peak_leistung": f"{pv_peak:.0f} W",
            "schwelle_sehr_hoch": f"{pv_very_high:.0f} W (60%)",
            "schwelle_hoch": f"{pv_high:.0f} W (30%)",
            "schwelle_moderat": f"{pv_moderate:.0f} W (10%)",
            "punkte": pv_score,
            "bewertung": "++++" if pv_score >= 4 else "++" if pv_score >= 2 else "+" if pv_score >= 1 else "--" if pv_score < 0 else "o"
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

        # === Strompreis (EPEX Quantile hat Priorität) ===
        if self.ctrl.epex_quantile_entity and 0 <= self.ctrl.epex_quantile <= 1:
            quantile = self.ctrl.epex_quantile
            epex_price = self.ctrl.epex_price

            if quantile <= 0.2:
                price_score = 3
                reasons_positive.append(f"EPEX Top 20% günstig (Q={quantile:.2f})")
            elif quantile <= 0.4:
                price_score = 1
                reasons_positive.append(f"EPEX günstig (Q={quantile:.2f})")
            elif quantile >= 0.8:
                price_score = -3
                reasons_negative.append(f"EPEX Top 20% teuer (Q={quantile:.2f})")
            elif quantile >= 0.6:
                price_score = -1
                reasons_negative.append(f"EPEX teuer (Q={quantile:.2f})")
            else:
                price_score = 0

            breakdown["strompreis"] = {
                "wert": f"{epex_price:.4f} €/kWh",
                "quelle": "EPEX Spot",
                "quantile": f"{quantile:.2f}",
                "quantile_erklaerung": "0=günstigster, 1=teuerster Preis des Tages",
                "bewertung_bereich": "≤0.2: +++, ≤0.4: +, ≥0.6: -, ≥0.8: ---",
                "punkte": price_score,
                "bewertung": "+++" if price_score >= 3 else "++" if price_score >= 2 else "+" if price_score >= 1 else "---" if price_score <= -3 else "--" if price_score <= -2 else "-" if price_score <= -1 else "o"
            }
        else:
            # Fallback: Absoluter Preis
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

        # === PV-Prognose (Solcast hat Priorität) ===
        forecast_source = None
        forecast = 0.0

        if self.ctrl.solcast_forecast_entity and self.ctrl.solcast_forecast_today > 0:
            forecast = self.ctrl.solcast_forecast_today
            forecast_source = "Solcast"
        elif self.ctrl.pv_forecast_entity and self.ctrl.pv_forecast > 0:
            forecast = self.ctrl.pv_forecast
            forecast_source = "Standard"

        if forecast_source and forecast > 0:
            if forecast >= 10:
                forecast_score = 1
                reasons_positive.append(f"Gute PV-Prognose ({forecast:.1f} kWh, {forecast_source})")
            elif forecast < 3:
                forecast_score = -1
                reasons_negative.append(f"Schlechte PV-Prognose ({forecast:.1f} kWh, {forecast_source})")
            else:
                forecast_score = 0

            breakdown["pv_prognose"] = {
                "wert": f"{forecast:.1f} kWh",
                "quelle": forecast_source,
                "schwelle_gut": "≥10 kWh",
                "schwelle_schlecht": "<3 kWh",
                "punkte": forecast_score,
                "bewertung": "+" if forecast_score >= 1 else "-" if forecast_score <= -1 else "o"
            }
            total_score += forecast_score

        # === Zusammenfassung ===
        if total_score >= 5:
            bereich = "dunkelgrün (≥5)"
        elif total_score >= 3:
            bereich = "grün (≥3)"
        elif total_score <= -2:
            bereich = "rot (≤-2)"
        else:
            bereich = "gelb"

        breakdown["gesamt"] = {
            "punkte": total_score,
            "bereich": bereich,
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
            "farbe": self.ctrl.consumption_recommendation_color,
            "gesamt_score": analysis["total_score"],
            "bewertung": self._get_score_explanation(analysis["total_score"]),

            # === NEU: Für mehrzeilige Card-Anzeige ===
            "status": self.ctrl.recommendation_status,  # "Ungünstig", "Guter Zeitpunkt", etc.
            "gruende": self.ctrl.recommendation_reasons,  # Alle Gründe kombiniert
            "tipp": self.ctrl.best_opportunity_text,  # Bester Tipp (PV oder Preis)

            # === Separate Infos für flexible Card-Layouts ===
            "pv_info": self.ctrl.pv_info,  # "kein PV", "kaum PV", "viel PV", etc.
            "akku_info": self.ctrl.akku_info,  # "Akku voll", "Akku leer", oder leer
            "preis_info": self.ctrl.preis_info,  # "Strom günstig", "Strom teuer", oder leer
            "pv_tipp": self.ctrl.pv_tipp,  # "In 2h ca. 5 kW PV (12:00)" oder leer
            "preis_tipp": self.ctrl.preis_tipp,  # "In 3h günstig (14:00, 12ct)"

            # Gründe (für einfache Anzeige)
            "gruende_positiv": ", ".join(analysis["gruende_positiv"]) if analysis["gruende_positiv"] else "Keine",
            "gruende_negativ": ", ".join(analysis["gruende_negativ"]) if analysis["gruende_negativ"] else "Keine",

            # Detaillierte Aufschlüsselung
            "score_details": analysis["breakdown"],

            # Konfiguration (zum Nachvollziehen)
            "config": {
                "pv_peak_leistung": f"{self.ctrl.pv_peak_power:.0f} W",
                "pv_sehr_hoch": f"{self.ctrl.pv_peak_power * 0.6:.0f} W (60%)",
                "pv_hoch": f"{self.ctrl.pv_peak_power * 0.3:.0f} W (30%)",
                "preis_guenstig": f"{self.ctrl.price_low_threshold:.2f} €/kWh",
                "preis_teuer": f"{self.ctrl.price_high_threshold:.2f} €/kWh",
                "batterie_voll": f"{self.ctrl.battery_soc_high:.0f}%" if self.ctrl.battery_soc_entity else "N/A",
                "batterie_leer": f"{self.ctrl.battery_soc_low:.0f}%" if self.ctrl.battery_soc_entity else "N/A",
            },

            # Integration Status
            "integrationen": {
                "epex_spot": self.ctrl.has_epex_integration,
                "solcast": self.ctrl.has_solcast_integration,
            },
        }

        # EPEX Spot Details wenn verfügbar
        if self.ctrl.has_epex_integration:
            attrs["epex_spot"] = {
                "preis": f"{self.ctrl.epex_price:.4f} €/kWh" if self.ctrl.epex_price_entity else "N/A",
                "quantile": f"{self.ctrl.epex_quantile:.2f}" if self.ctrl.epex_quantile_entity else "N/A",
                "quantile_erklaerung": "0=günstigster, 1=teuerster Preis des Tages",
                "prognose_eintraege": len(self.ctrl.epex_price_forecast),
            }

        # Solcast Details wenn verfügbar
        if self.ctrl.has_solcast_integration:
            attrs["solcast"] = {
                "prognose_heute": f"{self.ctrl.solcast_forecast_today:.1f} kWh",
                "stunden_eintraege": len(self.ctrl.solcast_hourly_forecast),
            }

        return attrs

    def _get_score_explanation(self, score: int) -> str:
        """Erklärt den Score."""
        if score >= 6:
            return "Perfekter Zeitpunkt!"
        elif score >= 5:
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
        """Sensor ist erst nach Datenwiederherstellung verfügbar."""
        return super().available


class NextCheapHourSensor(BaseEntity):
    """
    Zeigt die nächste günstige Stunde basierend auf EPEX Preisprognose.

    Benötigt konfigurierte EPEX Spot Integration mit Preisprognose.
    """

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Nächste günstige Stunde",
            icon="mdi:clock-check",
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> str:
        """Zeigt wann die nächste günstige Stunde ist."""
        return self.ctrl.next_cheap_hour_text

    @property
    def icon(self) -> str:
        """Icon basierend auf Verfügbarkeit."""
        info = self.ctrl.next_cheap_hour
        if not info:
            return "mdi:clock-alert"
        elif info["in_hours"] == 0:
            return "mdi:clock-check"
        elif info["in_hours"] <= 2:
            return "mdi:clock-fast"
        else:
            return "mdi:clock-outline"

    @property
    def extra_state_attributes(self) -> dict:
        """Detaillierte Informationen zur Preisprognose."""
        info = self.ctrl.next_cheap_hour

        attrs = {
            "epex_integration": self.ctrl.has_epex_integration,
            "forecast_entries": len(self.ctrl.epex_price_forecast),
        }

        if info:
            attrs.update({
                "hour": info["hour"],
                "price_eur_kwh": round(info["price"], 4),
                "in_hours": info["in_hours"],
            })

        return attrs

    @property
    def available(self) -> bool:
        """Sensor ist erst nach Datenwiederherstellung verfügbar."""
        return super().available


# =============================================================================
# STROMPREIS-DURCHSCHNITTS-SENSOREN
# =============================================================================


class DailyFeedInSensor(BaseEntity):
    """Einspeisung heute: Vergütung und Menge."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Einspeisung Heute",
            unit="€",
            icon="mdi:transmission-tower-export",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.daily_feed_in_earnings, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "menge_kwh": round(self.ctrl.daily_feed_in_kwh, 2),
            "vergütung_ct": f"{self.ctrl.current_feed_in_tariff * 100:.2f}",
        }


class DailyGridImportSensor(BaseEntity):
    """Netzbezug heute: Kosten und Verbrauch."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Netzbezug Heute",
            unit="€",
            icon="mdi:transmission-tower-import",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.daily_grid_import_cost, 2)

    @property
    def extra_state_attributes(self) -> dict:
        avg = self.ctrl.daily_average_price_ct
        return {
            "verbrauch_kwh": round(self.ctrl.daily_grid_import_kwh, 2),
            "durchschnitt_ct": round(avg, 2) if avg else None,
        }


class DailyAveragePriceSensor(BaseEntity):
    """Durchschnittlich bezahlter Strompreis heute in ct/kWh."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ø Strompreis Heute",
            unit="ct/kWh",
            icon="mdi:calendar-today",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float | None:
        avg = self.ctrl.daily_average_price_ct
        if avg is None:
            return None
        return round(avg, 2)


class MonthlyAveragePriceSensor(BaseEntity):
    """Durchschnittlich bezahlter Strompreis diesen Monat in ct/kWh."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ø Strompreis Monat",
            unit="ct/kWh",
            icon="mdi:calendar-month",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float | None:
        avg = self.ctrl.monthly_average_price_ct
        if avg is None:
            return None
        return round(avg, 2)


class AverageElectricityPriceSensor(BaseEntity):
    """
    Gesamter gewichteter Durchschnittsstrompreis in ct/kWh.

    Zeigt den tatsächlich bezahlten Durchschnittspreis seit Tracking-Beginn.
    Ideal zum Vergleich mit Fixpreis-Tarifen.
    """

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ø Strompreis Gesamt",
            unit="ct/kWh",
            icon="mdi:chart-line",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float | None:
        avg = self.ctrl.average_electricity_price_ct
        if avg is None:
            return None
        return round(avg, 2)

    @property
    def extra_state_attributes(self) -> dict:
        avg_eur = self.ctrl.average_electricity_price
        return {
            "verbrauch_kwh": round(self.ctrl.tracked_grid_import_kwh, 2),
            "kosten_eur": round(self.ctrl.total_grid_import_cost, 2),
            "average_eur_per_kwh": f"{avg_eur:.4f}" if avg_eur else None,
            "beschreibung": "Gewichteter Durchschnitt seit Tracking-Beginn",
        }


class DailyNetElectricityCostSensor(BaseEntity):
    """Netto-Stromkosten heute: Netzbezug minus Einspeisung."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Stromkosten Netto Heute",
            unit="€",
            icon="mdi:cash-register",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.daily_net_electricity_cost, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "netzbezug_eur": round(self.ctrl.daily_grid_import_cost, 2),
            "einspeisung_eur": round(self.ctrl.daily_feed_in_earnings, 2),
        }


class TotalGridImportCostSensor(BaseEntity):
    """Gesamtkosten für Netzbezug in Euro."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Netzbezug Kosten",
            unit="€",
            icon="mdi:cash-minus",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.total_grid_import_cost, 2)

    @property
    def extra_state_attributes(self) -> dict:
        avg = self.ctrl.average_electricity_price_ct
        return {
            "verbrauch_kwh": round(self.ctrl.tracked_grid_import_kwh, 2),
            "durchschnittspreis_ct": f"{avg:.2f}" if avg else None,
        }


class SpotVsFixedPriceSensor(BaseEntity):
    """
    Vergleich Spot-Tarif vs. konfiguriertem Fixpreis.

    Zeigt die Ersparnis/Mehrkosten in Euro:
    - Positiv = Spot war günstiger als Fixpreis
    - Negativ = Fixpreis wäre günstiger gewesen
    """

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Spot vs Fixpreis",
            unit="€",
            icon="mdi:scale-balance",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float | None:
        savings = self.ctrl.spot_vs_fixed_savings
        if savings is None:
            return None
        return round(savings, 2)

    @property
    def icon(self) -> str:
        savings = self.ctrl.spot_vs_fixed_savings
        if savings is None:
            return "mdi:scale-balance"
        elif savings > 0:
            return "mdi:thumb-up"  # Spot war günstiger
        elif savings < 0:
            return "mdi:thumb-down"  # Fixpreis wäre günstiger
        return "mdi:scale-balance"

    @property
    def extra_state_attributes(self) -> dict:
        avg = self.ctrl.average_electricity_price_ct
        fixed = self.ctrl.fixed_price_compare_ct
        savings = self.ctrl.spot_vs_fixed_savings
        kwh = self.ctrl.tracked_grid_import_kwh

        attrs = {
            "fixpreis_ct": round(fixed, 2),
            "spot_durchschnitt_ct": round(avg, 2) if avg else None,
            "verbrauch_kwh": round(kwh, 2),
        }

        if avg and fixed and kwh > 0:
            # Was hätte Fixpreis gekostet?
            fixed_cost = kwh * (fixed / 100)
            spot_cost = self.ctrl.total_grid_import_cost
            attrs["fixpreis_kosten_eur"] = round(fixed_cost, 2)
            attrs["spot_kosten_eur"] = round(spot_cost, 2)
            attrs["differenz_pro_kwh_ct"] = round(fixed - avg, 2) if avg else None

            if savings and savings > 0:
                attrs["fazit"] = f"Spot {abs(savings):.2f}€ günstiger"
            elif savings and savings < 0:
                attrs["fazit"] = f"Fixpreis wäre {abs(savings):.2f}€ günstiger"
            else:
                attrs["fazit"] = "Etwa gleich"

        return attrs


# =============================================================================
# AUTO-CHARGE BATTERIE-SENSOREN
# =============================================================================


class AutoChargeReasonSensor(BaseEntity):
    """Zeigt den Grund warum geladen/nicht geladen wird."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ladegrund",
            icon="mdi:information-outline",
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> str:
        return self.ctrl.auto_charge_reason

    @property
    def icon(self) -> str:
        if self.ctrl.should_auto_charge:
            return "mdi:check-circle"
        return "mdi:close-circle"


class AutoChargePriceDiffSensor(BaseEntity):
    """Preisdifferenz zwischen billigster und teuerster Stunde heute."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Preisdifferenz Heute",
            unit="ct/kWh",
            icon="mdi:cash-multiple",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> float | None:
        diff = self.ctrl.epex_price_diff_today
        if diff is None:
            return None
        return round(diff, 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "schwelle_ct": self.ctrl.auto_charge_min_price_diff,
            "bedingung_erfuellt": self.ctrl._check_price_diff_condition(),
            "beschreibung": f"Min. {self.ctrl.auto_charge_min_price_diff} ct nötig",
        }


class AutoChargePVForecastSensor(BaseEntity):
    """PV Prognose für heute (für Auto-Charge Entscheidung)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "PV Prognose Heute",
            unit="kWh",
            icon="mdi:solar-power",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> float:
        forecast = self.ctrl.solcast_forecast_today if self.ctrl.has_solcast_integration else self.ctrl.pv_forecast
        return round(forecast, 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "schwelle_kwh": self.ctrl.auto_charge_pv_threshold,
            "bedingung_erfuellt": self.ctrl._check_pv_condition(),
            "quelle": "Solcast" if self.ctrl.has_solcast_integration else "Manuell",
            "beschreibung": f"Unter {self.ctrl.auto_charge_pv_threshold} kWh = laden",
        }


class AutoChargePriceQuantileSensor(BaseEntity):
    """Aktuelles Preis-Quantile (0=billigste, 1=teuerste Stunde)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Preis Quantile",
            icon="mdi:percent",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> float | None:
        if not self.ctrl.has_epex_integration:
            return None
        return round(self.ctrl.epex_quantile, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "schwelle": self.ctrl.auto_charge_price_quantile,
            "bedingung_erfuellt": self.ctrl._check_price_condition(),
            "preis_ct": round(self.ctrl.current_electricity_price * 100, 1),
            "beschreibung": f"0=billigste, 1=teuerste. Unter {self.ctrl.auto_charge_price_quantile} = günstig",
        }


class AutoChargeConditionsSensor(BaseEntity):
    """Zeigt welche Bedingungen erfüllt sind."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Bedingungen",
            icon="mdi:checkbox-marked-circle-outline",
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> str:
        """Zeigt Anzahl erfüllter Bedingungen."""
        conditions = [
            not self.ctrl.auto_charge_winter_only or self.ctrl.is_winter,
            self.ctrl._check_pv_condition(),
            self.ctrl._check_price_condition(),
            self.ctrl._check_soc_condition(),
            self.ctrl._check_price_diff_condition(),
        ]
        fulfilled = sum(conditions)
        return f"{fulfilled}/5 erfüllt"

    @property
    def icon(self) -> str:
        if self.ctrl.should_auto_charge:
            return "mdi:checkbox-marked-circle"
        return "mdi:checkbox-blank-circle-outline"

    @property
    def extra_state_attributes(self) -> dict:
        winter_ok = not self.ctrl.auto_charge_winter_only or self.ctrl.is_winter
        pv_ok = self.ctrl._check_pv_condition()
        price_ok = self.ctrl._check_price_condition()
        soc_ok = self.ctrl._check_soc_condition()
        diff_ok = self.ctrl._check_price_diff_condition()

        return {
            "winter": "✓ Winter" if winter_ok else "✗ Sommer",
            "pv_prognose": "✓ Niedrig" if pv_ok else "✗ Hoch",
            "preis": "✓ Günstig" if price_ok else "✗ Teuer",
            "batterie_soc": "✓ Niedrig" if soc_ok else "✗ Ausreichend",
            "preisdifferenz": "✓ Groß" if diff_ok else "✗ Klein",
            "alle_erfuellt": self.ctrl.should_auto_charge,
        }


class AutoChargeDiagnosticSensor(BaseEntity):
    """
    Diagnose-Sensor für Auto-Charge.

    Zeigt alle relevanten Informationen warum geladen/nicht geladen wird.
    """

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Auto-Charge Diagnose",
            icon="mdi:battery-charging-wireless",
            entity_category=EntityCategory.DIAGNOSTIC,
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> str:
        """Status-Text."""
        if not self.ctrl.auto_charge_enabled:
            return "Deaktiviert"
        if self.ctrl.auto_charge_winter_only and not self.ctrl.is_winter:
            return "Pausiert (Sommer)"
        if self.ctrl.should_auto_charge:
            return "Laden empfohlen"
        return "Kein Laden"

    @property
    def icon(self) -> str:
        if not self.ctrl.auto_charge_enabled:
            return "mdi:battery-off"
        if self.ctrl.should_auto_charge:
            return "mdi:battery-charging"
        return "mdi:battery-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Alle Diagnose-Informationen."""
        forecast = self.ctrl.solcast_forecast_today if self.ctrl.has_solcast_integration else self.ctrl.pv_forecast
        price_diff = self.ctrl.epex_price_diff_today

        # Berechne Ersparnis-Potenzial
        charge_cost = None
        potential_savings = None
        if price_diff and self.ctrl.auto_charge_power:
            charge_kwh = self.ctrl.auto_charge_power / 1000
            charge_cost = charge_kwh * self.ctrl.current_electricity_price
            potential_savings = charge_kwh * (price_diff / 100) * 0.85

        # Bedingungen mit Erklärung
        def check_with_reason(name: str, current, threshold, condition_met: bool, compare: str = "<") -> dict:
            if compare == "<":
                status = "✓" if condition_met else f"✗ ({current} >= {threshold})"
            elif compare == "<=":
                status = "✓" if condition_met else f"✗ ({current} > {threshold})"
            else:
                status = "✓" if condition_met else f"✗ ({current} < {threshold})"
            return {
                "erfuellt": condition_met,
                "aktuell": current,
                "schwelle": threshold,
                "status": status,
            }

        return {
            # === HAUPT-STATUS ===
            "empfehlung": "LADEN" if self.ctrl.should_auto_charge else "NICHT LADEN",
            "grund": self.ctrl.auto_charge_reason,

            # === EINSTELLUNGEN ===
            "einstellungen": {
                "aktiviert": self.ctrl.auto_charge_enabled,
                "nur_winter": self.ctrl.auto_charge_winter_only,
                "pv_schwelle_kwh": self.ctrl.auto_charge_pv_threshold,
                "preis_quantile_schwelle": self.ctrl.auto_charge_price_quantile,
                "min_soc_prozent": self.ctrl.auto_charge_min_soc,
                "ziel_soc_prozent": self.ctrl.auto_charge_target_soc,
                "min_preisdiff_ct": self.ctrl.auto_charge_min_price_diff,
                "ladeleistung_w": self.ctrl.auto_charge_power,
            },

            # === AKTUELLE WERTE ===
            "aktuell": {
                "ist_winter": self.ctrl.is_winter,
                "pv_prognose_kwh": round(forecast, 1),
                "preis_quantile": round(self.ctrl.epex_quantile, 2) if self.ctrl.has_epex_integration else None,
                "preis_ct": round(self.ctrl.current_electricity_price * 100, 1),
                "batterie_soc": round(self.ctrl.battery_soc, 0) if self.ctrl.battery_soc_entity else None,
                "preisdifferenz_ct": price_diff,
            },

            # === BEDINGUNGEN (warum wird/wird nicht geladen) ===
            "bedingung_winter": {
                "erfuellt": not self.ctrl.auto_charge_winter_only or self.ctrl.is_winter,
                "nur_winter_aktiv": self.ctrl.auto_charge_winter_only,
                "ist_winter": self.ctrl.is_winter,
                "status": "✓" if (not self.ctrl.auto_charge_winter_only or self.ctrl.is_winter) else "✗ (Sommer, nur Okt-März)",
            },
            "bedingung_pv": {
                "erfuellt": self.ctrl._check_pv_condition(),
                "aktuell_kwh": round(forecast, 1),
                "schwelle_kwh": self.ctrl.auto_charge_pv_threshold,
                "status": "✓" if self.ctrl._check_pv_condition() else f"✗ (Prognose {forecast:.1f} kWh zu hoch)",
            },
            "bedingung_preis": {
                "erfuellt": self.ctrl._check_price_condition(),
                "aktuell_quantile": round(self.ctrl.epex_quantile, 2) if self.ctrl.has_epex_integration else None,
                "schwelle_quantile": self.ctrl.auto_charge_price_quantile,
                "status": "✓" if self.ctrl._check_price_condition() else f"✗ (Quantile {self.ctrl.epex_quantile:.2f} zu hoch)",
            },
            "bedingung_soc": {
                "erfuellt": self.ctrl._check_soc_condition(),
                "aktuell_prozent": round(self.ctrl.battery_soc, 0) if self.ctrl.battery_soc_entity else None,
                "schwelle_prozent": self.ctrl.auto_charge_min_soc,
                "status": "✓" if self.ctrl._check_soc_condition() else f"✗ (SOC {self.ctrl.battery_soc:.0f}% bereits hoch genug)",
            },
            "bedingung_preisdiff": {
                "erfuellt": self.ctrl._check_price_diff_condition(),
                "aktuell_ct": price_diff,
                "schwelle_ct": self.ctrl.auto_charge_min_price_diff,
                "status": "✓" if self.ctrl._check_price_diff_condition() else f"✗ (Differenz {price_diff} ct zu gering)",
            },

            # === KOSTEN/ERSPARNIS ===
            "kostenrechnung": {
                "ladeleistung_kw": self.ctrl.auto_charge_power / 1000,
                "aktueller_preis_ct": round(self.ctrl.current_electricity_price * 100, 1),
                "kosten_1h_eur": round(charge_cost, 2) if charge_cost else None,
                "ersparnis_1h_eur": round(potential_savings, 2) if potential_savings else None,
                "effizienz_annahme": "85%",
            },

            # === STATISTIKEN ===
            "statistik": self.ctrl.auto_charge_stats,

            # === INTEGRATION STATUS ===
            "integrationen": {
                "epex_spot": self.ctrl.has_epex_integration,
                "solcast": self.ctrl.has_solcast_integration,
                "batterie_sensor": bool(self.ctrl.battery_soc_entity),
            },
        }


# =============================================================================
# BENCHMARK SENSORS
# =============================================================================

class BenchmarkAvgSensor(BaseEntity):
    """Reference average consumption for country/household size."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Benchmark Durchschnitt",
                         unit="kWh/Jahr", icon="mdi:home-group",
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        return self.ctrl.benchmark_avg_consumption_kwh


class BenchmarkOwnSensor(BaseEntity):
    """Own household consumption extrapolated to 1 year."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Benchmark Eigener Verbrauch",
                         unit="kWh/Jahr", icon="mdi:home-lightning-bolt",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        val = self.ctrl.benchmark_own_annual_consumption_kwh
        return round(val) if val is not None else None


class BenchmarkComparisonSensor(BaseEntity):
    """Percentage difference vs. average."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Benchmark Vergleich",
                         unit="%", icon="mdi:check-circle",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        val = self.ctrl.benchmark_consumption_vs_avg
        return round(val, 1) if val is not None else None

    @property
    def icon(self):
        val = self.ctrl.benchmark_consumption_vs_avg
        if val is not None and val <= 0:
            return "mdi:check-circle"
        return "mdi:alert"

    @property
    def extra_state_attributes(self):
        return {
            "country": self.ctrl.benchmark_country,
            "household_size": self.ctrl.benchmark_household_size,
            "reference_kwh": self.ctrl.benchmark_avg_consumption_kwh,
            "own_kwh": self.ctrl.benchmark_own_annual_consumption_kwh,
            "heatpump_excluded": bool(self.ctrl.benchmark_heatpump and self.ctrl.benchmark_heatpump_entity),
        }


class BenchmarkCO2Sensor(BaseEntity):
    """CO2 avoided by PV per year."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Benchmark CO2 Vermieden",
                         unit="kg/Jahr", icon="mdi:molecule-co2",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        val = self.ctrl.benchmark_co2_avoided_kg
        return round(val, 1) if val is not None else None


class BenchmarkScoreSensor(BaseEntity):
    """Efficiency score 0-100."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Benchmark Effizienz Score",
                         unit="Punkte", icon="mdi:star-circle",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        return self.ctrl.benchmark_efficiency_score

    @property
    def icon(self):
        score = self.ctrl.benchmark_efficiency_score
        if score is not None:
            if score >= 60:
                return "mdi:star-circle"
            if score >= 30:
                return "mdi:star-half-full"
        return "mdi:star-outline"


class BenchmarkRatingSensor(BaseEntity):
    """Text rating based on efficiency score."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Benchmark Bewertung",
                         icon="mdi:trophy",
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        return self.ctrl.benchmark_rating


class BenchmarkHeatpumpAvgSensor(BaseEntity):
    """Reference heat pump consumption."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Benchmark WP Durchschnitt",
                         unit="kWh/Jahr", icon="mdi:heat-pump",
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        return self.ctrl.benchmark_avg_heatpump_kwh


class BenchmarkHeatpumpOwnSensor(BaseEntity):
    """Own heat pump consumption extrapolated to 1 year."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Benchmark WP Verbrauch",
                         unit="kWh/Jahr", icon="mdi:heat-pump-outline",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        val = self.ctrl.benchmark_own_heatpump_kwh
        return round(val) if val is not None else None
