from __future__ import annotations

from typing import Final
from homeassistant.const import Platform

# --- Domain / Platforms -------------------------------------------------------
DOMAIN: Final[str] = "pv_management"
DATA_CTRL: Final[str] = "ctrl"

PLATFORMS: Final[tuple[Platform, ...]] = (
    Platform.SENSOR,
    Platform.BUTTON,
)

# --- Config keys (Setup) ------------------------------------------------------
CONF_NAME: Final[str] = "name"
CONF_PV_PRODUCTION_ENTITY: Final[str] = "pv_production_entity"
CONF_GRID_EXPORT_ENTITY: Final[str] = "grid_export_entity"
CONF_GRID_IMPORT_ENTITY: Final[str] = "grid_import_entity"
CONF_CONSUMPTION_ENTITY: Final[str] = "consumption_entity"

# --- Neue Sensoren für Empfehlungslogik ---------------------------------------
CONF_BATTERY_SOC_ENTITY: Final[str] = "battery_soc_entity"
CONF_PV_POWER_ENTITY: Final[str] = "pv_power_entity"
CONF_PV_FORECAST_ENTITY: Final[str] = "pv_forecast_entity"

# --- EPEX Spot Integration ----------------------------------------------------
CONF_EPEX_PRICE_ENTITY: Final[str] = "epex_price_entity"
CONF_EPEX_QUANTILE_ENTITY: Final[str] = "epex_quantile_entity"

# --- Solcast Integration ------------------------------------------------------
CONF_SOLCAST_FORECAST_ENTITY: Final[str] = "solcast_forecast_entity"

# --- Option keys (können später geändert werden) ------------------------------
CONF_ELECTRICITY_PRICE: Final[str] = "electricity_price"
CONF_ELECTRICITY_PRICE_ENTITY: Final[str] = "electricity_price_entity"
CONF_ELECTRICITY_PRICE_UNIT: Final[str] = "electricity_price_unit"
CONF_FEED_IN_TARIFF: Final[str] = "feed_in_tariff"
CONF_FEED_IN_TARIFF_ENTITY: Final[str] = "feed_in_tariff_entity"
CONF_FEED_IN_TARIFF_UNIT: Final[str] = "feed_in_tariff_unit"

# --- Preis-Einheiten ----------------------------------------------------------
PRICE_UNIT_EUR: Final[str] = "eur"
PRICE_UNIT_CENT: Final[str] = "cent"
CONF_INSTALLATION_COST: Final[str] = "installation_cost"
CONF_SAVINGS_OFFSET: Final[str] = "savings_offset"
CONF_ENERGY_OFFSET_SELF: Final[str] = "energy_offset_self_consumption"
CONF_ENERGY_OFFSET_EXPORT: Final[str] = "energy_offset_export"
CONF_INSTALLATION_DATE: Final[str] = "installation_date"

# --- Empfehlungs-Schwellwerte -------------------------------------------------
CONF_BATTERY_SOC_HIGH: Final[str] = "battery_soc_high"
CONF_BATTERY_SOC_LOW: Final[str] = "battery_soc_low"
CONF_PRICE_HIGH_THRESHOLD: Final[str] = "price_high_threshold"
CONF_PRICE_LOW_THRESHOLD: Final[str] = "price_low_threshold"
CONF_PV_POWER_HIGH: Final[str] = "pv_power_high"

# --- Defaults -----------------------------------------------------------------
DEFAULT_NAME: Final[str] = "PV Management"
DEFAULT_ELECTRICITY_PRICE: Final[float] = 0.35  # €/kWh
DEFAULT_ELECTRICITY_PRICE_UNIT: Final[str] = PRICE_UNIT_EUR
DEFAULT_FEED_IN_TARIFF: Final[float] = 0.08  # €/kWh
DEFAULT_FEED_IN_TARIFF_UNIT: Final[str] = PRICE_UNIT_EUR
DEFAULT_INSTALLATION_COST: Final[float] = 10000.0  # €
DEFAULT_SAVINGS_OFFSET: Final[float] = 0.0  # € bereits amortisiert
DEFAULT_ENERGY_OFFSET_SELF: Final[float] = 0.0  # kWh Eigenverbrauch vor Tracking
DEFAULT_ENERGY_OFFSET_EXPORT: Final[float] = 0.0  # kWh Export vor Tracking

# Empfehlungs-Defaults
DEFAULT_BATTERY_SOC_HIGH: Final[float] = 80.0  # % - Batterie "voll"
DEFAULT_BATTERY_SOC_LOW: Final[float] = 20.0   # % - Batterie "leer"
DEFAULT_PRICE_HIGH_THRESHOLD: Final[float] = 0.30  # €/kWh - teuer
DEFAULT_PRICE_LOW_THRESHOLD: Final[float] = 0.15   # €/kWh - günstig
DEFAULT_PV_POWER_HIGH: Final[float] = 1000.0  # W - viel PV

# --- Ranges für Config Flow / Options -----------------------------------------
RANGE_PRICE_EUR: Final[dict] = {"min": 0.01, "max": 1.0, "step": 0.001}
RANGE_PRICE_CENT: Final[dict] = {"min": 1.0, "max": 100.0, "step": 0.01}
RANGE_TARIFF_EUR: Final[dict] = {"min": 0.0, "max": 0.5, "step": 0.001}
RANGE_TARIFF_CENT: Final[dict] = {"min": 0.0, "max": 50.0, "step": 0.01}
RANGE_COST: Final[dict] = {"min": 0.0, "max": 200000.0, "step": 1.0}
RANGE_OFFSET: Final[dict] = {"min": 0.0, "max": 100000.0, "step": 0.01}
RANGE_ENERGY_OFFSET: Final[dict] = {"min": 0.0, "max": 500000.0, "step": 0.01}
RANGE_BATTERY_SOC: Final[dict] = {"min": 0.0, "max": 100.0, "step": 1.0}
RANGE_PV_POWER: Final[dict] = {"min": 0.0, "max": 50000.0, "step": 1.0}

# --- Empfehlungs-Zustände -----------------------------------------------------
RECOMMENDATION_DARK_GREEN: Final[str] = "dark_green"
RECOMMENDATION_GREEN: Final[str] = "green"
RECOMMENDATION_YELLOW: Final[str] = "yellow"
RECOMMENDATION_RED: Final[str] = "red"
