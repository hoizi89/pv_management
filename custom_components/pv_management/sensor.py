from __future__ import annotations

import logging
from dataclasses import dataclass
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
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import (
    DOMAIN, DATA_CTRL, CONF_NAME,
    CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
    CONF_ELECTRICITY_PRICE_ENTITY, CONF_FEED_IN_TARIFF_ENTITY,
    CONF_BATTERY_SOC_ENTITY, CONF_PV_POWER_ENTITY, CONF_PV_FORECAST_ENTITY,
    RECOMMENDATION_DARK_GREEN, RECOMMENDATION_GREEN, RECOMMENDATION_YELLOW, RECOMMENDATION_RED,
)

_LOGGER = logging.getLogger(__name__)

# Device types for grouping sensors
DEVICE_MAIN = "main"
DEVICE_BATTERY = "battery"
DEVICE_PRICES = "prices"
DEVICE_BENCHMARK = "benchmark"
DEVICE_PV_STRINGS = "pv_strings"
DEVICE_FORECAST = "forecast"


def get_device_info(name: str, device_type: str = DEVICE_MAIN) -> DeviceInfo:
    """Create DeviceInfo for different device types."""
    if device_type == DEVICE_BATTERY:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_battery")},
            name=f"{name} Battery",
            manufacturer="Custom",
            model="PV Management - Battery",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_PRICES:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_prices")},
            name=f"{name} Electricity Prices",
            manufacturer="Custom",
            model="PV Management - Electricity Prices",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_BENCHMARK:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_benchmark")},
            name=f"{name} Energy Benchmark",
            manufacturer="Custom",
            model="PV Management - Energy Benchmark",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_PV_STRINGS:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_pv_strings")},
            name=f"{name} PV Strings",
            manufacturer="Custom",
            model="PV Management - PV Strings",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_FORECAST:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_forecast")},
            name=f"{name} Load Forecast",
            manufacturer="Custom",
            model="PV Management - Load Forecast",
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
    """Set up sensors."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Management")

    entities = [
        # === RECOMMENDATION (most important for daily use) ===
        ConsumptionRecommendationSensor(ctrl, name),
        NextCheapHourSensor(ctrl, name),

        # === AMORTISATION (main purpose) ===
        AmortisationPercentSensor(ctrl, name),
        TotalSavingsSensor(ctrl, name),  # This one stores persistently!
        RemainingCostSensor(ctrl, name),
        StatusSensor(ctrl, name),
        EstimatedPaybackDateSensor(ctrl, name),
        EstimatedRemainingDaysSensor(ctrl, name),

        # === ENERGY (ratio sensors always visible) ===
        SelfConsumptionRatioSensor(ctrl, name),
        AutarkyRateSensor(ctrl, name),

        # === STATISTICS ===
        AverageDailySavingsSensor(ctrl, name),
        AverageMonthlySavingsSensor(ctrl, name),
        AverageYearlySavingsSensor(ctrl, name),
        DaysSinceInstallationSensor(ctrl, name),

        # === ENVIRONMENT ===
        CO2SavedSensor(ctrl, name),

        # === DIAGNOSTIC ===
        CurrentElectricityPriceSensor(ctrl, name),
        CurrentFeedInTariffSensor(ctrl, name),
        PVProductionSensor(ctrl, name),
        InstallationCostSensor(ctrl, name),
        ConfigurationDiagnosticSensor(ctrl, name, entry),

        # === DAILY ELECTRICITY COSTS ===
        DailyNetElectricityCostSensor(ctrl, name),

        # === ELECTRICITY PRICE AVERAGE ===
        DailyAveragePriceSensor(ctrl, name),
        MonthlyAveragePriceSensor(ctrl, name),
        AverageElectricityPriceSensor(ctrl, name),
        TotalGridImportCostSensor(ctrl, name),
        SpotVsFixedPriceSensor(ctrl, name),  # Spot vs fixed price comparison

        # === AUTO-CHARGE BATTERY ===
        AutoChargeReasonSensor(ctrl, name),
        AutoChargePriceDiffSensor(ctrl, name),
        AutoChargePVForecastSensor(ctrl, name),
        AutoChargePriceQuantileSensor(ctrl, name),
        AutoChargeConditionsSensor(ctrl, name),
        AutoChargeDiagnosticSensor(ctrl, name),

    ]

    # === PV SURPLUS (live W) — only if house power sensor is configured ===
    # Without house_power these sensors are permanently "unavailable",
    # so we don't create them at all instead of cluttering the device.
    if ctrl.house_power_entity:
        entities.extend([
            PVSurplusValueSensor(ctrl, name),
            PVPeakValueSensor(ctrl, name),
        ])

    # === EXPORT-DEPENDENT SENSORS (only if grid export sensor configured) ===
    if ctrl.grid_export_entity:
        entities.extend([
            SelfConsumptionSensor(ctrl, name),
            FeedInSensor(ctrl, name),
            SavingsSelfConsumptionSensor(ctrl, name),
            EarningsFeedInSensor(ctrl, name),
            DailyFeedInSensor(ctrl, name),
        ])

    # === GRID-IMPORT-DEPENDENT SENSORS ===
    if ctrl.grid_import_entity:
        entities.append(DailyGridImportSensor(ctrl, name))

    # === BENCHMARK (optional) ===
    if ctrl.benchmark_enabled:
        entities.extend([
            BenchmarkAvgSensor(ctrl, name),
            BenchmarkOwnSensor(ctrl, name),
            BenchmarkComparisonSensor(ctrl, name),
            BenchmarkCO2Sensor(ctrl, name),
            BenchmarkGridImportSensor(ctrl, name),
            BenchmarkAnnualPVSensor(ctrl, name),
            BenchmarkScoreSensor(ctrl, name),
            BenchmarkRatingSensor(ctrl, name),
        ])
        if ctrl.pv_strings:
            entities.append(BenchmarkSpecificYieldSensor(ctrl, name))
        if ctrl.benchmark_heatpump:
            entities.extend([
                BenchmarkHeatpumpAvgSensor(ctrl, name),
                BenchmarkHeatpumpOwnSensor(ctrl, name),
                BenchmarkHeatpumpComparisonSensor(ctrl, name),
                BenchmarkHouseholdSensor(ctrl, name),
            ])

    # === LOAD FORECAST (optional, 24x7 profile) ===
    if ctrl.forecast_enabled and ctrl.consumption_entity:
        entities.extend([
            LoadForecast1hSensor(ctrl, name),
            LoadForecast6hSensor(ctrl, name),
            LoadForecastTodayRestSensor(ctrl, name),
            LoadForecastTomorrowSensor(ctrl, name),
            LoadForecast24hSensor(ctrl, name),
        ])

    # === PV STRINGS (optional) ===
    if ctrl.pv_strings:
        entities.append(TotalDailyProductionSensor(ctrl, name))
        for i, (string_name, string_entity, power_entity, installed_kwp) in enumerate(ctrl.pv_strings):
            entities.extend([
                PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "production"),
                PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "daily"),
                PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "percentage"),
            ])
            if power_entity:
                entities.extend([
                    PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "peak"),
                ])
            if installed_kwp > 0 or power_entity:
                entities.append(PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "specific_yield"))
            if power_entity and installed_kwp > 0:
                entities.append(PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "performance_ratio"))
        if any(p for _, _, p, _ in ctrl.pv_strings):
            entities.append(TotalPeakSensor(ctrl, name))

    async_add_entities(entities)


class BaseEntity(SensorEntity):
    """Base class for all sensors."""

    _attr_should_poll = False
    _attr_has_entity_name = True

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
        raw_key = key.lower().replace(' ', '_').replace('/', '_')
        # translation_key must be ASCII [a-z0-9-_] for hassfest
        ascii_key = raw_key.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss').replace('ø', 'avg')
        self._attr_translation_key = ascii_key
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        # unique_id keeps original key for backwards compatibility
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_{raw_key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_state_class = state_class
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_device_info = get_device_info(name, device_type)
        self._removed = False

    @property
    def available(self) -> bool:
        """Sensor is only available after stored data has been restored."""
        return getattr(self.ctrl, "_restored", True)

    async def async_added_to_hass(self):
        self._removed = False
        self.ctrl.register_entity_listener(self._on_ctrl_update)

    async def async_will_remove_from_hass(self):
        """Remove listener when entity is unloaded."""
        self._removed = True
        self.ctrl.unregister_entity_listener(self._on_ctrl_update)

    @callback
    def _on_ctrl_update(self):
        if not self._removed and self.hass:
            self.async_write_ha_state()


class PVStringSensor(BaseEntity):
    """Generic sensor for PV string comparison."""

    def __init__(self, ctrl, name: str, string_index: int, string_name: str, entity_id: str, power_entity_id: str | None, installed_kwp: float, sensor_type: str):
        self._string_entity_id = entity_id
        self._power_entity_id = power_entity_id
        self._installed_kwp = installed_kwp
        self._sensor_type = sensor_type

        uid_suffix_map = {
            "production": "Produktion",
            "daily": "Tagesproduktion",
            "peak": "Peak",
            "percentage": "Anteil",
            "specific_yield": "Spez. Ertrag",
            "performance_ratio": "Performance Ratio",
        }
        props_map = {
            "production": ("kWh", "mdi:solar-panel", SensorStateClass.TOTAL_INCREASING),
            "daily": ("kWh/Tag", "mdi:weather-sunny", SensorStateClass.MEASUREMENT),
            "peak": ("kW", "mdi:solar-power-variant", SensorStateClass.MEASUREMENT),
            "percentage": ("%", "mdi:chart-pie", SensorStateClass.MEASUREMENT),
            "specific_yield": ("kWh/kWp", "mdi:solar-power-variant-outline", SensorStateClass.MEASUREMENT),
            "performance_ratio": ("%", "mdi:gauge", SensorStateClass.MEASUREMENT),
        }
        uid_suffix = uid_suffix_map[sensor_type]
        unit, icon, state_class = props_map[sensor_type]
        key = f"{string_name} {uid_suffix}"

        super().__init__(ctrl, name, key, unit=unit, icon=icon, state_class=state_class, device_type=DEVICE_PV_STRINGS)
        # PVStringSensor uses dynamic user-configured names, so disable translation_key
        self._attr_translation_key = None
        self._attr_name = key

    @property
    def native_value(self):
        if self._sensor_type == "production":
            val = self.ctrl.get_string_production_kwh(self._string_entity_id)
            return round(val, 2) if val else 0.0
        elif self._sensor_type == "daily":
            val = self.ctrl.get_string_daily_kwh(self._string_entity_id)
            return round(val, 2) if val is not None else None
        elif self._sensor_type == "peak":
            val = self.ctrl.get_string_peak_kw(self._power_entity_id)
            return val
        elif self._sensor_type == "specific_yield":
            kwp = self._installed_kwp
            if kwp <= 0 and self._power_entity_id:
                peak_kw = self.ctrl.get_string_peak_kw(self._power_entity_id)
                kwp = peak_kw if peak_kw else 0.0
            return self.ctrl.get_string_specific_yield(self._string_entity_id, kwp)
        elif self._sensor_type == "performance_ratio":
            return self.ctrl.get_string_performance_ratio(self._power_entity_id, self._installed_kwp)
        else:  # percentage
            val = self.ctrl.get_string_percentage(self._string_entity_id)
            return round(val, 1) if val is not None else None


class TotalDailyProductionSensor(BaseEntity):
    """Average daily production across all PV strings."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Gesamt Tagesproduktion", unit="kWh/Tag", icon="mdi:weather-sunny",
                         state_class=SensorStateClass.MEASUREMENT, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        return self.ctrl.get_total_daily_production_kwh()


class TotalPeakSensor(BaseEntity):
    """Total peak across all PV strings."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Gesamt Peak", unit="kW", icon="mdi:solar-power-variant",
                         state_class=SensorStateClass.MEASUREMENT, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        return self.ctrl.get_total_peak_kw()


# =============================================================================
# MAIN SENSORS
# =============================================================================


class AmortisationPercentSensor(BaseEntity):
    """Amortisation percentage - main indicator."""

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


@dataclass
class _PersistedTrackingData(ExtraStoredData):
    """Kumulative Tracking-Daten, die unabhängig vom Entity-State
    (auch bei "unavailable") von Home Assistant persistiert werden."""

    data: dict

    def as_dict(self) -> dict:
        return self.data


class TotalSavingsSensor(BaseEntity, RestoreEntity):
    """
    Total savings in Euro.

    IMPORTANT: This sensor stores the incrementally calculated values
    persistently so they survive restarts!
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
        """Restore saved state."""
        await super().async_added_to_hass()

        # Issue #9: Kumulative Werte aus extra_restore_state_data laden.
        # extra_state_attributes eines "unavailable" Sensors werden von HA
        # NICHT persistiert — extra_restore_state_data dagegen schon. Damit
        # überleben die Werte den Reboot auch wenn der Sensor durch die
        # _restored-Race kurzzeitig unavailable war.
        attrs: dict | None = None
        last_extra = await self.async_get_last_extra_data()
        if last_extra is not None:
            stored = last_extra.as_dict()
            if isinstance(stored, dict) and stored.get("tracked_self_consumption_kwh") is not None:
                attrs = stored

        # Fallback: attributbasierter Restore (Migration von Versionen < v4.0.8)
        if attrs is None:
            last_state = await self.async_get_last_state()
            if last_state and (last_state.attributes or {}).get("tracked_self_consumption_kwh") is not None:
                attrs = dict(last_state.attributes or {})

        if attrs is not None:

            # Explicit float conversion (HA sometimes stores as string)
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
                # Electricity price tracking
                "tracked_grid_import_kwh": safe_float(attrs.get("tracked_grid_import_kwh")),
                "total_grid_import_cost": safe_float(attrs.get("total_grid_import_cost")),
                # Auto-Charge statistics
                "auto_charge_count": safe_float(attrs.get("auto_charge_count")),
                "auto_charge_total_hours": safe_float(attrs.get("auto_charge_total_hours")),
                "auto_charge_total_kwh": safe_float(attrs.get("auto_charge_total_kwh")),
                "auto_charge_estimated_savings": safe_float(attrs.get("auto_charge_estimated_savings")),
                # Heat pump delta tracking
                "tracked_wp_kwh": safe_float(attrs.get("tracked_wp_kwh")),
                "wp_first_seen_date": attrs.get("wp_first_seen_date"),
                # PV string delta tracking
                "string_tracked_kwh": attrs.get("string_tracked_kwh", {}),
                "string_first_seen_date": attrs.get("string_first_seen_date"),
                "string_peak_w": attrs.get("string_peak_w", {}),
                # Daily tracking
                "daily_grid_import_kwh": safe_float(attrs.get("daily_grid_import_kwh")),
                "daily_grid_import_cost": safe_float(attrs.get("daily_grid_import_cost")),
                "daily_feed_in_earnings": safe_float(attrs.get("daily_feed_in_earnings")),
                "daily_feed_in_kwh": safe_float(attrs.get("daily_feed_in_kwh")),
                "daily_reset_date": attrs.get("daily_reset_date"),
                # Monthly tracking
                "monthly_grid_import_kwh": safe_float(attrs.get("monthly_grid_import_kwh")),
                "monthly_grid_import_cost": safe_float(attrs.get("monthly_grid_import_cost")),
                "monthly_reset_month": attrs.get("monthly_reset_month"),
                "monthly_reset_year": attrs.get("monthly_reset_year"),
                # Benchmark Snapshot
                "benchmark_start_date": attrs.get("benchmark_start_date"),
                "benchmark_start_self_consumption": safe_float(attrs.get("benchmark_start_self_consumption")),
                "benchmark_start_grid_import": safe_float(attrs.get("benchmark_start_grid_import")),
                "benchmark_start_feed_in": safe_float(attrs.get("benchmark_start_feed_in")),
                "monthly_buckets": attrs.get("monthly_buckets", {}),
                "monthly_bucket_month": attrs.get("monthly_bucket_month"),
            }

            _LOGGER.info(
                "TotalSavingsSensor: Restore data: self=%.2f kWh, feed=%.2f kWh, savings=%.2f€, earnings=%.2f€",
                restore_data["total_self_consumption_kwh"],
                restore_data["total_feed_in_kwh"],
                restore_data["accumulated_savings_self"],
                restore_data["accumulated_earnings_feed"],
            )

            self.ctrl.restore_state(restore_data)
            _LOGGER.info("TotalSavingsSensor: State restored")

            # Explicit state update after restore
            self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self.ctrl.total_savings, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """
        Store all important values as attributes.
        These are restored by RestoreEntity.
        """
        return {
            "savings_self_consumption": f"{self.ctrl.savings_self_consumption:.2f}€",
            "earnings_feed_in": f"{self.ctrl.earnings_feed_in:.2f}€",
            # Incrementally calculated values (will be restored)
            "tracked_self_consumption_kwh": round(self.ctrl._total_self_consumption_kwh, 4),
            "tracked_feed_in_kwh": round(self.ctrl._total_feed_in_kwh, 4),
            "accumulated_savings_self": round(self.ctrl._accumulated_savings_self, 4),
            "accumulated_earnings_feed": round(self.ctrl._accumulated_earnings_feed, 4),
            "first_seen_date": self.ctrl._first_seen_date.isoformat() if self.ctrl._first_seen_date else None,
            # Electricity price tracking (will be restored)
            "tracked_grid_import_kwh": round(self.ctrl._tracked_grid_import_kwh, 4),
            "total_grid_import_cost": round(self.ctrl._total_grid_import_cost, 4),
            # Auto-Charge statistics (will be restored)
            "auto_charge_count": self.ctrl._auto_charge_count,
            "auto_charge_total_hours": round(self.ctrl._auto_charge_total_hours, 2),
            "auto_charge_total_kwh": round(self.ctrl._auto_charge_total_kwh, 2),
            "auto_charge_estimated_savings": round(self.ctrl._auto_charge_estimated_savings, 2),
            # Heat pump delta tracking (persistent)
            "tracked_wp_kwh": round(self.ctrl._tracked_wp_kwh, 4),
            "wp_first_seen_date": self.ctrl._wp_first_seen_date.isoformat() if self.ctrl._wp_first_seen_date else None,
            # PV string delta tracking (persistent)
            "string_tracked_kwh": self.ctrl._string_tracked_kwh,
            "string_first_seen_date": self.ctrl._string_first_seen_date.isoformat() if self.ctrl._string_first_seen_date else None,
            "string_peak_w": self.ctrl._string_peak_w,
            # Daily tracking
            "daily_grid_import_kwh": round(self.ctrl._daily_grid_import_kwh, 4),
            "daily_grid_import_cost": round(self.ctrl._daily_grid_import_cost, 4),
            "daily_feed_in_earnings": round(self.ctrl._daily_feed_in_earnings, 4),
            "daily_feed_in_kwh": round(self.ctrl._daily_feed_in_kwh, 4),
            "daily_reset_date": date.today().isoformat(),
            # Monthly tracking
            "monthly_grid_import_kwh": round(self.ctrl._monthly_grid_import_kwh, 4),
            "monthly_grid_import_cost": round(self.ctrl._monthly_grid_import_cost, 4),
            "monthly_reset_month": date.today().month,
            "monthly_reset_year": date.today().year,
            # Benchmark Snapshot
            "benchmark_start_date": self.ctrl._benchmark_start_date.isoformat() if self.ctrl._benchmark_start_date else None,
            "benchmark_start_self_consumption": round(self.ctrl._benchmark_start_self_consumption, 4),
            "benchmark_start_grid_import": round(self.ctrl._benchmark_start_grid_import, 4),
            "benchmark_start_feed_in": round(self.ctrl._benchmark_start_feed_in, 4),
            "monthly_buckets": {str(k): v for k, v in self.ctrl._monthly_buckets.items()},
            "monthly_bucket_month": self.ctrl._monthly_bucket_month,
            # Info
            "calculation_method": "incremental (dynamic prices supported)",
        }

    @property
    def extra_restore_state_data(self) -> _PersistedTrackingData:
        """Persistiert alle kumulativen Werte über Reboots hinweg (Issue #9).

        Anders als extra_state_attributes wird extra_restore_state_data von
        HA auch dann gespeichert, wenn die Entity gerade "unavailable" ist.
        """
        return _PersistedTrackingData(dict(self.extra_state_attributes))


class RemainingCostSensor(BaseEntity):
    """Remaining amount until amortisation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Restbetrag",
            unit="€",
            icon="mdi:cash-minus",
            # state_class must be None for device_class=MONETARY (not MEASUREMENT)
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
    """Status text (e.g. '45.2% amortised' or 'Amortised!')."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Status",
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
# ENERGY SENSORS
# =============================================================================


class SelfConsumptionSensor(BaseEntity):
    """Self consumption in kWh (incrementally calculated)."""

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
    """Grid feed-in in kWh (incrementally calculated)."""

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
    """PV production in kWh (mirrored from input sensor)."""

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
# FINANCIAL SENSORS
# =============================================================================


class SavingsSelfConsumptionSensor(BaseEntity):
    """Savings from self consumption (incrementally calculated)."""

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
    """Earnings from feed-in (incrementally calculated)."""

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
# EFFICIENCY SENSORS
# =============================================================================


class SelfConsumptionRatioSensor(BaseEntity):
    """Self consumption ratio in percent."""

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
            "description": "Share of PV production that is self consumed",
        }


class AutarkyRateSensor(BaseEntity):
    """Autarky rate in percent."""

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
            "description": "Share of consumption covered by PV",
            "note": "Requires configured consumption sensor" if self.ctrl.autarky_rate is None else None,
        }


# =============================================================================
# STATISTICS SENSORS
# =============================================================================


class AverageDailySavingsSensor(BaseEntity):
    """Average daily savings."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Ersparnis/Tag",
            unit="€/Tag",
            icon="mdi:calendar-today",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.average_daily_savings, 2)


class AverageMonthlySavingsSensor(BaseEntity):
    """Average monthly savings."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Ersparnis/Monat",
            unit="€/Monat",
            icon="mdi:calendar-month",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.average_monthly_savings, 2)


class AverageYearlySavingsSensor(BaseEntity):
    """Average yearly savings."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Ersparnis/Jahr",
            unit="€/Jahr",
            icon="mdi:calendar",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.average_yearly_savings, 2)


class DaysSinceInstallationSensor(BaseEntity):
    """Days since installation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Tage",
            unit="Tage",
            icon="mdi:calendar-clock",
            state_class=SensorStateClass.TOTAL_INCREASING,
        )

    @property
    def native_value(self) -> int:
        return self.ctrl.days_since_installation


# =============================================================================
# FORECAST SENSORS
# =============================================================================


class EstimatedRemainingDaysSensor(BaseEntity):
    """Estimated remaining days until amortisation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Restlaufzeit",
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
            return {"status": "Calculation not possible"}

        years = remaining // 365
        months = (remaining % 365) // 30
        days = remaining % 30

        parts = []
        if years > 0:
            parts.append(f"{years} year{'s' if years > 1 else ''}")
        if months > 0:
            parts.append(f"{months} month{'s' if months > 1 else ''}")
        if days > 0 or not parts:
            parts.append(f"{days} day{'s' if days != 1 else ''}")

        return {
            "formatted": ", ".join(parts),
            "years": years,
            "months": months,
            "days": days,
        }


class EstimatedPaybackDateSensor(BaseEntity):
    """Estimated amortisation date."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Datum",
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
# ENVIRONMENT SENSORS
# =============================================================================


class CO2SavedSensor(BaseEntity):
    """CO2 emissions saved."""

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
# CONFIGURATION SENSORS (DIAGNOSTIC)
# =============================================================================


class CurrentElectricityPriceSensor(BaseEntity):
    """Current electricity price."""

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
    """Current feed-in tariff."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Preis Einspeisung",
            unit="€/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_type=DEVICE_PRICES,
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
    """Installation cost of the PV system."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Kosten",
            unit="€",
            icon="mdi:cash",
            device_class=SensorDeviceClass.MONETARY,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.installation_cost, 2)


class ConfigurationDiagnosticSensor(BaseEntity):
    """Diagnostic sensor showing all configured sensors and their status."""

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
        """Get status of an entity."""
        if not entity_id:
            return {"configured": False, "entity_id": None, "state": None, "status": "not configured"}

        state = self.hass.states.get(entity_id)
        if state is None:
            return {
                "configured": True,
                "entity_id": entity_id,
                "state": None,
                "status": "not found",
            }
        elif state.state in ("unavailable", "unknown"):
            return {
                "configured": True,
                "entity_id": entity_id,
                "state": state.state,
                "status": "unavailable",
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
        """Shows overall configuration status."""
        issues = 0

        # Check all configured sensors
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
            return f"{issues} issue{'s' if issues > 1 else ''}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Shows all configured sensors and their status."""
        pv_status = self._get_entity_status(self.ctrl.pv_production_entity)
        export_status = self._get_entity_status(self.ctrl.grid_export_entity)
        import_status = self._get_entity_status(self.ctrl.grid_import_entity)
        consumption_status = self._get_entity_status(self.ctrl.consumption_entity)
        price_status = self._get_entity_status(self.ctrl.electricity_price_entity)
        tariff_status = self._get_entity_status(self.ctrl.feed_in_tariff_entity)

        return {
            # === SENSOR CONFIGURATION ===
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

            # Price sensors (optional)
            "electricity_price_entity": price_status["entity_id"],
            "electricity_price_status": price_status["status"],
            "electricity_price_value": price_status["state"],
            "electricity_price_source": "sensor" if self.ctrl.electricity_price_entity else "config",

            "feed_in_tariff_entity": tariff_status["entity_id"],
            "feed_in_tariff_status": tariff_status["status"],
            "feed_in_tariff_value": tariff_status["state"],
            "feed_in_tariff_source": "sensor" if self.ctrl.feed_in_tariff_entity else "config",

            # === ACCUMULATED VALUES (these are stored) ===
            "tracked_self_consumption_kwh": round(self.ctrl._total_self_consumption_kwh, 4),
            "tracked_feed_in_kwh": round(self.ctrl._total_feed_in_kwh, 4),
            "accumulated_savings_self_eur": round(self.ctrl._accumulated_savings_self, 4),
            "accumulated_earnings_feed_eur": round(self.ctrl._accumulated_earnings_feed, 4),

            # === LAST SENSOR VALUES (for delta calculation) ===
            "last_pv_production_kwh": self.ctrl._last_pv_production_kwh,
            "last_grid_export_kwh": self.ctrl._last_grid_export_kwh,

            # === CURRENT SENSOR VALUES ===
            "current_pv_production_kwh": round(self.ctrl._pv_production_kwh, 4),
            "current_grid_export_kwh": round(self.ctrl._grid_export_kwh, 4),
            "current_grid_import_kwh": round(self.ctrl._grid_import_kwh, 4),
            "current_consumption_kwh": round(self.ctrl._consumption_kwh, 4),

            # === CALCULATED VALUES ===
            "total_self_consumption_kwh": round(self.ctrl.self_consumption_kwh, 4),
            "total_feed_in_kwh": round(self.ctrl.feed_in_kwh, 4),
            "total_savings_eur": round(self.ctrl.total_savings, 4),

            # === PRICES ===
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
        """Icon based on status."""
        if self.native_value == "OK":
            return "mdi:check-circle"
        else:
            return "mdi:alert-circle"


# =============================================================================
# RECOMMENDATION SENSOR (TRAFFIC LIGHT)
# =============================================================================


class ConsumptionRecommendationSensor(BaseEntity):
    """
    Electricity consumption recommendation as traffic light.

    Shows whether now is a good time to consume electricity.
    Based on: PV power, battery, electricity price, time of day, forecast.
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
        """Shows recommendation text."""
        return self.ctrl.consumption_recommendation_text

    @property
    def icon(self) -> str:
        """Icon as traffic light color."""
        rec = self.ctrl.consumption_recommendation
        if rec == RECOMMENDATION_DARK_GREEN:
            return "mdi:checkbox-marked-circle-outline"  # Double check mark
        elif rec == RECOMMENDATION_GREEN:
            return "mdi:checkbox-marked-circle"  # Green check mark
        elif rec == RECOMMENDATION_RED:
            return "mdi:close-circle"  # Red X
        else:
            return "mdi:minus-circle"  # Yellow dash

    def _calculate_score_breakdown(self) -> dict[str, Any]:
        """Calculate detailed score breakdown."""
        from datetime import datetime

        breakdown = {}
        total_score = 0
        reasons_positive = []
        reasons_negative = []

        # === PV power (based on peak power, with winter base load deduction) ===
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
            reasons_positive.append("Very high PV")
        elif pv_power >= pv_high:
            pv_score = 2
            reasons_positive.append("High PV")
        elif pv_power >= pv_moderate:
            pv_score = 1
            reasons_positive.append("Some PV")
        elif pv_power < pv_low:
            pv_score = -1
            reasons_negative.append("Barely any PV")
        else:
            pv_score = 0

        breakdown["pv_power"] = {
            "value": f"{pv_power_raw:.0f} W",
            "effective": f"{pv_power:.0f} W" if is_winter and winter_base > 0 else None,
            "winter_base_load": f"{winter_base:.0f} W" if is_winter and winter_base > 0 else None,
            "percent": f"{pv_percent:.0f}%",
            "peak_power": f"{pv_peak:.0f} W",
            "threshold_very_high": f"{pv_very_high:.0f} W (60%)",
            "threshold_high": f"{pv_high:.0f} W (30%)",
            "threshold_moderate": f"{pv_moderate:.0f} W (10%)",
            "points": pv_score,
            "rating": "++++" if pv_score >= 4 else "++" if pv_score >= 2 else "+" if pv_score >= 1 else "--" if pv_score < 0 else "o"
        }
        total_score += pv_score

        # === Battery ===
        if self.ctrl.battery_soc_entity:
            battery_soc = self.ctrl.battery_soc
            soc_high = self.ctrl.battery_soc_high
            soc_low = self.ctrl.battery_soc_low

            if battery_soc >= soc_high:
                bat_score = 2
                reasons_positive.append(f"Battery full ({battery_soc:.0f}%)")
            elif battery_soc <= soc_low:
                bat_score = -2
                reasons_negative.append(f"Battery empty ({battery_soc:.0f}%)")
            else:
                bat_score = 0

            breakdown["battery"] = {
                "value": f"{battery_soc:.0f}%",
                "threshold_full": f"{soc_high:.0f}%",
                "threshold_empty": f"{soc_low:.0f}%",
                "points": bat_score,
                "rating": "++" if bat_score >= 2 else "--" if bat_score <= -2 else "o"
            }
            total_score += bat_score

        # === Electricity price (EPEX quantile has priority) ===
        if self.ctrl.epex_quantile_entity and 0 <= self.ctrl.epex_quantile <= 1:
            quantile = self.ctrl.epex_quantile
            epex_price = self.ctrl.epex_price

            if quantile <= 0.2:
                price_score = 3
                reasons_positive.append(f"EPEX top 20% cheap (Q={quantile:.2f})")
            elif quantile <= 0.4:
                price_score = 1
                reasons_positive.append(f"EPEX cheap (Q={quantile:.2f})")
            elif quantile >= 0.8:
                price_score = -3
                reasons_negative.append(f"EPEX top 20% expensive (Q={quantile:.2f})")
            elif quantile >= 0.6:
                price_score = -1
                reasons_negative.append(f"EPEX expensive (Q={quantile:.2f})")
            else:
                price_score = 0

            breakdown["electricity_price"] = {
                "value": f"{epex_price:.4f} €/kWh",
                "source": "EPEX Spot",
                "quantile": f"{quantile:.2f}",
                "quantile_explanation": "0=cheapest, 1=most expensive price of the day",
                "rating_range": "≤0.2: +++, ≤0.4: +, ≥0.6: -, ≥0.8: ---",
                "points": price_score,
                "rating": "+++" if price_score >= 3 else "++" if price_score >= 2 else "+" if price_score >= 1 else "---" if price_score <= -3 else "--" if price_score <= -2 else "-" if price_score <= -1 else "o"
            }
        else:
            # Fallback: Absolute price
            price = self.ctrl.current_electricity_price
            price_low = self.ctrl.price_low_threshold
            price_high = self.ctrl.price_high_threshold

            if price <= price_low:
                price_score = 2
                reasons_positive.append(f"Cheap electricity ({price:.2f}€/kWh)")
            elif price >= price_high:
                price_score = -2
                reasons_negative.append(f"Expensive electricity ({price:.2f}€/kWh)")
            else:
                price_score = 0

            breakdown["electricity_price"] = {
                "value": f"{price:.4f} €/kWh",
                "source": self.ctrl.electricity_price_source,
                "threshold_cheap": f"{price_low:.2f} €/kWh",
                "threshold_expensive": f"{price_high:.2f} €/kWh",
                "points": price_score,
                "rating": "++" if price_score >= 2 else "--" if price_score <= -2 else "o"
            }
        total_score += price_score

        # === Time of day ===
        hour = datetime.now().hour

        if 10 <= hour <= 15:
            time_score = 1
            reasons_positive.append(f"Good time of day ({hour}:00)")
        elif hour < 6 or hour > 21:
            time_score = -1
            reasons_negative.append(f"Night time ({hour}:00)")
        else:
            time_score = 0

        breakdown["time_of_day"] = {
            "value": f"{hour}:00",
            "peak_hours": "10:00 - 15:00",
            "points": time_score,
            "rating": "+" if time_score >= 1 else "-" if time_score <= -1 else "o"
        }
        total_score += time_score

        # === PV forecast (Solcast has priority) ===
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
                reasons_positive.append(f"Good PV forecast ({forecast:.1f} kWh, {forecast_source})")
            elif forecast < 3:
                forecast_score = -1
                reasons_negative.append(f"Poor PV forecast ({forecast:.1f} kWh, {forecast_source})")
            else:
                forecast_score = 0

            breakdown["pv_forecast"] = {
                "value": f"{forecast:.1f} kWh",
                "source": forecast_source,
                "threshold_good": "≥10 kWh",
                "threshold_bad": "<3 kWh",
                "points": forecast_score,
                "rating": "+" if forecast_score >= 1 else "-" if forecast_score <= -1 else "o"
            }
            total_score += forecast_score

        # === Summary ===
        if total_score >= 5:
            bereich = "dark green (≥5)"
        elif total_score >= 3:
            bereich = "green (≥3)"
        elif total_score <= -2:
            bereich = "red (≤-2)"
        else:
            bereich = "yellow"

        breakdown["total"] = {
            "points": total_score,
            "range": bereich,
        }

        return {
            "breakdown": breakdown,
            "reasons_positive": reasons_positive,
            "reasons_negative": reasons_negative,
            "total_score": total_score,
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Detailed recommendation info with score breakdown."""
        rec = self.ctrl.consumption_recommendation
        analysis = self._calculate_score_breakdown()

        attrs = {
            # Main info
            "traffic_light": rec,
            "color": self.ctrl.consumption_recommendation_color,
            "total_score": analysis["total_score"],
            "rating": self._get_score_explanation(analysis["total_score"]),

            # === For multi-line card display ===
            "status": self.ctrl.recommendation_status,  # "Unfavorable", "Good timing", etc.
            "reasons": self.ctrl.recommendation_reasons,  # All reasons combined
            "tip": self.ctrl.best_opportunity_text,  # Best tip (PV or price)

            # === Separate info for flexible card layouts ===
            "pv_info": self.ctrl.pv_info,  # "no PV", "barely PV", "high PV", etc.
            "battery_info": self.ctrl.akku_info,  # "Battery full", "Battery empty", or empty
            "price_info": self.ctrl.preis_info,  # "Electricity cheap", "Electricity expensive", or empty
            "pv_tip": self.ctrl.pv_tipp,  # "In 2h approx. 5 kW PV (12:00)" or empty
            "price_tip": self.ctrl.preis_tipp,  # "In 3h cheap (14:00, 12ct)"

            # Reasons (for simple display)
            "reasons_positive": ", ".join(analysis["reasons_positive"]) if analysis["reasons_positive"] else "None",
            "reasons_negative": ", ".join(analysis["reasons_negative"]) if analysis["reasons_negative"] else "None",

            # Detailed breakdown
            "score_details": analysis["breakdown"],

            # Configuration (for reference)
            "config": {
                "pv_peak_power": f"{self.ctrl.pv_peak_power:.0f} W",
                "pv_very_high": f"{self.ctrl.pv_peak_power * 0.6:.0f} W (60%)",
                "pv_high": f"{self.ctrl.pv_peak_power * 0.3:.0f} W (30%)",
                "price_cheap": f"{self.ctrl.price_low_threshold:.2f} €/kWh",
                "price_expensive": f"{self.ctrl.price_high_threshold:.2f} €/kWh",
                "battery_full": f"{self.ctrl.battery_soc_high:.0f}%" if self.ctrl.battery_soc_entity else "N/A",
                "battery_empty": f"{self.ctrl.battery_soc_low:.0f}%" if self.ctrl.battery_soc_entity else "N/A",
            },

            # Integration status
            "integrations": {
                "epex_spot": self.ctrl.has_epex_integration,
                "solcast": self.ctrl.has_solcast_integration,
            },
        }

        # EPEX Spot details when available
        if self.ctrl.has_epex_integration:
            attrs["epex_spot"] = {
                "price": f"{self.ctrl.epex_price:.4f} €/kWh" if self.ctrl.epex_price_entity else "N/A",
                "quantile": f"{self.ctrl.epex_quantile:.2f}" if self.ctrl.epex_quantile_entity else "N/A",
                "quantile_explanation": "0=cheapest, 1=most expensive price of the day",
                "forecast_entries": len(self.ctrl.epex_price_forecast),
            }

        # Solcast details when available
        if self.ctrl.has_solcast_integration:
            attrs["solcast"] = {
                "forecast_today": f"{self.ctrl.solcast_forecast_today:.1f} kWh",
                "hourly_entries": len(self.ctrl.solcast_hourly_forecast),
            }

        return attrs

    def _get_score_explanation(self, score: int) -> str:
        """Explains the score."""
        if score >= 6:
            return "Perfect timing!"
        elif score >= 5:
            return "Ideal timing!"
        elif score >= 3:
            return "Good timing"
        elif score >= 1:
            return "Acceptable"
        elif score >= -1:
            return "Neutral"
        elif score >= -3:
            return "Rather unfavorable"
        else:
            return "Bad timing"

    @property
    def available(self) -> bool:
        """Sensor is only available after data restoration."""
        return super().available


class NextCheapHourSensor(BaseEntity):
    """
    Shows the next cheap hour based on EPEX price forecast.

    Requires configured EPEX Spot integration with price forecast.
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
        """Shows when the next cheap hour is."""
        return self.ctrl.next_cheap_hour_text

    @property
    def icon(self) -> str:
        """Icon based on availability."""
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
        """Detailed price forecast information."""
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
        """Sensor is only available after data restoration."""
        return super().available


# =============================================================================
# ELECTRICITY PRICE AVERAGE SENSORS
# =============================================================================


class DailyFeedInSensor(BaseEntity):
    """Feed-in today: tariff and amount."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Tages Einspeisung",
            unit="€",
            icon="mdi:transmission-tower-export",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.daily_feed_in_earnings, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "amount_kwh": round(self.ctrl.daily_feed_in_kwh, 2),
            "tariff_ct": f"{self.ctrl.current_feed_in_tariff * 100:.2f}",
        }


class DailyGridImportSensor(BaseEntity):
    """Grid import today: cost and consumption."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Tages Netzbezug",
            unit="€",
            icon="mdi:transmission-tower-import",
            state_class=SensorStateClass.TOTAL,
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
            "consumption_kwh": round(self.ctrl.daily_grid_import_kwh, 2),
            "average_ct": round(avg, 2) if avg else None,
        }


class DailyAveragePriceSensor(BaseEntity):
    """Average paid electricity price today in ct/kWh."""

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
    """Average paid electricity price this month in ct/kWh."""

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
    Overall weighted average electricity price in ct/kWh.

    Shows the actual average price paid since tracking began.
    Ideal for comparison with fixed-price tariffs.
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
            "consumption_kwh": round(self.ctrl.tracked_grid_import_kwh, 2),
            "cost_eur": round(self.ctrl.total_grid_import_cost, 2),
            "average_eur_per_kwh": f"{avg_eur:.4f}" if avg_eur else None,
            "description": "Weighted average since tracking began",
        }


class DailyNetElectricityCostSensor(BaseEntity):
    """Net electricity cost today: grid import minus feed-in."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Tages Stromkosten",
            unit="€",
            icon="mdi:cash-register",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.daily_net_electricity_cost, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "grid_import_eur": round(self.ctrl.daily_grid_import_cost, 2),
            "feed_in_eur": round(self.ctrl.daily_feed_in_earnings, 2),
        }


class TotalGridImportCostSensor(BaseEntity):
    """Total grid import cost in Euro."""

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
            "consumption_kwh": round(self.ctrl.tracked_grid_import_kwh, 2),
            "average_price_ct": f"{avg:.2f}" if avg else None,
        }


class SpotVsFixedPriceSensor(BaseEntity):
    """
    Comparison of spot tariff vs. configured fixed price.

    Shows savings/additional cost in Euro:
    - Positive = spot was cheaper than fixed price
    - Negative = fixed price would have been cheaper
    """

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Spot vs Fixpreis",
            unit="€",
            icon="mdi:scale-balance",
            state_class=SensorStateClass.TOTAL,
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
            return "mdi:thumb-up"  # Spot was cheaper
        elif savings < 0:
            return "mdi:thumb-down"  # Fixed price would have been cheaper
        return "mdi:scale-balance"

    @property
    def extra_state_attributes(self) -> dict:
        avg = self.ctrl.average_electricity_price_ct
        fixed = self.ctrl.fixed_price_compare_ct
        savings = self.ctrl.spot_vs_fixed_savings
        kwh = self.ctrl.tracked_grid_import_kwh

        attrs = {
            "fixed_price_ct": round(fixed, 2),
            "spot_average_ct": round(avg, 2) if avg else None,
            "consumption_kwh": round(kwh, 2),
        }

        if avg and fixed and kwh > 0:
            # What would fixed price have cost?
            fixed_cost = kwh * (fixed / 100)
            spot_cost = self.ctrl.total_grid_import_cost
            attrs["fixed_price_cost_eur"] = round(fixed_cost, 2)
            attrs["spot_cost_eur"] = round(spot_cost, 2)
            attrs["difference_per_kwh_ct"] = round(fixed - avg, 2) if avg else None

            if savings and savings > 0:
                attrs["conclusion"] = f"Spot {abs(savings):.2f}€ cheaper"
            elif savings and savings < 0:
                attrs["conclusion"] = f"Fixed price would be {abs(savings):.2f}€ cheaper"
            else:
                attrs["conclusion"] = "About the same"

        return attrs


# =============================================================================
# AUTO-CHARGE BATTERY SENSORS
# =============================================================================


class AutoChargeReasonSensor(BaseEntity):
    """Shows the reason for charging/not charging."""

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
    """Price difference between cheapest and most expensive hour today."""

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
            "threshold_ct": self.ctrl.auto_charge_min_price_diff,
            "condition_met": self.ctrl._check_price_diff_condition(),
            "description": f"Min. {self.ctrl.auto_charge_min_price_diff} ct required",
        }


class AutoChargePVForecastSensor(BaseEntity):
    """PV forecast for today (for auto-charge decision)."""

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
            "threshold_kwh": self.ctrl.auto_charge_pv_threshold,
            "condition_met": self.ctrl._check_pv_condition(),
            "source": "Solcast" if self.ctrl.has_solcast_integration else "Manual",
            "description": f"Below {self.ctrl.auto_charge_pv_threshold} kWh = charge",
        }


class AutoChargePriceQuantileSensor(BaseEntity):
    """Current price quantile (0=cheapest, 1=most expensive hour)."""

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
            "threshold": self.ctrl.auto_charge_price_quantile,
            "condition_met": self.ctrl._check_price_condition(),
            "price_ct": round(self.ctrl.current_electricity_price * 100, 1),
            "description": f"0=cheapest, 1=most expensive. Below {self.ctrl.auto_charge_price_quantile} = cheap",
        }


class AutoChargeConditionsSensor(BaseEntity):
    """Shows which conditions are met."""

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
        """Shows number of fulfilled conditions."""
        conditions = [
            not self.ctrl.auto_charge_winter_only or self.ctrl.is_winter,
            self.ctrl._check_pv_condition(),
            self.ctrl._check_price_condition(),
            self.ctrl._check_soc_condition(),
            self.ctrl._check_price_diff_condition(),
        ]
        fulfilled = sum(conditions)
        return f"{fulfilled}/5 met"

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
            "winter": "✓ Winter" if winter_ok else "✗ Summer",
            "pv_prognose": "✓ Low" if pv_ok else "✗ High",
            "preis": "✓ Cheap" if price_ok else "✗ Expensive",
            "batterie_soc": "✓ Low" if soc_ok else "✗ Sufficient",
            "preisdifferenz": "✓ Large" if diff_ok else "✗ Small",
            "all_met": self.ctrl.should_auto_charge,
        }


class AutoChargeDiagnosticSensor(BaseEntity):
    """
    Diagnostic sensor for auto-charge.

    Shows all relevant information about why charging/not charging.
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
        """Status text."""
        if not self.ctrl.auto_charge_enabled:
            return "Disabled"
        if self.ctrl.auto_charge_winter_only and not self.ctrl.is_winter:
            return "Paused (summer)"
        if self.ctrl.should_auto_charge:
            return "Charging recommended"
        return "No charging"

    @property
    def icon(self) -> str:
        if not self.ctrl.auto_charge_enabled:
            return "mdi:battery-off"
        if self.ctrl.should_auto_charge:
            return "mdi:battery-charging"
        return "mdi:battery-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """All diagnostic information."""
        forecast = self.ctrl.solcast_forecast_today if self.ctrl.has_solcast_integration else self.ctrl.pv_forecast
        price_diff = self.ctrl.epex_price_diff_today

        # Calculate savings potential
        charge_cost = None
        potential_savings = None
        if price_diff and self.ctrl.auto_charge_power:
            charge_kwh = self.ctrl.auto_charge_power / 1000
            charge_cost = charge_kwh * self.ctrl.current_electricity_price
            potential_savings = charge_kwh * (price_diff / 100) * 0.85

        # Conditions with explanation
        def check_with_reason(name: str, current, threshold, condition_met: bool, compare: str = "<") -> dict:
            if compare == "<":
                status = "✓" if condition_met else f"✗ ({current} >= {threshold})"
            elif compare == "<=":
                status = "✓" if condition_met else f"✗ ({current} > {threshold})"
            else:
                status = "✓" if condition_met else f"✗ ({current} < {threshold})"
            return {
                "met": condition_met,
                "current": current,
                "threshold": threshold,
                "status": status,
            }

        return {
            # === MAIN STATUS ===
            "recommendation": "CHARGE" if self.ctrl.should_auto_charge else "NO CHARGE",
            "reason": self.ctrl.auto_charge_reason,

            # === SETTINGS ===
            "settings": {
                "enabled": self.ctrl.auto_charge_enabled,
                "winter_only": self.ctrl.auto_charge_winter_only,
                "pv_threshold_kwh": self.ctrl.auto_charge_pv_threshold,
                "price_quantile_threshold": self.ctrl.auto_charge_price_quantile,
                "min_soc_percent": self.ctrl.auto_charge_min_soc,
                "target_soc_percent": self.ctrl.auto_charge_target_soc,
                "min_price_diff_ct": self.ctrl.auto_charge_min_price_diff,
                "charge_power_w": self.ctrl.auto_charge_power,
            },

            # === CURRENT VALUES ===
            "current": {
                "is_winter": self.ctrl.is_winter,
                "pv_forecast_kwh": round(forecast, 1),
                "price_quantile": round(self.ctrl.epex_quantile, 2) if self.ctrl.has_epex_integration else None,
                "price_ct": round(self.ctrl.current_electricity_price * 100, 1),
                "battery_soc": round(self.ctrl.battery_soc, 0) if self.ctrl.battery_soc_entity else None,
                "price_diff_ct": price_diff,
            },

            # === CONDITIONS (why charging/not charging) ===
            "condition_winter": {
                "met": not self.ctrl.auto_charge_winter_only or self.ctrl.is_winter,
                "winter_only_active": self.ctrl.auto_charge_winter_only,
                "is_winter": self.ctrl.is_winter,
                "status": "✓" if (not self.ctrl.auto_charge_winter_only or self.ctrl.is_winter) else "✗ (Summer, Oct-Mar only)",
            },
            "condition_pv": {
                "met": self.ctrl._check_pv_condition(),
                "current_kwh": round(forecast, 1),
                "threshold_kwh": self.ctrl.auto_charge_pv_threshold,
                "status": "✓" if self.ctrl._check_pv_condition() else f"✗ (Forecast {forecast:.1f} kWh too high)",
            },
            "condition_price": {
                "met": self.ctrl._check_price_condition(),
                "current_quantile": round(self.ctrl.epex_quantile, 2) if self.ctrl.has_epex_integration else None,
                "threshold_quantile": self.ctrl.auto_charge_price_quantile,
                "status": "✓" if self.ctrl._check_price_condition() else f"✗ (Quantile {self.ctrl.epex_quantile:.2f} too high)",
            },
            "condition_soc": {
                "met": self.ctrl._check_soc_condition(),
                "current_percent": round(self.ctrl.battery_soc, 0) if self.ctrl.battery_soc_entity else None,
                "threshold_percent": self.ctrl.auto_charge_min_soc,
                "status": "✓" if self.ctrl._check_soc_condition() else f"✗ (SOC {self.ctrl.battery_soc:.0f}% already high enough)",
            },
            "condition_price_diff": {
                "met": self.ctrl._check_price_diff_condition(),
                "current_ct": price_diff,
                "threshold_ct": self.ctrl.auto_charge_min_price_diff,
                "status": "✓" if self.ctrl._check_price_diff_condition() else f"✗ (Difference {price_diff} ct too low)",
            },

            # === COST/SAVINGS ===
            "cost_calculation": {
                "charge_power_kw": self.ctrl.auto_charge_power / 1000,
                "current_price_ct": round(self.ctrl.current_electricity_price * 100, 1),
                "cost_1h_eur": round(charge_cost, 2) if charge_cost else None,
                "savings_1h_eur": round(potential_savings, 2) if potential_savings else None,
                "efficiency_assumption": "85%",
            },

            # === STATISTICS ===
            "statistics": self.ctrl.auto_charge_stats,

            # === INTEGRATION STATUS ===
            "integrations": {
                "epex_spot": self.ctrl.has_epex_integration,
                "solcast": self.ctrl.has_solcast_integration,
                "battery_sensor": bool(self.ctrl.battery_soc_entity),
            },
        }


# =============================================================================
# BENCHMARK SENSORS
# =============================================================================

MONTH_NAMES_DE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                  "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


class BenchmarkAvgSensor(BaseEntity):
    """Reference average consumption for country/household size."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Haus Durchschnitt",
                         unit="kWh/Jahr", icon="mdi:home-group",
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        return self.ctrl.benchmark_avg_consumption_kwh


class BenchmarkOwnSensor(BaseEntity):
    """Own household consumption extrapolated to 1 year."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Gesamtverbrauch",
                         unit="kWh/Jahr", icon="mdi:home-lightning-bolt",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        val = self.ctrl.benchmark_own_annual_consumption_kwh
        return round(val) if val is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {
            "calculation": "buckets" if len(self.ctrl._monthly_buckets) >= 12 else "extrapolation",
            "buckets_filled": len(self.ctrl._monthly_buckets),
        }
        for m in range(1, 13):
            name = MONTH_NAMES_DE[m - 1].lower()
            bucket = self.ctrl._monthly_buckets.get(m)
            if bucket is not None:
                attrs[f"{name}_consumption_kwh"] = round(
                    bucket.get("self_consumption", 0.0) + bucket.get("grid_import", 0.0), 1
                )
                attrs[f"{name}_feed_in_kwh"] = round(bucket.get("feed_in", 0.0), 1)
                attrs[f"{name}_wp_kwh"] = round(bucket.get("wp", 0.0), 1)
        return attrs


class BenchmarkHouseholdSensor(BaseEntity):
    """Household consumption without heat pump, extrapolated to 1 year."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Haus Verbrauch",
                         unit="kWh/Jahr", icon="mdi:home-lightning-bolt-outline",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        val = self.ctrl.benchmark_household_consumption_kwh
        return round(val) if val is not None else None


class BenchmarkComparisonSensor(BaseEntity):
    """Percentage difference vs. average."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Haus Vergleich",
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
        super().__init__(ctrl, name, "PV CO2 Vermieden",
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
        super().__init__(ctrl, name, "Effizienz Score",
                         unit="Punkte", icon="mdi:star-circle",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)
        self._last_score: int | None = None

    @property
    def native_value(self):
        score = self.ctrl.benchmark_efficiency_score
        if score is not None:
            self._last_score = score
        return self._last_score

    @property
    def extra_state_attributes(self) -> dict:
        autarky = self.ctrl.autarky_rate
        specific = self.ctrl.benchmark_specific_yield
        sc_ratio = self.ctrl.self_consumption_ratio
        comparison = self.ctrl.benchmark_consumption_vs_avg
        return {
            "autarky_points": f"{min(35, autarky * 0.35):.1f}/35" if autarky is not None else "n/a",
            "specific_yield_points": f"{min(25, (specific / 900) * 25):.1f}/25" if specific and specific > 0 else "n/a",
            "self_consumption_points": f"{min(20, sc_ratio * 0.2):.1f}/20" if sc_ratio is not None else "n/a",
            "consumption_points": f"{max(0, min(20, 10 - comparison * 0.2)):.1f}/20" if comparison is not None else "n/a",
        }

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
        super().__init__(ctrl, name, "Bewertung",
                         icon="mdi:trophy",
                         device_type=DEVICE_BENCHMARK)
        self._last_rating: str | None = None

    @property
    def native_value(self):
        rating = self.ctrl.benchmark_rating
        if rating is not None:
            self._last_rating = rating
        return self._last_rating


class BenchmarkGridImportSensor(BaseEntity):
    """Annual grid import extrapolated from benchmark period."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Netz Bezug",
                         unit="kWh/Jahr", icon="mdi:transmission-tower-import",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        val = self.ctrl.benchmark_annual_grid_import_kwh
        return round(val, 0) if val else None


class BenchmarkAnnualPVSensor(BaseEntity):
    """Extrapolated annual PV production."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "PV Produktion",
                         unit="kWh/Jahr", icon="mdi:solar-power",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_annual_pv_production_kwh
        if val is None:
            return None
        return round(val, 0)


class BenchmarkSpecificYieldSensor(BaseEntity):
    """Specific yield in kWh/kWp."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "PV Ertrag",
                         unit="kWh/kWp", icon="mdi:solar-power-variant-outline",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_specific_yield
        if val is None:
            return None
        return round(val, 0)


class BenchmarkHeatpumpAvgSensor(BaseEntity):
    """Reference heat pump consumption."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "WP Durchschnitt",
                         unit="kWh/Jahr", icon="mdi:heat-pump",
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        return self.ctrl.benchmark_avg_heatpump_kwh


class BenchmarkHeatpumpOwnSensor(BaseEntity):
    """Own heat pump consumption extrapolated to 1 year."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "WP Verbrauch",
                         unit="kWh/Jahr", icon="mdi:heat-pump-outline",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        val = self.ctrl.benchmark_own_heatpump_kwh
        return round(val) if val is not None else None


class BenchmarkHeatpumpComparisonSensor(BaseEntity):
    """Heat pump consumption vs average comparison in %."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "WP Vergleich",
                         unit="%", icon="mdi:heat-pump",
                         state_class=SensorStateClass.MEASUREMENT,
                         device_type=DEVICE_BENCHMARK)

    @property
    def native_value(self):
        val = self.ctrl.benchmark_heatpump_vs_avg
        return round(val, 1) if val is not None else None


# ---------------------------------------------------------------------------
# LOAD FORECAST SENSORS (24x7 profile)
# ---------------------------------------------------------------------------

class _ForecastBaseSensor(BaseEntity):
    """Basis für Load-Forecast Sensoren. Liest aus ctrl.forecaster."""

    def __init__(self, ctrl, name: str, key: str, icon: str = "mdi:chart-bell-curve"):
        super().__init__(
            ctrl,
            name,
            key,
            unit="kWh",
            icon=icon,
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.ENERGY_STORAGE,
            device_type=DEVICE_FORECAST,
        )

    @property
    def available(self) -> bool:
        return getattr(self.ctrl, "_restored", True) and self.ctrl.forecaster is not None

    @property
    def extra_state_attributes(self) -> dict:
        fc = self.ctrl.forecaster
        if fc is None:
            return {}
        attrs: dict[str, Any] = {
            "method": fc.method,
            "days_of_history": fc.days_of_history,
            "base_load_only": fc.base_load_only,
        }
        if fc.last_update is not None:
            attrs["last_update"] = fc.last_update.isoformat()
        if fc.last_error:
            attrs["last_error"] = fc.last_error
        return attrs


class LoadForecast1hSensor(_ForecastBaseSensor):
    """Verbrauchsprognose nächste Stunde."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose 1h", icon="mdi:clock-outline")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_next_hours(1) if fc is not None else None


class LoadForecast6hSensor(_ForecastBaseSensor):
    """Verbrauchsprognose nächste 6 Stunden."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose 6h", icon="mdi:clock-time-six-outline")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_next_hours(6) if fc is not None else None


class LoadForecastTodayRestSensor(_ForecastBaseSensor):
    """Verbrauchsprognose Rest des heutigen Tages."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose Heute Rest", icon="mdi:weather-sunset-down")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_today_rest() if fc is not None else None


class LoadForecastTomorrowSensor(_ForecastBaseSensor):
    """Verbrauchsprognose morgen (00:00–23:00)."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose Morgen", icon="mdi:calendar-arrow-right")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_tomorrow() if fc is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        fc = self.ctrl.forecaster
        if fc is None:
            return attrs
        try:
            from datetime import timedelta
            from homeassistant.util import dt as dt_util
            start_tomorrow = (dt_util.as_local(dt_util.utcnow()) + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            attrs["forecast_hourly"] = fc.hourly_forecast(24, now=start_tomorrow)
            low, high = fc.confidence_band(24, now=start_tomorrow)
            if low is not None:
                attrs["confidence_low"] = low
            if high is not None:
                attrs["confidence_high"] = high
        except Exception:
            pass
        return attrs


class LoadForecast24hSensor(_ForecastBaseSensor):
    """Rollierende 24h-Prognose ab jetzt (für Batterie-/Lade-Logik)."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose 24h", icon="mdi:chart-bell-curve")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_next_hours(24) if fc is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        fc = self.ctrl.forecaster
        if fc is None:
            return attrs
        try:
            attrs["forecast_hourly"] = fc.hourly_forecast(24)
            low, high = fc.confidence_band(24)
            if low is not None:
                attrs["confidence_low"] = low
            if high is not None:
                attrs["confidence_high"] = high
        except Exception:
            pass
        return attrs


# =============================================================================
# PV SURPLUS (live)
# =============================================================================


class PVSurplusValueSensor(BaseEntity):
    """Aktueller PV-Überschuss in W (pv_power - house_power, clamp >= 0)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "PV Ueberschuss",
            unit="W",
            icon="mdi:solar-power-variant",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.POWER,
        )

    @property
    def available(self) -> bool:
        return bool(self.ctrl.house_power_entity) and super().available

    @property
    def native_value(self) -> float:
        return round(self.ctrl.current_pv_surplus_w, 0)

    @property
    def extra_state_attributes(self):
        return {
            "pv_leistung_w": round(self.ctrl.pv_power, 0),
            "hausverbrauch_w": round(self.ctrl.house_power, 0),
            "shiftable_load_w": round(self.ctrl.shiftable_load_power, 0),
            "effektiver_hausverbrauch_w": round(self.ctrl.effective_house_power, 0),
            "schwellen_w": {
                k: round(v, 0) for k, v in self.ctrl.surplus_thresholds_w.items()
            },
        }


class PVPeakValueSensor(BaseEntity):
    """Aktuell verwendete PV-Anlagen-Peakleistung in W (Fallback-Kette sichtbar)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "PV Peak",
            unit="W",
            icon="mdi:solar-power-variant-outline",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.POWER,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.pv_peak_power, 0)

    @property
    def extra_state_attributes(self):
        return {
            "quelle": self.ctrl.pv_peak_power_source,
            "kwp_aus_strings": round(self.ctrl.total_installed_kwp, 2),
            "schwellen_w": {
                k: round(v, 0) for k, v in self.ctrl.surplus_thresholds_w.items()
            },
        }
