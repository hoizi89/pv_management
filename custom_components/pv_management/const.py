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
CONF_PV_PEAK_POWER: Final[str] = "pv_peak_power"
CONF_WINTER_BASE_LOAD: Final[str] = "winter_base_load"

# --- Auto-Charge (Batterie automatisch laden) ---------------------------------
CONF_AUTO_CHARGE_ENABLED: Final[str] = "auto_charge_enabled"
CONF_AUTO_CHARGE_WINTER_ONLY: Final[str] = "auto_charge_winter_only"
CONF_AUTO_CHARGE_PV_THRESHOLD: Final[str] = "auto_charge_pv_threshold"
CONF_AUTO_CHARGE_PRICE_QUANTILE: Final[str] = "auto_charge_price_quantile"
CONF_AUTO_CHARGE_MIN_SOC: Final[str] = "auto_charge_min_soc"
# REMOVED: CONF_AUTO_CHARGE_TARGET_SOC - now uses CONF_BATTERY_TARGET_SOC
CONF_AUTO_CHARGE_MIN_PRICE_DIFF: Final[str] = "auto_charge_min_price_diff"
CONF_AUTO_CHARGE_POWER: Final[str] = "auto_charge_power"

# --- Gemeinsame Batterie-Einstellung (für Auto-Charge UND Entlade-Steuerung) --
CONF_BATTERY_TARGET_SOC: Final[str] = "battery_target_soc"  # Ziel-SOC / Halte-SOC

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
DEFAULT_PV_POWER_HIGH: Final[float] = 1000.0  # W - viel PV (Fallback)
DEFAULT_PV_PEAK_POWER: Final[float] = 10000.0  # W - 10kWp Anlage
DEFAULT_WINTER_BASE_LOAD: Final[float] = 0.0  # W - Grundlast Winter (z.B. Wärmepumpe)

# Auto-Charge Defaults
DEFAULT_AUTO_CHARGE_ENABLED: Final[bool] = False
DEFAULT_AUTO_CHARGE_WINTER_ONLY: Final[bool] = True  # Nur im Winter laden (Okt-März)
DEFAULT_AUTO_CHARGE_PV_THRESHOLD: Final[float] = 5.0  # kWh - unter dieser Prognose wird geladen
DEFAULT_AUTO_CHARGE_PRICE_QUANTILE: Final[float] = 0.3  # 0-1, unter diesem Wert ist "günstig"
DEFAULT_AUTO_CHARGE_MIN_SOC: Final[float] = 30.0  # % - nur laden wenn SOC unter diesem Wert
DEFAULT_AUTO_CHARGE_MIN_PRICE_DIFF: Final[float] = 15.0  # ct/kWh - min. Differenz (Ladeverlust + Batterie/WR-Verschleiß)
DEFAULT_AUTO_CHARGE_POWER: Final[float] = 3000.0  # W - Ladeleistung beim Auto-Charge

# Gemeinsamer Default für Ziel/Halte-SOC
DEFAULT_BATTERY_TARGET_SOC: Final[float] = 100.0  # % - Ziel-SOC für Laden UND Halten

# --- Amortisation Helper Sync -------------------------------------------------
CONF_AMORTISATION_HELPER: Final[str] = "amortisation_helper"
CONF_RESTORE_FROM_HELPER: Final[str] = "restore_from_helper"

# --- Fixpreis-Vergleich -------------------------------------------------------
CONF_FIXED_PRICE_COMPARE: Final[str] = "fixed_price_compare"  # Fixpreis zum Vergleich (ct/kWh)

# --- Discharge Control (Entlade-Steuerung) ------------------------------------
CONF_DISCHARGE_ENABLED: Final[str] = "discharge_enabled"
CONF_DISCHARGE_WINTER_ONLY: Final[str] = "discharge_winter_only"
CONF_DISCHARGE_PRICE_QUANTILE: Final[str] = "discharge_price_quantile"
# REMOVED: CONF_DISCHARGE_HOLD_SOC - now uses CONF_BATTERY_TARGET_SOC
CONF_DISCHARGE_ALLOW_SOC: Final[str] = "discharge_allow_soc"
CONF_DISCHARGE_SUMMER_SOC: Final[str] = "discharge_summer_soc"

# Fixpreis-Vergleich Default (Energie AG Angebot)
DEFAULT_FIXED_PRICE_COMPARE: Final[float] = 13.9  # ct/kWh

# Discharge Defaults
DEFAULT_DISCHARGE_ENABLED: Final[bool] = False
DEFAULT_DISCHARGE_WINTER_ONLY: Final[bool] = True  # Nur im Winter aktiv (Okt-März)
DEFAULT_DISCHARGE_PRICE_QUANTILE: Final[float] = 0.7  # 0-1, über diesem Wert ist "teuer" → entladen
# REMOVED: DEFAULT_DISCHARGE_HOLD_SOC - now uses DEFAULT_BATTERY_TARGET_SOC
DEFAULT_DISCHARGE_ALLOW_SOC: Final[float] = 20.0  # % - Batterie kann bis hierhin entladen werden
DEFAULT_DISCHARGE_SUMMER_SOC: Final[float] = 10.0  # % - Im Sommer normale Entladung (10%)

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
RECOMMENDATION_ORANGE: Final[str] = "orange"
RECOMMENDATION_RED: Final[str] = "red"
