from __future__ import annotations

from typing import Final
from homeassistant.const import Platform

# --- Domain / Platforms -------------------------------------------------------
DOMAIN: Final[str] = "pv_management"
DATA_CTRL: Final[str] = "ctrl"

PLATFORMS: Final[tuple[Platform, ...]] = (
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
)

# --- Config keys (Setup) ------------------------------------------------------
CONF_NAME: Final[str] = "name"
CONF_PV_PRODUCTION_ENTITY: Final[str] = "pv_production_entity"
CONF_GRID_EXPORT_ENTITY: Final[str] = "grid_export_entity"
CONF_GRID_IMPORT_ENTITY: Final[str] = "grid_import_entity"
CONF_CONSUMPTION_ENTITY: Final[str] = "consumption_entity"

# --- Sensors for recommendation logic -----------------------------------------
CONF_BATTERY_SOC_ENTITY: Final[str] = "battery_soc_entity"
CONF_PV_POWER_ENTITY: Final[str] = "pv_power_entity"
CONF_PV_FORECAST_ENTITY: Final[str] = "pv_forecast_entity"

# --- EPEX Spot Integration ----------------------------------------------------
CONF_EPEX_PRICE_ENTITY: Final[str] = "epex_price_entity"
CONF_EPEX_QUANTILE_ENTITY: Final[str] = "epex_quantile_entity"

# --- Solcast Integration ------------------------------------------------------
CONF_SOLCAST_FORECAST_ENTITY: Final[str] = "solcast_forecast_entity"

# --- Option keys (can be changed later) ---------------------------------------
CONF_ELECTRICITY_PRICE: Final[str] = "electricity_price"
CONF_ELECTRICITY_PRICE_ENTITY: Final[str] = "electricity_price_entity"
CONF_ELECTRICITY_PRICE_UNIT: Final[str] = "electricity_price_unit"
CONF_FEED_IN_TARIFF: Final[str] = "feed_in_tariff"
CONF_FEED_IN_TARIFF_ENTITY: Final[str] = "feed_in_tariff_entity"
CONF_FEED_IN_TARIFF_UNIT: Final[str] = "feed_in_tariff_unit"

# --- Price units --------------------------------------------------------------
PRICE_UNIT_EUR: Final[str] = "eur"
PRICE_UNIT_CENT: Final[str] = "cent"
CONF_INSTALLATION_COST: Final[str] = "installation_cost"
CONF_SAVINGS_OFFSET: Final[str] = "savings_offset"
CONF_ENERGY_OFFSET_SELF: Final[str] = "energy_offset_self_consumption"
CONF_ENERGY_OFFSET_EXPORT: Final[str] = "energy_offset_export"
CONF_INSTALLATION_DATE: Final[str] = "installation_date"

# --- Recommendation thresholds ------------------------------------------------
CONF_BATTERY_SOC_HIGH: Final[str] = "battery_soc_high"
CONF_BATTERY_SOC_LOW: Final[str] = "battery_soc_low"
CONF_PRICE_HIGH_THRESHOLD: Final[str] = "price_high_threshold"
CONF_PRICE_LOW_THRESHOLD: Final[str] = "price_low_threshold"
CONF_PV_POWER_HIGH: Final[str] = "pv_power_high"
CONF_PV_PEAK_POWER: Final[str] = "pv_peak_power"
CONF_WINTER_BASE_LOAD: Final[str] = "winter_base_load"

# --- Auto-Charge (automatic battery charging) ---------------------------------
CONF_AUTO_CHARGE_ENABLED: Final[str] = "auto_charge_enabled"
CONF_AUTO_CHARGE_WINTER_ONLY: Final[str] = "auto_charge_winter_only"
CONF_AUTO_CHARGE_PV_THRESHOLD: Final[str] = "auto_charge_pv_threshold"
CONF_AUTO_CHARGE_PRICE_QUANTILE: Final[str] = "auto_charge_price_quantile"
CONF_AUTO_CHARGE_MIN_SOC: Final[str] = "auto_charge_min_soc"
# REMOVED: CONF_AUTO_CHARGE_TARGET_SOC - now uses CONF_BATTERY_TARGET_SOC
CONF_AUTO_CHARGE_MIN_PRICE_DIFF: Final[str] = "auto_charge_min_price_diff"
CONF_AUTO_CHARGE_POWER: Final[str] = "auto_charge_power"

# --- Shared battery setting (for Auto-Charge AND Discharge Control) -----------
CONF_BATTERY_TARGET_SOC: Final[str] = "battery_target_soc"  # target SOC / hold SOC

# --- Defaults -----------------------------------------------------------------
DEFAULT_NAME: Final[str] = "PV Management"
DEFAULT_ELECTRICITY_PRICE: Final[float] = 0.35  # €/kWh
DEFAULT_ELECTRICITY_PRICE_UNIT: Final[str] = PRICE_UNIT_EUR
DEFAULT_FEED_IN_TARIFF: Final[float] = 0.08  # €/kWh
DEFAULT_FEED_IN_TARIFF_UNIT: Final[str] = PRICE_UNIT_EUR
DEFAULT_INSTALLATION_COST: Final[float] = 10000.0  # €
DEFAULT_SAVINGS_OFFSET: Final[float] = 0.0  # € already amortised
DEFAULT_ENERGY_OFFSET_SELF: Final[float] = 0.0  # kWh self consumption before tracking
DEFAULT_ENERGY_OFFSET_EXPORT: Final[float] = 0.0  # kWh export before tracking

# Recommendation defaults
DEFAULT_BATTERY_SOC_HIGH: Final[float] = 80.0  # % - battery "full"
DEFAULT_BATTERY_SOC_LOW: Final[float] = 20.0   # % - battery "empty"
DEFAULT_PRICE_HIGH_THRESHOLD: Final[float] = 0.30  # €/kWh - expensive
DEFAULT_PRICE_LOW_THRESHOLD: Final[float] = 0.15   # €/kWh - cheap
DEFAULT_PV_POWER_HIGH: Final[float] = 1000.0  # W - high PV (fallback)
DEFAULT_PV_PEAK_POWER: Final[float] = 10000.0  # W - 10kWp system
DEFAULT_WINTER_BASE_LOAD: Final[float] = 0.0  # W - winter base load (e.g. heat pump)

# Auto-Charge Defaults
DEFAULT_AUTO_CHARGE_ENABLED: Final[bool] = False
DEFAULT_AUTO_CHARGE_WINTER_ONLY: Final[bool] = True  # only charge in winter (Oct-Mar)
DEFAULT_AUTO_CHARGE_PV_THRESHOLD: Final[float] = 5.0  # kWh - charge below this forecast
DEFAULT_AUTO_CHARGE_PRICE_QUANTILE: Final[float] = 0.3  # 0-1, below this value is "cheap"
DEFAULT_AUTO_CHARGE_MIN_SOC: Final[float] = 30.0  # % - only charge when SOC below this value
DEFAULT_AUTO_CHARGE_MIN_PRICE_DIFF: Final[float] = 15.0  # ct/kWh - min. difference (charging losses + battery/inverter wear)
DEFAULT_AUTO_CHARGE_POWER: Final[float] = 3000.0  # W - charge power for auto-charge

# Shared default for target/hold SOC
DEFAULT_BATTERY_TARGET_SOC: Final[float] = 100.0  # % - target SOC for charging AND holding

# --- Amortisation Helper Sync -------------------------------------------------
CONF_AMORTISATION_HELPER: Final[str] = "amortisation_helper"
CONF_RESTORE_FROM_HELPER: Final[str] = "restore_from_helper"
CONF_YEARLY_COST: Final[str] = "yearly_cost"
DEFAULT_YEARLY_COST: Final[float] = 0.0  # €/Jahr (z.B. Versicherung, Wartung)

# --- Fixed price comparison ---------------------------------------------------
CONF_FIXED_PRICE_COMPARE: Final[str] = "fixed_price_compare"  # fixed price for comparison (ct/kWh)

# --- Discharge Control --------------------------------------------------------
CONF_DISCHARGE_ENABLED: Final[str] = "discharge_enabled"
CONF_DISCHARGE_WINTER_ONLY: Final[str] = "discharge_winter_only"
CONF_DISCHARGE_PRICE_QUANTILE: Final[str] = "discharge_price_quantile"
# REMOVED: CONF_DISCHARGE_HOLD_SOC - now uses CONF_BATTERY_TARGET_SOC
CONF_DISCHARGE_ALLOW_SOC: Final[str] = "discharge_allow_soc"
CONF_DISCHARGE_SUMMER_SOC: Final[str] = "discharge_summer_soc"

# Fixed price comparison default
DEFAULT_FIXED_PRICE_COMPARE: Final[float] = 13.9  # ct/kWh

# Discharge Defaults
DEFAULT_DISCHARGE_ENABLED: Final[bool] = False
DEFAULT_DISCHARGE_WINTER_ONLY: Final[bool] = True  # only active in winter (Oct-Mar)
DEFAULT_DISCHARGE_PRICE_QUANTILE: Final[float] = 0.7  # 0-1, above this value is "expensive" → discharge
# REMOVED: DEFAULT_DISCHARGE_HOLD_SOC - now uses DEFAULT_BATTERY_TARGET_SOC
DEFAULT_DISCHARGE_ALLOW_SOC: Final[float] = 20.0  # % - battery can discharge down to this level
DEFAULT_DISCHARGE_SUMMER_SOC: Final[float] = 10.0  # % - normal discharge in summer (10%)

# --- Ranges for Config Flow / Options -----------------------------------------
RANGE_PRICE_EUR: Final[dict] = {"min": 0.01, "max": 1.0, "step": 0.001}
RANGE_PRICE_CENT: Final[dict] = {"min": 1.0, "max": 100.0, "step": 0.01}
RANGE_TARIFF_EUR: Final[dict] = {"min": 0.0, "max": 0.5, "step": 0.001}
RANGE_TARIFF_CENT: Final[dict] = {"min": 0.0, "max": 50.0, "step": 0.01}
RANGE_COST: Final[dict] = {"min": 0.0, "max": 200000.0, "step": 1.0}
RANGE_OFFSET: Final[dict] = {"min": 0.0, "max": 100000.0, "step": 0.01}
RANGE_ENERGY_OFFSET: Final[dict] = {"min": 0.0, "max": 500000.0, "step": 0.01}
RANGE_BATTERY_SOC: Final[dict] = {"min": 0.0, "max": 100.0, "step": 1.0}
RANGE_PV_POWER: Final[dict] = {"min": 0.0, "max": 50000.0, "step": 1.0}

# --- Recommendation states ----------------------------------------------------
RECOMMENDATION_DARK_GREEN: Final[str] = "dark_green"
RECOMMENDATION_GREEN: Final[str] = "green"
RECOMMENDATION_YELLOW: Final[str] = "yellow"
RECOMMENDATION_ORANGE: Final[str] = "orange"
RECOMMENDATION_RED: Final[str] = "red"

# --- Benchmark ----------------------------------------------------------------
CONF_BENCHMARK_ENABLED: Final[str] = "benchmark_enabled"
CONF_BENCHMARK_HOUSEHOLD_SIZE: Final[str] = "benchmark_household_size"
CONF_BENCHMARK_COUNTRY: Final[str] = "benchmark_country"
CONF_BENCHMARK_HEATPUMP: Final[str] = "benchmark_heatpump"
CONF_BENCHMARK_HEATPUMP_ENTITY: Final[str] = "benchmark_heatpump_entity"
CONF_BENCHMARK_HEATPUMP_DATE: Final[str] = "benchmark_heatpump_date"

DEFAULT_BENCHMARK_ENABLED: Final[bool] = False
DEFAULT_BENCHMARK_HOUSEHOLD_SIZE: Final[int] = 3
DEFAULT_BENCHMARK_COUNTRY: Final[str] = "AT"
DEFAULT_BENCHMARK_HEATPUMP: Final[bool] = False

# Average annual household electricity consumption WITHOUT heat pump per household size (kWh/year)
# Sources: E-Control (AT), BDEW (DE), BFE (CH) — 2023/2024 data
BENCHMARK_CONSUMPTION: Final[dict[str, dict[int, int]]] = {
    "AT": {1: 2200, 2: 3500, 3: 4000, 4: 4500, 5: 5500, 6: 6500},
    "DE": {1: 2000, 2: 3200, 3: 3900, 4: 4400, 5: 5400, 6: 6300},
    "CH": {1: 2500, 2: 3800, 3: 4400, 4: 5000, 5: 6000, 6: 7000},
}

# Average heat pump electricity consumption (kWh/year) — single-family home
# Sources: Austrian Energy Agency, BDEW heat pump study 2023
BENCHMARK_HEATPUMP_CONSUMPTION: Final[dict[str, int]] = {
    "AT": 4000,
    "DE": 4500,
    "CH": 3500,
}

# CO2 factor electricity mix (kg CO2/kWh) — Umweltbundesamt AT/DE, BFE CH
BENCHMARK_CO2_FACTORS: Final[dict[str, float]] = {
    "AT": 0.150,
    "DE": 0.380,
    "CH": 0.030,
}

RANGE_HOUSEHOLD_SIZE: Final[dict] = {"min": 1, "max": 6, "step": 1}

# --- PV Strings (comparison of multiple strings) -----------------------------
CONF_PV_STRING_1_NAME: Final[str] = "pv_string_1_name"
CONF_PV_STRING_1_ENTITY: Final[str] = "pv_string_1_entity"
CONF_PV_STRING_2_NAME: Final[str] = "pv_string_2_name"
CONF_PV_STRING_2_ENTITY: Final[str] = "pv_string_2_entity"
CONF_PV_STRING_3_NAME: Final[str] = "pv_string_3_name"
CONF_PV_STRING_3_ENTITY: Final[str] = "pv_string_3_entity"
CONF_PV_STRING_4_NAME: Final[str] = "pv_string_4_name"
CONF_PV_STRING_4_ENTITY: Final[str] = "pv_string_4_entity"
CONF_PV_STRING_1_POWER: Final[str] = "pv_string_1_power"
CONF_PV_STRING_2_POWER: Final[str] = "pv_string_2_power"
CONF_PV_STRING_3_POWER: Final[str] = "pv_string_3_power"
CONF_PV_STRING_4_POWER: Final[str] = "pv_string_4_power"
CONF_PV_STRING_1_KWP: Final[str] = "pv_string_1_kwp"
CONF_PV_STRING_2_KWP: Final[str] = "pv_string_2_kwp"
CONF_PV_STRING_3_KWP: Final[str] = "pv_string_3_kwp"
CONF_PV_STRING_4_KWP: Final[str] = "pv_string_4_kwp"

PV_STRING_CONFIGS = [
    (CONF_PV_STRING_1_NAME, CONF_PV_STRING_1_ENTITY, CONF_PV_STRING_1_POWER, CONF_PV_STRING_1_KWP),
    (CONF_PV_STRING_2_NAME, CONF_PV_STRING_2_ENTITY, CONF_PV_STRING_2_POWER, CONF_PV_STRING_2_KWP),
    (CONF_PV_STRING_3_NAME, CONF_PV_STRING_3_ENTITY, CONF_PV_STRING_3_POWER, CONF_PV_STRING_3_KWP),
    (CONF_PV_STRING_4_NAME, CONF_PV_STRING_4_ENTITY, CONF_PV_STRING_4_POWER, CONF_PV_STRING_4_KWP),
]
