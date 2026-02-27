from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Any

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    DOMAIN, DATA_CTRL, PLATFORMS,
    CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
    CONF_BATTERY_SOC_ENTITY, CONF_PV_POWER_ENTITY, CONF_PV_FORECAST_ENTITY,
    CONF_ELECTRICITY_PRICE, CONF_ELECTRICITY_PRICE_ENTITY, CONF_ELECTRICITY_PRICE_UNIT,
    CONF_FEED_IN_TARIFF, CONF_FEED_IN_TARIFF_ENTITY, CONF_FEED_IN_TARIFF_UNIT,
    CONF_INSTALLATION_COST, CONF_INSTALLATION_DATE, CONF_SAVINGS_OFFSET,
    CONF_BATTERY_SOC_HIGH, CONF_BATTERY_SOC_LOW,
    CONF_PRICE_HIGH_THRESHOLD, CONF_PRICE_LOW_THRESHOLD, CONF_PV_POWER_HIGH,
    CONF_PV_PEAK_POWER, CONF_WINTER_BASE_LOAD,
    CONF_EPEX_PRICE_ENTITY, CONF_EPEX_QUANTILE_ENTITY, CONF_SOLCAST_FORECAST_ENTITY,
    CONF_AUTO_CHARGE_ENABLED, CONF_AUTO_CHARGE_WINTER_ONLY, CONF_AUTO_CHARGE_PV_THRESHOLD,
    CONF_AUTO_CHARGE_PRICE_QUANTILE, CONF_AUTO_CHARGE_MIN_SOC,
    CONF_AUTO_CHARGE_MIN_PRICE_DIFF, CONF_AUTO_CHARGE_POWER,
    CONF_BATTERY_TARGET_SOC,  # Gemeinsame Einstellung für Ziel/Halte-SOC
    CONF_DISCHARGE_ENABLED, CONF_DISCHARGE_WINTER_ONLY, CONF_DISCHARGE_PRICE_QUANTILE,
    CONF_DISCHARGE_ALLOW_SOC, CONF_DISCHARGE_SUMMER_SOC,
    CONF_AMORTISATION_HELPER, CONF_RESTORE_FROM_HELPER,  # NEU: Helper Sync
    CONF_FIXED_PRICE_COMPARE,  # NEU: Fixpreis-Vergleich
    DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    DEFAULT_BATTERY_SOC_HIGH, DEFAULT_BATTERY_SOC_LOW,
    DEFAULT_PRICE_HIGH_THRESHOLD, DEFAULT_PRICE_LOW_THRESHOLD, DEFAULT_PV_POWER_HIGH,
    DEFAULT_PV_PEAK_POWER, DEFAULT_WINTER_BASE_LOAD,
    DEFAULT_AUTO_CHARGE_ENABLED, DEFAULT_AUTO_CHARGE_WINTER_ONLY, DEFAULT_AUTO_CHARGE_PV_THRESHOLD,
    DEFAULT_AUTO_CHARGE_PRICE_QUANTILE, DEFAULT_AUTO_CHARGE_MIN_SOC,
    DEFAULT_AUTO_CHARGE_MIN_PRICE_DIFF, DEFAULT_AUTO_CHARGE_POWER,
    DEFAULT_BATTERY_TARGET_SOC,  # Gemeinsamer Default
    DEFAULT_DISCHARGE_ENABLED, DEFAULT_DISCHARGE_WINTER_ONLY, DEFAULT_DISCHARGE_PRICE_QUANTILE,
    DEFAULT_DISCHARGE_ALLOW_SOC, DEFAULT_DISCHARGE_SUMMER_SOC,
    DEFAULT_FIXED_PRICE_COMPARE,  # NEU
    PRICE_UNIT_CENT,
    RECOMMENDATION_DARK_GREEN, RECOMMENDATION_GREEN, RECOMMENDATION_YELLOW, RECOMMENDATION_ORANGE, RECOMMENDATION_RED,
    CONF_BENCHMARK_ENABLED, CONF_BENCHMARK_HOUSEHOLD_SIZE, CONF_BENCHMARK_COUNTRY,
    CONF_BENCHMARK_HEATPUMP, CONF_BENCHMARK_HEATPUMP_ENTITY,
    DEFAULT_BENCHMARK_ENABLED, DEFAULT_BENCHMARK_HOUSEHOLD_SIZE, DEFAULT_BENCHMARK_COUNTRY,
    DEFAULT_BENCHMARK_HEATPUMP,
    BENCHMARK_CONSUMPTION, BENCHMARK_HEATPUMP_CONSUMPTION, BENCHMARK_CO2_FACTORS,
    PV_STRING_CONFIGS,
)

_LOGGER = logging.getLogger(__name__)

# CO2 Faktor für deutschen Strommix (kg CO2 pro kWh)
CO2_FACTOR_GRID = 0.4


class PVManagementController:
    """
    Controller für PV-Management.

    Features:
    - Amortisationsberechnung (inkrementell für dynamische Preise)
    - Stromverbrauch-Empfehlung (Ampel basierend auf PV, Batterie, Preis)
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry

        # Konfigurierbare Werte (aus Options, fallback zu data)
        self._load_options()

        # Aktuelle Sensor-Werte (für Delta-Berechnung)
        self._last_pv_production_kwh: float | None = None
        self._last_grid_export_kwh: float | None = None
        self._last_grid_import_kwh: float | None = None
        self._last_consumption_kwh: float | None = None

        # Aktuelle Totals (werden live aktualisiert)
        self._pv_production_kwh = 0.0
        self._grid_export_kwh = 0.0
        self._grid_import_kwh = 0.0
        self._consumption_kwh = 0.0

        # Aktuelle Live-Werte für Empfehlung
        self._battery_soc = 0.0  # %
        self._pv_power = 0.0     # W
        self._pv_forecast = 0.0  # kWh

        # EPEX Spot Werte
        self._epex_price = 0.0       # €/kWh (aktueller EPEX Preis)
        self._epex_quantile = 0.5    # 0-1 (0=günstigster, 1=teuerster Preis des Tages)
        self._epex_price_forecast: list[dict] = []  # Preisprognose aus data Attribut

        # Solcast Werte
        self._solcast_forecast_today = 0.0  # kWh Prognose heute
        self._solcast_hourly_forecast: list[dict] = []  # Stündliche Prognose

        # Letzte bekannte Preise (für Fallback wenn Sensor temporär nicht verfügbar)
        self._last_known_electricity_price: float | None = None
        self._last_known_feed_in_tariff: float | None = None
        self._price_sensor_available = True
        self._tariff_sensor_available = True
        self._price_fallback_logged = False  # Nur einmal loggen
        self._tariff_fallback_logged = False

        # INKREMENTELL berechnete Werte (werden persistent gespeichert)
        self._total_self_consumption_kwh = 0.0
        self._total_feed_in_kwh = 0.0
        self._accumulated_savings_self = 0.0
        self._accumulated_earnings_feed = 0.0

        # Strompreis-Tracking für Durchschnittsberechnung (gewichtet nach Verbrauch)
        self._total_grid_import_cost = 0.0  # Gesamtkosten Netzbezug in €
        self._tracked_grid_import_kwh = 0.0  # Netzbezug für Durchschnittsberechnung

        # Tägliches Strompreis-Tracking
        self._daily_grid_import_cost = 0.0
        self._daily_grid_import_kwh = 0.0
        self._daily_feed_in_earnings = 0.0
        self._daily_feed_in_kwh = 0.0
        self._daily_tracking_date: date | None = None

        # Monatliches Strompreis-Tracking
        self._monthly_grid_import_cost = 0.0
        self._monthly_grid_import_kwh = 0.0
        self._monthly_tracking_month: int | None = None  # 1-12

        # Auto-Charge Statistiken
        self._auto_charge_count = 0  # Anzahl Aktivierungen
        self._auto_charge_total_hours = 0.0  # Gesamte Ladezeit in Stunden
        self._auto_charge_total_kwh = 0.0  # Geladene kWh durch Auto-Charge
        self._auto_charge_estimated_savings = 0.0  # Geschätzte Ersparnis in €
        self._auto_charge_last_start = None  # Zeitpunkt des letzten Starts
        self._auto_charge_was_active = False  # War Auto-Charge im letzten Zyklus aktiv?
        self._is_auto_charging = False  # Hysterese: Läuft gerade ein Ladevorgang?

        # Flag ob Werte aus Restore geladen wurden
        self._restored = False
        self._first_seen_date: date | None = None

        # Notification Tracking (verhindert Spam)
        self._milestones_fired: set[int] = set()
        self._monthly_summary_month: int | None = None

        # Wärmepumpe Delta-Tracking (persistent über Neustarts)
        self._last_wp_kwh: float | None = None
        self._tracked_wp_kwh = 0.0
        self._wp_first_seen_date: date | None = None

        # Benchmark-Startpunkte (Snapshot bei Reset/Erststart)
        self._benchmark_start_date: date | None = None
        self._benchmark_start_self_consumption: float = 0.0
        self._benchmark_start_grid_import: float = 0.0
        self._benchmark_start_feed_in: float = 0.0

        # PV-String Delta-Tracking
        self._string_last_kwh: dict[str, float | None] = {}
        self._string_tracked_kwh: dict[str, float] = {}
        self._string_first_seen_date: date | None = None
        self._string_peak_w: dict[str, float] = {}

        # Monatliche Buckets für Rolling-12-Month (Ring-Buffer)
        # Key: Monat (1-12), Value: dict mit Energiewerten
        self._monthly_buckets: dict[int, dict[str, float]] = {}
        self._monthly_bucket_month: int | None = None

        # Listener
        self._remove_listeners = []
        self._entity_listeners = []

    def _load_options(self):
        """Lädt Optionen aus Entry (Options überschreiben Data)."""
        opts = {**self.entry.data, **self.entry.options}

        # Sensor-Entities (können nachträglich geändert werden)
        self.pv_production_entity = opts.get(CONF_PV_PRODUCTION_ENTITY)
        self.grid_export_entity = opts.get(CONF_GRID_EXPORT_ENTITY)
        self.grid_import_entity = opts.get(CONF_GRID_IMPORT_ENTITY)
        self.consumption_entity = opts.get(CONF_CONSUMPTION_ENTITY)

        # Neue Entities für Empfehlungslogik
        self.battery_soc_entity = opts.get(CONF_BATTERY_SOC_ENTITY)
        self.pv_power_entity = opts.get(CONF_PV_POWER_ENTITY)
        self.pv_forecast_entity = opts.get(CONF_PV_FORECAST_ENTITY)

        # EPEX Spot Entities
        self.epex_price_entity = opts.get(CONF_EPEX_PRICE_ENTITY)
        self.epex_quantile_entity = opts.get(CONF_EPEX_QUANTILE_ENTITY)

        # Solcast Entity
        self.solcast_forecast_entity = opts.get(CONF_SOLCAST_FORECAST_ENTITY)

        # Preis-Konfiguration
        self.electricity_price = opts.get(CONF_ELECTRICITY_PRICE, DEFAULT_ELECTRICITY_PRICE)
        self.electricity_price_entity = opts.get(CONF_ELECTRICITY_PRICE_ENTITY)
        self.electricity_price_unit = opts.get(CONF_ELECTRICITY_PRICE_UNIT, DEFAULT_ELECTRICITY_PRICE_UNIT)
        self.feed_in_tariff = opts.get(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)
        self.feed_in_tariff_entity = opts.get(CONF_FEED_IN_TARIFF_ENTITY)
        self.feed_in_tariff_unit = opts.get(CONF_FEED_IN_TARIFF_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT)

        # Kosten und Datum
        self.installation_cost = opts.get(CONF_INSTALLATION_COST, DEFAULT_INSTALLATION_COST)
        self.installation_date = opts.get(CONF_INSTALLATION_DATE)
        self.savings_offset = opts.get(CONF_SAVINGS_OFFSET, DEFAULT_SAVINGS_OFFSET)

        # Empfehlungs-Schwellwerte
        self.battery_soc_high = opts.get(CONF_BATTERY_SOC_HIGH, DEFAULT_BATTERY_SOC_HIGH)
        self.battery_soc_low = opts.get(CONF_BATTERY_SOC_LOW, DEFAULT_BATTERY_SOC_LOW)
        self.price_high_threshold = opts.get(CONF_PRICE_HIGH_THRESHOLD, DEFAULT_PRICE_HIGH_THRESHOLD)
        self.price_low_threshold = opts.get(CONF_PRICE_LOW_THRESHOLD, DEFAULT_PRICE_LOW_THRESHOLD)
        self.pv_power_high = opts.get(CONF_PV_POWER_HIGH, DEFAULT_PV_POWER_HIGH)
        self.pv_peak_power = opts.get(CONF_PV_PEAK_POWER, DEFAULT_PV_PEAK_POWER)
        self.winter_base_load = opts.get(CONF_WINTER_BASE_LOAD, DEFAULT_WINTER_BASE_LOAD)

        # Gemeinsame Batterie-Einstellung (für Auto-Charge UND Entlade-Steuerung)
        # Migration: Alte Einstellungen werden auch unterstützt
        self.battery_target_soc = opts.get(
            CONF_BATTERY_TARGET_SOC,
            opts.get("auto_charge_target_soc",  # Legacy fallback
                opts.get("discharge_hold_soc",  # Legacy fallback
                    DEFAULT_BATTERY_TARGET_SOC))
        )

        # Auto-Charge Einstellungen
        self.auto_charge_enabled = opts.get(CONF_AUTO_CHARGE_ENABLED, DEFAULT_AUTO_CHARGE_ENABLED)
        self.auto_charge_winter_only = opts.get(CONF_AUTO_CHARGE_WINTER_ONLY, DEFAULT_AUTO_CHARGE_WINTER_ONLY)
        self.auto_charge_pv_threshold = opts.get(CONF_AUTO_CHARGE_PV_THRESHOLD, DEFAULT_AUTO_CHARGE_PV_THRESHOLD)
        self.auto_charge_price_quantile = opts.get(CONF_AUTO_CHARGE_PRICE_QUANTILE, DEFAULT_AUTO_CHARGE_PRICE_QUANTILE)
        self.auto_charge_min_soc = opts.get(CONF_AUTO_CHARGE_MIN_SOC, DEFAULT_AUTO_CHARGE_MIN_SOC)
        self.auto_charge_min_price_diff = opts.get(CONF_AUTO_CHARGE_MIN_PRICE_DIFF, DEFAULT_AUTO_CHARGE_MIN_PRICE_DIFF)
        self.auto_charge_power = opts.get(CONF_AUTO_CHARGE_POWER, DEFAULT_AUTO_CHARGE_POWER)

        # Discharge Control Einstellungen (Entlade-Steuerung)
        self.discharge_enabled = opts.get(CONF_DISCHARGE_ENABLED, DEFAULT_DISCHARGE_ENABLED)
        self.discharge_winter_only = opts.get(CONF_DISCHARGE_WINTER_ONLY, DEFAULT_DISCHARGE_WINTER_ONLY)
        self.discharge_price_quantile = opts.get(CONF_DISCHARGE_PRICE_QUANTILE, DEFAULT_DISCHARGE_PRICE_QUANTILE)
        self.discharge_allow_soc = opts.get(CONF_DISCHARGE_ALLOW_SOC, DEFAULT_DISCHARGE_ALLOW_SOC)
        self.discharge_summer_soc = opts.get(CONF_DISCHARGE_SUMMER_SOC, DEFAULT_DISCHARGE_SUMMER_SOC)

        # Fixpreis-Vergleich (ct/kWh → €/kWh)
        self.fixed_price_compare = opts.get(CONF_FIXED_PRICE_COMPARE, DEFAULT_FIXED_PRICE_COMPARE) / 100.0

        # Amortisation Helper (Pflicht für Persistenz)
        self.amortisation_helper = opts.get(CONF_AMORTISATION_HELPER)
        self.restore_from_helper = opts.get(CONF_RESTORE_FROM_HELPER, False)

        # Aliase für Rückwärtskompatibilität
        self.auto_charge_target_soc = self.battery_target_soc
        self.discharge_hold_soc = self.battery_target_soc

        # Benchmark
        self.benchmark_enabled = opts.get(CONF_BENCHMARK_ENABLED, DEFAULT_BENCHMARK_ENABLED)
        self.benchmark_household_size = opts.get(CONF_BENCHMARK_HOUSEHOLD_SIZE, DEFAULT_BENCHMARK_HOUSEHOLD_SIZE)
        self.benchmark_country = opts.get(CONF_BENCHMARK_COUNTRY, DEFAULT_BENCHMARK_COUNTRY)
        self.benchmark_heatpump = opts.get(CONF_BENCHMARK_HEATPUMP, DEFAULT_BENCHMARK_HEATPUMP)
        self.benchmark_heatpump_entity = opts.get(CONF_BENCHMARK_HEATPUMP_ENTITY)

        # PV-Strings
        self.pv_strings = []  # list of (name, energy_entity_id, power_entity_id_or_None)
        for name_key, entity_key, power_key, kwp_key in PV_STRING_CONFIGS:
            s_name = opts.get(name_key, "").strip()
            s_entity = opts.get(entity_key)
            s_power = opts.get(power_key)
            s_kwp = opts.get(kwp_key, 0.0)
            try:
                s_kwp = float(s_kwp) if s_kwp else 0.0
            except (ValueError, TypeError):
                s_kwp = 0.0
            if s_name and s_entity:
                self.pv_strings.append((s_name, s_entity, s_power, s_kwp))
        self._string_entity_ids = {e for _, e, _, _ in self.pv_strings}
        self._string_power_entity_ids = {p for _, _, p, _ in self.pv_strings if p}

    @property
    def is_winter(self) -> bool:
        """Prüft ob aktuell Winter ist (Oktober bis März)."""
        month = datetime.now().month
        return month >= 10 or month <= 3

    @property
    def effective_pv_power(self) -> float:
        """Effektive PV-Leistung nach Abzug der Winter-Grundlast."""
        pv = self._pv_power
        if self.is_winter and self.winter_base_load > 0:
            pv = max(0, pv - self.winter_base_load)
        return pv

    def _convert_price_to_eur(self, price: float, unit: str, auto_detect: bool = False) -> float:
        """
        Konvertiert Preis zu Euro/kWh (von Cent falls nötig).

        Bei auto_detect=True wird anhand des Wertes erkannt:
        - Wert > 1.0 → wahrscheinlich Cent/kWh → durch 100 teilen
        - Wert <= 1.0 → wahrscheinlich Euro/kWh → direkt verwenden
        """
        if auto_detect:
            # Automatische Erkennung: Werte > 1 sind vermutlich in Cent
            if price > 1.0:
                _LOGGER.debug("Auto-detect: Preis %.2f > 1, interpretiere als Cent/kWh", price)
                return price / 100.0
            else:
                _LOGGER.debug("Auto-detect: Preis %.4f <= 1, interpretiere als Euro/kWh", price)
                return price

        # Manuelle Einstellung
        if unit == PRICE_UNIT_CENT:
            return price / 100.0
        return price

    def _get_entity_value(self, entity_id: str | None, fallback: float = 0.0) -> tuple[float, bool]:
        """
        Holt Wert von Entity oder verwendet Fallback.

        Returns: (value, is_available)
        """
        if not entity_id:
            return fallback, True  # Config-Wert ist immer "verfügbar"

        state = self.hass.states.get(entity_id)
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                return float(state.state), True
            except (ValueError, TypeError):
                pass
        return fallback, False

    @property
    def current_electricity_price(self) -> float:
        """
        Aktueller Strompreis in €/kWh.

        Fallback-Kette:
        1. Aktueller Sensor-Wert (wenn verfügbar) - AUTO-DETECT Euro/Cent
        2. Letzter bekannter Sensor-Wert (gecached)
        3. Konfigurierter Standardpreis (mit manueller Einheit)
        """
        if self.electricity_price_entity:
            raw_price, is_available = self._get_entity_value(
                self.electricity_price_entity, self.electricity_price
            )
            self._price_sensor_available = is_available

            if is_available:
                # Sensor verfügbar - AUTO-DETECT ob Euro oder Cent
                self._last_known_electricity_price = raw_price
                self._price_fallback_logged = False  # Reset für nächstes Mal
                return self._convert_price_to_eur(raw_price, self.electricity_price_unit, auto_detect=True)
            elif self._last_known_electricity_price is not None:
                # Sensor nicht verfügbar, aber wir haben einen gecachten Wert
                return self._convert_price_to_eur(self._last_known_electricity_price, self.electricity_price_unit, auto_detect=True)
            else:
                # Kein gecachter Wert, verwende Config-Fallback (manuelle Einheit)
                if not self._price_fallback_logged:
                    _LOGGER.info("Strompreis-Sensor nicht verfügbar, verwende Konfigurationswert")
                    self._price_fallback_logged = True
                return self._convert_price_to_eur(self.electricity_price, self.electricity_price_unit, auto_detect=False)
        else:
            # Kein Sensor konfiguriert, verwende Config-Wert (manuelle Einheit)
            self._price_sensor_available = True
            return self._convert_price_to_eur(self.electricity_price, self.electricity_price_unit, auto_detect=False)

    @property
    def current_feed_in_tariff(self) -> float:
        """
        Aktuelle Einspeisevergütung in €/kWh.

        Fallback-Kette wie bei current_electricity_price.
        AUTO-DETECT für Sensor-Werte, manuelle Einheit für Fallback.
        """
        if self.feed_in_tariff_entity:
            raw_tariff, is_available = self._get_entity_value(
                self.feed_in_tariff_entity, self.feed_in_tariff
            )
            self._tariff_sensor_available = is_available

            if is_available:
                self._last_known_feed_in_tariff = raw_tariff
                self._tariff_fallback_logged = False  # Reset für nächstes Mal
                return self._convert_price_to_eur(raw_tariff, self.feed_in_tariff_unit, auto_detect=True)
            elif self._last_known_feed_in_tariff is not None:
                # Sensor nicht verfügbar, aber wir haben einen gecachten Wert
                return self._convert_price_to_eur(self._last_known_feed_in_tariff, self.feed_in_tariff_unit, auto_detect=True)
            else:
                if not self._tariff_fallback_logged:
                    _LOGGER.info("Einspeise-Tarif-Sensor nicht verfügbar, verwende Konfigurationswert")
                    self._tariff_fallback_logged = True
                return self._convert_price_to_eur(self.feed_in_tariff, self.feed_in_tariff_unit, auto_detect=False)
        else:
            self._tariff_sensor_available = True
            return self._convert_price_to_eur(self.feed_in_tariff, self.feed_in_tariff_unit, auto_detect=False)

    @property
    def electricity_price_source(self) -> str:
        """Zeigt die Quelle des aktuellen Strompreises."""
        if not self.electricity_price_entity:
            return "config"
        elif self._price_sensor_available:
            return "sensor"
        elif self._last_known_electricity_price is not None:
            return "cached"
        else:
            return "fallback"

    @property
    def feed_in_tariff_source(self) -> str:
        """Zeigt die Quelle des aktuellen Tarifs."""
        if not self.feed_in_tariff_entity:
            return "config"
        elif self._tariff_sensor_available:
            return "sensor"
        elif self._last_known_feed_in_tariff is not None:
            return "cached"
        else:
            return "fallback"

    @property
    def battery_soc(self) -> float:
        """Aktueller Batterie-Ladestand in %."""
        return self._battery_soc

    @property
    def pv_power(self) -> float:
        """Aktuelle PV-Leistung in W."""
        return self._pv_power

    @property
    def pv_forecast(self) -> float:
        """PV-Prognose in kWh."""
        return self._pv_forecast

    @property
    def epex_price(self) -> float:
        """Aktueller EPEX Spot Preis in €/kWh."""
        return self._epex_price

    @property
    def epex_quantile(self) -> float:
        """
        EPEX Quantile (0-1).
        0 = günstigster Preis des Tages
        1 = teuerster Preis des Tages
        """
        return self._epex_quantile

    @property
    def epex_price_forecast(self) -> list[dict]:
        """EPEX Preisprognose (aus data Attribut)."""
        return self._epex_price_forecast

    @property
    def solcast_forecast_today(self) -> float:
        """Solcast PV-Prognose für heute in kWh."""
        return self._solcast_forecast_today

    @property
    def solcast_hourly_forecast(self) -> list[dict]:
        """Solcast stündliche Prognose (aus detailedHourly Attribut)."""
        return self._solcast_hourly_forecast

    @property
    def has_epex_integration(self) -> bool:
        """Prüft ob EPEX Spot konfiguriert ist."""
        return bool(self.epex_quantile_entity or self.epex_price_entity)

    @property
    def has_solcast_integration(self) -> bool:
        """Prüft ob Solcast konfiguriert ist."""
        return bool(self.solcast_forecast_entity)

    # =========================================================================
    # AUTO-CHARGE LOGIK
    # =========================================================================

    @property
    def should_auto_charge(self) -> bool:
        """
        Prüft ob die Batterie jetzt automatisch geladen werden sollte.

        Bedingungen:
        1. Auto-Charge ist aktiviert
        2. Winter-Only: Nur im Winter laden (Okt-März) wenn aktiviert
        3. PV-Prognose ist unter dem Schwellwert (schlechtes Wetter erwartet)
        4. Strompreis ist günstig (Quantile unter Schwellwert)
        5. Batterie-SOC ist unter dem Minimum (Start) oder unter Ziel (Weiterladen)
        6. Preisdifferenz zwischen billig/teuer ist groß genug

        Hysterese: Einmal gestartet, wird bis target_soc weitergeladen.
        """
        if not self.auto_charge_enabled:
            self._is_auto_charging = False
            return False

        # Winter-Only Prüfung
        if self.auto_charge_winter_only and not self.is_winter:
            self._is_auto_charging = False
            return False

        # Prüfe alle Bedingungen
        pv_condition = self._check_pv_condition()
        price_condition = self._check_price_condition()
        soc_condition = self._check_soc_condition()  # Enthält Hysterese-Logik
        price_diff_condition = self._check_price_diff_condition()

        result = pv_condition and price_condition and soc_condition and price_diff_condition

        # Wenn alle Bedingungen erfüllt sind und wir noch nicht laden → Starten
        if result and not self._is_auto_charging:
            self._is_auto_charging = True
            _LOGGER.info("Auto-Charge: Ladevorgang gestartet bei SOC %.0f%%", self._battery_soc)

        # Wenn Preis nicht mehr günstig → Stoppen (auch wenn Ziel nicht erreicht)
        if self._is_auto_charging and not price_condition:
            self._is_auto_charging = False
            _LOGGER.info("Auto-Charge: Preis nicht mehr günstig, Laden pausiert")

        return result

    def _check_pv_condition(self) -> bool:
        """Prüft ob PV-Prognose unter Schwellwert ist."""
        forecast = self._solcast_forecast_today if self.has_solcast_integration else self._pv_forecast
        return forecast < self.auto_charge_pv_threshold

    def _check_price_condition(self) -> bool:
        """Prüft ob Strompreis günstig genug ist."""
        if not self.has_epex_integration:
            # Ohne EPEX: Prüfe absoluten Preis
            return self.current_electricity_price <= self.price_low_threshold

        # Mit EPEX: Prüfe Quantile
        return self._epex_quantile <= self.auto_charge_price_quantile

    def _check_soc_condition(self) -> bool:
        """
        Prüft ob Batterie geladen werden sollte (mit Hysterese).

        - Start: SOC < min_soc (z.B. unter 30%)
        - Stopp: SOC >= target_soc (z.B. bei 80%)

        Dazwischen: Weiterladen bis Ziel erreicht.
        """
        if not self.battery_soc_entity:
            # Ohne Batterie-Sensor: Auto-Charge nicht möglich (Sicherheit!)
            _LOGGER.debug("Auto-Charge: Kein Batterie-Sensor konfiguriert, SOC-Prüfung nicht möglich")
            return False

        current_soc = self._battery_soc

        # Wenn wir bereits laden: Weitermachen bis Ziel erreicht
        if self._is_auto_charging:
            if current_soc >= self.auto_charge_target_soc:
                # Ziel erreicht → Laden beenden
                self._is_auto_charging = False
                _LOGGER.info("Auto-Charge: Ziel-SOC %.0f%% erreicht, Laden beendet", current_soc)
                return False
            else:
                # Noch nicht am Ziel → Weiterladen
                return True

        # Noch nicht am Laden: Nur starten wenn unter Minimum
        if current_soc < self.auto_charge_min_soc:
            return True

        return False

    def _check_price_diff_condition(self) -> bool:
        """Prüft ob die Preisdifferenz groß genug ist um sich zu lohnen."""
        price_diff = self.epex_price_diff_today
        if price_diff is None:
            # Ohne EPEX Daten: Bedingung überspringen
            return True

        # Preisdifferenz in ct/kWh
        return price_diff >= self.auto_charge_min_price_diff

    # =========================================================================
    # DISCHARGE CONTROL (Entlade-Steuerung für teure Stunden)
    # =========================================================================

    @property
    def discharge_is_summer_mode(self) -> bool:
        """Prüft ob Sommer-Modus aktiv ist (normale Entladung)."""
        if not self.discharge_enabled:
            return False
        return self.discharge_winter_only and not self.is_winter

    @property
    def should_discharge(self) -> bool:
        """
        Prüft ob die Batterie jetzt entladen werden sollte (teure Stunden).

        Bedingungen:
        1. Discharge Control ist aktiviert
        2. Winter-Only: Im Sommer → immer False (normale Entladung)
        3. EPEX Quantile ist über dem Schwellwert (teurer Strom)

        Wenn True: Entladungstiefe auf discharge_allow_soc setzen (Batterie kann entladen)
        Wenn False: Entladungstiefe auf discharge_hold_soc setzen (Batterie wird gehalten)
        Im Sommer: Entladungstiefe auf discharge_summer_soc setzen (normal, z.B. 1%)
        """
        if not self.discharge_enabled:
            return False

        # Im Sommer: Normale Entladung, keine Steuerung
        if self.discharge_winter_only and not self.is_winter:
            return False

        if not self.has_epex_integration:
            # Ohne EPEX: Prüfe absoluten Preis
            return self.current_electricity_price >= self.price_high_threshold

        # Mit EPEX: Prüfe Quantile (über Schwellwert = teuer = entladen erlaubt)
        return self._epex_quantile >= self.discharge_price_quantile

    @property
    def discharge_reason(self) -> str:
        """Gibt den Grund für die Entlade-Empfehlung zurück."""
        if not self.discharge_enabled:
            return "Entlade-Steuerung deaktiviert"

        # Sommer-Modus
        if self.discharge_winter_only and not self.is_winter:
            return f"Sommer-Modus (Apr-Sep) → Normal ({self.discharge_summer_soc:.0f}%)"

        if not self.has_epex_integration:
            price_ct = self.current_electricity_price * 100
            threshold_ct = self.price_high_threshold * 100
            if self.current_electricity_price >= self.price_high_threshold:
                return f"Preis teuer ({price_ct:.1f} ct >= {threshold_ct:.1f} ct) → Entladen"
            else:
                return f"Preis günstig ({price_ct:.1f} ct < {threshold_ct:.1f} ct) → Halten"

        # Mit EPEX
        if self._epex_quantile >= self.discharge_price_quantile:
            return f"Preis teuer (Quantile {self._epex_quantile:.2f} >= {self.discharge_price_quantile}) → Entladen"
        else:
            return f"Preis günstig (Quantile {self._epex_quantile:.2f} < {self.discharge_price_quantile}) → Halten"

    @property
    def discharge_target_soc(self) -> float | None:
        """
        Gibt den Ziel-SOC basierend auf Entlade-Empfehlung zurück.

        Wenn Entlade-Steuerung deaktiviert → None (keine Steuerung)
        """
        if not self.discharge_enabled:
            return None  # Keine Steuerung wenn deaktiviert

        # Sommer-Modus: Normale Entladung
        if self.discharge_winter_only and not self.is_winter:
            return self.discharge_summer_soc  # z.B. 10% - normale Entladung im Sommer

        if self.should_discharge:
            return self.discharge_allow_soc  # z.B. 20% - Batterie kann entladen werden
        else:
            return self.discharge_hold_soc  # z.B. 80% - Batterie wird gehalten

    @property
    def epex_price_diff_today(self) -> float | None:
        """
        Berechnet die Preisdifferenz (max - min) für heute in ct/kWh.
        Verwendet die EPEX Preisprognose.
        """
        if not self._epex_price_forecast:
            return None

        try:
            now = datetime.now()
            today = now.date()

            # Filtere Preise für heute
            today_prices = []
            for entry in self._epex_price_forecast:
                entry_time = entry.get("start_time") or entry.get("time")
                if entry_time:
                    if isinstance(entry_time, str):
                        entry_dt = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                    else:
                        entry_dt = entry_time

                    if entry_dt.date() == today:
                        # Versuche verschiedene Preisattribute
                        price_mwh = entry.get("price_eur_per_mwh")
                        price_kwh = entry.get("price_per_kwh")
                        price_generic = entry.get("price")

                        price_ct = None
                        if price_mwh is not None:
                            # EUR/MWh → ct/kWh (÷10)
                            price_ct = price_mwh / 10
                        elif price_kwh is not None:
                            # EUR/kWh → ct/kWh (×100)
                            price_ct = price_kwh * 100
                        elif price_generic is not None:
                            # Heuristik: >10 = wahrscheinlich EUR/MWh, <1 = EUR/kWh, sonst ct/kWh
                            if price_generic > 10:
                                price_ct = price_generic / 10
                            elif price_generic < 1:
                                price_ct = price_generic * 100
                            else:
                                price_ct = price_generic

                        if price_ct is not None:
                            today_prices.append(price_ct)

            if len(today_prices) < 2:
                return None

            price_diff = max(today_prices) - min(today_prices)
            return round(price_diff, 2)

        except Exception as e:
            _LOGGER.debug("Fehler bei Preisdifferenz-Berechnung: %s", e)
            return None

    @property
    def auto_charge_reason(self) -> str:
        """Gibt den Grund für die Auto-Charge Empfehlung zurück."""
        if not self.auto_charge_enabled:
            return "Auto-Charge deaktiviert"

        reasons = []
        blocks = []

        # Winter-Only Prüfung
        if self.auto_charge_winter_only:
            if self.is_winter:
                reasons.append("Winter (Okt-März)")
            else:
                blocks.append("Kein Winter (nur Okt-März aktiv)")

        # PV-Prognose
        forecast = self._solcast_forecast_today if self.has_solcast_integration else self._pv_forecast
        if forecast < self.auto_charge_pv_threshold:
            reasons.append(f"PV-Prognose niedrig ({forecast:.1f} kWh < {self.auto_charge_pv_threshold} kWh)")
        else:
            blocks.append(f"PV-Prognose zu hoch ({forecast:.1f} kWh)")

        # Strompreis
        if self.has_epex_integration:
            if self._epex_quantile <= self.auto_charge_price_quantile:
                reasons.append(f"Preis günstig (Quantile {self._epex_quantile:.2f} ≤ {self.auto_charge_price_quantile})")
            else:
                blocks.append(f"Preis zu hoch (Quantile {self._epex_quantile:.2f})")
        else:
            if self.current_electricity_price <= self.price_low_threshold:
                reasons.append(f"Preis günstig ({self.current_electricity_price*100:.1f} ct)")
            else:
                blocks.append(f"Preis zu hoch ({self.current_electricity_price*100:.1f} ct)")

        # Batterie SOC (mit Hysterese)
        if self.battery_soc_entity:
            if self._is_auto_charging:
                # Ladevorgang läuft bereits
                if self._battery_soc < self.auto_charge_target_soc:
                    reasons.append(f"Ladevorgang aktiv ({self._battery_soc:.0f}% → {self.auto_charge_target_soc}%)")
                else:
                    blocks.append(f"Ziel-SOC erreicht ({self._battery_soc:.0f}%)")
            elif self._battery_soc < self.auto_charge_min_soc:
                reasons.append(f"Batterie niedrig ({self._battery_soc:.0f}% < {self.auto_charge_min_soc}%)")
            else:
                blocks.append(f"Batterie ausreichend ({self._battery_soc:.0f}% ≥ {self.auto_charge_min_soc}%)")
        else:
            blocks.append("Kein Batterie-Sensor konfiguriert")

        # Preisdifferenz
        price_diff = self.epex_price_diff_today
        if price_diff is not None:
            if price_diff >= self.auto_charge_min_price_diff:
                reasons.append(f"Preisdifferenz lohnt ({price_diff:.1f} ct ≥ {self.auto_charge_min_price_diff} ct)")
            else:
                blocks.append(f"Preisdifferenz zu gering ({price_diff:.1f} ct < {self.auto_charge_min_price_diff} ct)")

        if blocks:
            return "Nicht laden: " + ", ".join(blocks)
        elif reasons:
            return "Laden empfohlen: " + ", ".join(reasons)
        else:
            return "Keine Daten verfügbar"

    def track_auto_charge_activity(self) -> None:
        """
        Trackt Auto-Charge Aktivität für Statistiken.
        Sollte regelmäßig aufgerufen werden (z.B. bei jedem Sensor-Update).
        """
        is_active = self.should_auto_charge and self.auto_charge_enabled

        if is_active and not self._auto_charge_was_active:
            # Auto-Charge wurde gerade gestartet
            self._auto_charge_count += 1
            self._auto_charge_last_start = datetime.now()
            _LOGGER.info("Auto-Charge gestartet (#%d)", self._auto_charge_count)

        elif not is_active and self._auto_charge_was_active and self._auto_charge_last_start:
            # Auto-Charge wurde gerade beendet
            duration = datetime.now() - self._auto_charge_last_start
            hours = duration.total_seconds() / 3600
            self._auto_charge_total_hours += hours

            # Schätze geladene kWh (Ladeleistung × Zeit)
            estimated_kwh = (self.auto_charge_power / 1000) * hours
            self._auto_charge_total_kwh += estimated_kwh

            # Schätze Ersparnis (Differenz zwischen billig und Durchschnitt)
            price_diff = self.epex_price_diff_today
            if price_diff:
                # Ersparnis = geladene kWh × (Preisdifferenz - Verluste)
                # Annahme: ~15% Verluste
                net_savings_per_kwh = (price_diff * 0.85) / 100  # ct → €
                savings = estimated_kwh * net_savings_per_kwh
                self._auto_charge_estimated_savings += savings

            _LOGGER.info(
                "Auto-Charge beendet: %.1fh, ~%.1f kWh, ~%.2f€ gespart",
                hours, estimated_kwh, savings if price_diff else 0
            )
            self._auto_charge_last_start = None

        self._auto_charge_was_active = is_active

    @property
    def auto_charge_stats(self) -> dict:
        """Gibt Auto-Charge Statistiken zurück."""
        return {
            "aktivierungen_gesamt": self._auto_charge_count,
            "ladezeit_gesamt_stunden": round(self._auto_charge_total_hours, 1),
            "geladene_kwh_geschaetzt": round(self._auto_charge_total_kwh, 1),
            "ersparnis_geschaetzt_eur": round(self._auto_charge_estimated_savings, 2),
            "aktuell_aktiv": self._auto_charge_was_active,
            "letzter_start": self._auto_charge_last_start.isoformat() if self._auto_charge_last_start else None,
        }

    @property
    def next_cheap_hour(self) -> dict | None:
        """
        Findet die nächste günstige Stunde basierend auf EPEX Preisprognose.
        Verwendet den konfigurierten "Preis günstig" Schwellwert.

        Returns: {"hour": 14, "price": 0.15, "in_hours": 2, "is_cheap": True} oder None
        """
        if not self._epex_price_forecast:
            return None

        try:
            now = datetime.now()
            current_hour = now.hour
            threshold = self.price_low_threshold  # Benutzer-Schwellwert für "günstig"

            # Sammle alle zukünftigen Preise
            upcoming_prices = []

            for entry in self._epex_price_forecast:
                hour = None
                price = None

                if isinstance(entry, dict):
                    # Verschiedene EPEX Formate unterstützen
                    start_time = entry.get("start_time") or entry.get("start") or entry.get("time") or entry.get("datetime")
                    price = (
                        entry.get("price_per_kwh") or      # EPEX Spot Data Integration
                        entry.get("price_eur_per_kwh") or  # Alternatives Format
                        entry.get("price") or              # Generisch
                        entry.get("total_price") or        # Mit Steuern
                        entry.get("marketprice")           # Awattar Format (ct/kWh)
                    )

                    if start_time and price is not None:
                        try:
                            if isinstance(start_time, str):
                                dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                                hour = dt.hour
                            elif hasattr(start_time, 'hour'):
                                hour = start_time.hour
                        except (ValueError, AttributeError):
                            continue

                if hour is not None and price is not None:
                    hours_until = hour - current_hour
                    if hours_until <= 0:
                        hours_until += 24  # Nächster Tag oder jetzt

                    # Nur zukünftige Stunden (nicht die aktuelle)
                    if hours_until > 0 and hours_until <= 24:
                        upcoming_prices.append({
                            "hour": hour,
                            "price": float(price),
                            "in_hours": hours_until,
                            "is_cheap": float(price) <= threshold
                        })

            if not upcoming_prices:
                return None

            # Zuerst: Suche nächste Stunde UNTER dem Schwellwert
            cheap_hours = [p for p in upcoming_prices if p["is_cheap"]]
            if cheap_hours:
                # Sortiere nach Zeit (nächste günstige Stunde zuerst)
                cheap_hours.sort(key=lambda x: x["in_hours"])
                next_cheap = cheap_hours[0]

                # Wenn nächste günstige Stunde ≤12h entfernt → direkt zurückgeben
                if next_cheap["in_hours"] <= 12:
                    return next_cheap

                # Wenn >12h entfernt: zeige günstigste in den nächsten 12h
                next_12h = [p for p in upcoming_prices if p["in_hours"] <= 12]
                if next_12h:
                    next_12h.sort(key=lambda x: x["price"])
                    result = next_12h[0]
                    result["is_fallback_12h"] = True  # Markiere als 12h-Fallback
                    return result

                # Sonst: trotzdem die günstige Stunde zeigen (auch wenn >12h)
                return next_cheap

            # Fallback: Günstigste Stunde in den nächsten 12h
            next_12h = [p for p in upcoming_prices if p["in_hours"] <= 12]
            if next_12h:
                next_12h.sort(key=lambda x: x["price"])
                result = next_12h[0]
                result["is_cheap"] = False
                return result

            # Letzter Fallback: Günstigste Stunde insgesamt
            upcoming_prices.sort(key=lambda x: x["price"])
            result = upcoming_prices[0]
            result["is_cheap"] = False
            return result

        except Exception as e:
            _LOGGER.debug("Fehler bei next_cheap_hour Berechnung: %s", e)
            return None

    @property
    def next_cheap_hour_text(self) -> str:
        """Menschenlesbare Ausgabe der nächsten günstigen Stunde."""
        info = self.next_cheap_hour
        if not info:
            return "Keine Prognose"

        price_ct = info['price'] * 100  # In Cent für bessere Lesbarkeit
        time_str = f"{info['hour']}:00"

        if info.get("is_cheap", False):
            # Unter dem konfigurierten Schwellwert
            if info["in_hours"] == 1:
                return f"In 1h günstig ({time_str}, {price_ct:.1f}ct)"
            else:
                return f"In {info['in_hours']}h günstig ({time_str}, {price_ct:.1f}ct)"
        else:
            # Über Schwellwert, aber günstigste Option
            if info["in_hours"] == 1:
                return f"In 1h am günstigsten ({time_str}, {price_ct:.1f}ct)"
            else:
                return f"In {info['in_hours']}h am günstigsten ({time_str}, {price_ct:.1f}ct)"

    @property
    def next_pv_peak(self) -> dict | None:
        """
        Findet die nächste Stunde mit hoher PV-Produktion (aus Solcast).

        Returns: {"hour": 12, "power_kw": 5.2, "in_hours": 3} oder None
        """
        if not self._solcast_hourly_forecast:
            return None

        try:
            now = datetime.now()
            current_hour = now.hour

            # Minimum 1 kW für "relevante" PV-Produktion
            min_power = 1.0

            upcoming = []
            for entry in self._solcast_hourly_forecast:
                if not isinstance(entry, dict):
                    continue

                # Solcast Format: period_start, pv_estimate (kW)
                period_start = entry.get("period_start")
                power = entry.get("pv_estimate", 0)

                if not period_start or power < min_power:
                    continue

                try:
                    if isinstance(period_start, str):
                        dt = datetime.fromisoformat(period_start.replace("Z", "+00:00"))
                        # Konvertiere zu lokaler Zeit falls nötig
                        if dt.tzinfo:
                            dt = dt.replace(tzinfo=None)
                        hour = dt.hour
                    elif hasattr(period_start, 'hour'):
                        hour = period_start.hour
                    else:
                        continue

                    hours_until = hour - current_hour
                    if hours_until <= 0:
                        hours_until += 24

                    # Nur nächste 12 Stunden
                    if 0 < hours_until <= 12:
                        upcoming.append({
                            "hour": hour,
                            "power_kw": float(power),
                            "in_hours": hours_until
                        })
                except (ValueError, AttributeError):
                    continue

            if not upcoming:
                return None

            # Finde die Stunde mit der höchsten Produktion
            upcoming.sort(key=lambda x: x["power_kw"], reverse=True)
            return upcoming[0]

        except Exception as e:
            _LOGGER.debug("Fehler bei next_pv_peak Berechnung: %s", e)
            return None

    @property
    def next_pv_peak_text(self) -> str:
        """Menschenlesbare Ausgabe der nächsten PV-Peak-Stunde."""
        info = self.next_pv_peak
        if not info:
            return ""

        time_str = f"{info['hour']}:00"
        power = info['power_kw']

        if info["in_hours"] == 1:
            return f"In 1h ca. {power:.0f} kW PV ({time_str})"
        else:
            return f"In {info['in_hours']}h ca. {power:.0f} kW PV ({time_str})"

    @property
    def best_opportunity_text(self) -> str:
        """
        Kombinierter Tipp: PV-Peak oder günstige Stunde - je nachdem was relevanter ist.
        Zeigt PV-Peak wenn tagsüber und gute Prognose, sonst Preis-Tipp.
        """
        pv_info = self.next_pv_peak
        price_info = self.next_cheap_hour

        hour = datetime.now().hour
        is_daytime = 6 <= hour <= 18

        # Tagsüber und gute PV erwartet → PV-Tipp hat Vorrang
        if is_daytime and pv_info and pv_info["power_kw"] >= 2.0:
            return self.next_pv_peak_text

        # Nachts oder wenig PV → Preis-Tipp
        if price_info:
            return self.next_cheap_hour_text

        # Fallback: PV-Tipp wenn vorhanden
        if pv_info:
            return self.next_pv_peak_text

        return ""

    @property
    def pv_production_kwh(self) -> float:
        """Aktuelle PV-Produktion vom Sensor."""
        return self._pv_production_kwh

    @property
    def grid_export_kwh(self) -> float:
        """Aktuelle Netzeinspeisung vom Sensor."""
        return self._grid_export_kwh

    @property
    def grid_import_kwh(self) -> float:
        """Aktueller Netzbezug vom Sensor."""
        return self._grid_import_kwh

    @property
    def tracked_grid_import_kwh(self) -> float:
        """Getrackte Netzbezug-kWh für Durchschnittsberechnung."""
        return self._tracked_grid_import_kwh

    @property
    def total_grid_import_cost(self) -> float:
        """Gesamtkosten Netzbezug in €."""
        return self._total_grid_import_cost

    @property
    def average_electricity_price(self) -> float | None:
        """
        Gewichteter durchschnittlicher Strompreis in €/kWh.
        Berechnet als: Gesamtkosten / Gesamtverbrauch
        """
        if self._tracked_grid_import_kwh <= 0:
            return None
        return self._total_grid_import_cost / self._tracked_grid_import_kwh

    @property
    def average_electricity_price_ct(self) -> float | None:
        """Gewichteter durchschnittlicher Strompreis in ct/kWh."""
        avg = self.average_electricity_price
        if avg is None:
            return None
        return avg * 100

    @property
    def daily_average_price_ct(self) -> float | None:
        """Täglicher gewichteter Durchschnittspreis in ct/kWh."""
        if self._daily_grid_import_kwh <= 0:
            return None
        return (self._daily_grid_import_cost / self._daily_grid_import_kwh) * 100

    @property
    def monthly_average_price_ct(self) -> float | None:
        """Monatlicher gewichteter Durchschnittspreis in ct/kWh."""
        if self._monthly_grid_import_kwh <= 0:
            return None
        return (self._monthly_grid_import_cost / self._monthly_grid_import_kwh) * 100

    @property
    def daily_grid_import_kwh(self) -> float:
        """Täglicher Netzbezug in kWh."""
        return self._daily_grid_import_kwh

    @property
    def daily_grid_import_cost(self) -> float:
        """Tägliche Netzbezugskosten in €."""
        return self._daily_grid_import_cost

    @property
    def daily_feed_in_earnings(self) -> float:
        """Tägliche Einspeisevergütung in €."""
        return self._daily_feed_in_earnings

    @property
    def daily_feed_in_kwh(self) -> float:
        """Tägliche Einspeisung in kWh."""
        return self._daily_feed_in_kwh

    @property
    def daily_net_electricity_cost(self) -> float:
        """Tägliche Netto-Stromkosten (Einkauf minus Verkauf) in €."""
        return self._daily_grid_import_cost - self._daily_feed_in_earnings

    @property
    def monthly_grid_import_kwh(self) -> float:
        """Monatlicher Netzbezug in kWh."""
        return self._monthly_grid_import_kwh

    @property
    def monthly_grid_import_cost(self) -> float:
        """Monatliche Netzbezugskosten in €."""
        return self._monthly_grid_import_cost

    @property
    def spot_vs_fixed_savings(self) -> float | None:
        """
        Ersparnis gegenüber konfiguriertem Fixpreis.
        Positiv = Spot günstiger, Negativ = Fixpreis günstiger.
        """
        avg = self.average_electricity_price
        if avg is None:
            return None
        # Vergleich mit konfiguriertem Fixpreis (aus Options)
        diff_per_kwh = self.fixed_price_compare - avg
        return diff_per_kwh * self._tracked_grid_import_kwh

    @property
    def fixed_price_compare_ct(self) -> float:
        """Konfigurierter Fixpreis in ct/kWh."""
        return self.fixed_price_compare * 100

    @property
    def spot_vs_fixed_savings_treuebonus(self) -> float | None:
        """
        Ersparnis gegenüber Fixpreis mit Treuebonus (1ct günstiger als konfigurierter Preis).
        DEPRECATED: Verwende spot_vs_fixed_savings mit angepasstem fixed_price_compare.
        """
        avg = self.average_electricity_price
        if avg is None:
            return None
        # Treuebonus = konfigurierter Preis - 1ct
        fixed_price_treuebonus = self.fixed_price_compare - 0.01
        diff_per_kwh = fixed_price_treuebonus - avg
        return diff_per_kwh * self._tracked_grid_import_kwh

    @property
    def consumption_kwh(self) -> float:
        """Aktueller Verbrauch vom Sensor."""
        return self._consumption_kwh

    @property
    def self_consumption_kwh(self) -> float:
        """Gesamter Eigenverbrauch (inkrementell berechnet)."""
        return self._total_self_consumption_kwh

    @property
    def feed_in_kwh(self) -> float:
        """Gesamte Einspeisung (inkrementell berechnet)."""
        return self._total_feed_in_kwh

    @property
    def savings_self_consumption(self) -> float:
        """Ersparnis durch Eigenverbrauch."""
        return self._accumulated_savings_self

    @property
    def earnings_feed_in(self) -> float:
        """Einnahmen durch Einspeisung."""
        return self._accumulated_earnings_feed

    @property
    def total_savings(self) -> float:
        """Gesamtersparnis inkl. manuellem Offset."""
        base = self.savings_self_consumption + self.earnings_feed_in
        return base + self.savings_offset

    @property
    def amortisation_percent(self) -> float:
        """Amortisation in Prozent."""
        if self.installation_cost <= 0:
            return 100.0
        return min(100.0, (self.total_savings / self.installation_cost) * 100)

    @property
    def remaining_cost(self) -> float:
        """Restbetrag bis zur Amortisation."""
        return max(0.0, self.installation_cost - self.total_savings)

    @property
    def is_amortised(self) -> bool:
        """True wenn vollständig amortisiert."""
        return self.total_savings >= self.installation_cost

    @property
    def self_consumption_ratio(self) -> float:
        """Eigenverbrauchsquote (%)."""
        if self._pv_production_kwh <= 0:
            return 0.0
        current_self = max(0.0, self._pv_production_kwh - self._grid_export_kwh)
        return min(100.0, (current_self / self._pv_production_kwh) * 100)

    @property
    def autarky_rate(self) -> float | None:
        """
        Autarkiegrad (%) - Anteil des Verbrauchs der durch PV gedeckt wird.

        Berechnung basiert auf SENSOR-TOTALS (nicht getrackten Werten):
        - Eigenverbrauch = PV Produktion - Netzeinspeisung
        - Mit Verbrauchs-Sensor: Eigenverbrauch / Verbrauch
        - Ohne Verbrauchs-Sensor: Eigenverbrauch / (Eigenverbrauch + Netzbezug)
        """
        # Eigenverbrauch aus aktuellen Sensor-Werten berechnen
        # (konsistent mit den anderen Sensor-Totals)
        self_consumption = max(0.0, self._pv_production_kwh - self._grid_export_kwh)

        if self_consumption <= 0:
            return None

        # Option 1: Verbrauchs-Sensor vorhanden
        if self.consumption_entity and self._consumption_kwh > 0:
            return min(100.0, (self_consumption / self._consumption_kwh) * 100)

        # Option 2: Netzbezug-Sensor vorhanden
        if self.grid_import_entity and self._grid_import_kwh > 0:
            total_consumption = self_consumption + self._grid_import_kwh
            if total_consumption > 0:
                return min(100.0, (self_consumption / total_consumption) * 100)

        # Keine Berechnung möglich
        return None

    @property
    def co2_saved_kg(self) -> float:
        """Eingesparte CO2-Emissionen in kg."""
        return self.self_consumption_kwh * CO2_FACTOR_GRID

    # --- Benchmark Properties -------------------------------------------------

    @property
    def benchmark_avg_consumption_kwh(self) -> int:
        """Reference household consumption (without heat pump) from BENCHMARK_CONSUMPTION."""
        country_data = BENCHMARK_CONSUMPTION.get(self.benchmark_country, BENCHMARK_CONSUMPTION["AT"])
        size = max(1, min(6, self.benchmark_household_size))
        return country_data.get(size, country_data[3])

    @property
    def benchmark_avg_heatpump_kwh(self) -> int | None:
        """Reference heat pump consumption. Only if benchmark_heatpump is True."""
        if not self.benchmark_heatpump:
            return None
        return BENCHMARK_HEATPUMP_CONSUMPTION.get(self.benchmark_country, 4000)

    @property
    def benchmark_own_annual_consumption_kwh(self) -> float | None:
        """Total consumption extrapolated to 1 year (incl. heat pump).

        Uses rolling 12-month buckets when available, otherwise extrapolation.
        """
        # Bucket-based (12 months available)
        if len(self._monthly_buckets) >= 12:
            total = sum(
                b.get("self_consumption", 0.0) + b.get("grid_import", 0.0)
                for b in self._monthly_buckets.values()
            )
            if 0 < total < 100_000:
                return total
        # Fallback: extrapolation
        if self._benchmark_start_date is None:
            return None
        days = max(1, (date.today() - self._benchmark_start_date).days)
        consumption = (
            (self._total_self_consumption_kwh - self._benchmark_start_self_consumption)
            + (self._tracked_grid_import_kwh - self._benchmark_start_grid_import)
        )
        if consumption <= 0:
            return None
        total_annual = consumption / days * 365
        if total_annual > 100_000:
            return None
        return total_annual

    @property
    def benchmark_own_heatpump_kwh(self) -> float | None:
        """Own heat pump consumption (delta since first seen, extrapolated to 1 year)."""
        if not self.benchmark_heatpump or not self.benchmark_heatpump_entity:
            return None
        # Bucket-based
        if len(self._monthly_buckets) >= 12:
            wp_total = sum(b.get("wp", 0.0) for b in self._monthly_buckets.values())
            if wp_total > 0:
                return wp_total
        # Fallback: extrapolation
        if self._wp_first_seen_date is None or self._tracked_wp_kwh <= 0:
            return None
        wp_days = max(1, (date.today() - self._wp_first_seen_date).days)
        return (self._tracked_wp_kwh / wp_days) * 365

    @property
    def benchmark_household_consumption_kwh(self) -> float | None:
        """Household consumption without heat pump, extrapolated to 1 year."""
        total = self.benchmark_own_annual_consumption_kwh
        if total is None:
            return None
        wp = self.benchmark_own_heatpump_kwh or 0.0
        wp = min(wp, total)  # WP kann nicht mehr als Gesamtverbrauch sein
        return total - wp

    @property
    def benchmark_consumption_vs_avg(self) -> float | None:
        """Percentage difference: household (excl. WP) vs average. Negative = better."""
        household = self.benchmark_household_consumption_kwh
        if household is None:
            return None
        avg = self.benchmark_avg_consumption_kwh
        if avg <= 0:
            return None
        return ((household - avg) / avg) * 100

    @property
    def benchmark_heatpump_vs_avg(self) -> float | None:
        """Percentage difference: own WP vs average WP. Negative = better."""
        own_wp = self.benchmark_own_heatpump_kwh
        if own_wp is None:
            return None
        avg_wp = self.benchmark_avg_heatpump_kwh
        if avg_wp is None or avg_wp <= 0:
            return None
        return (own_wp - avg_wp) / avg_wp * 100

    @property
    def benchmark_co2_avoided_kg(self) -> float | None:
        """CO2 avoided by PV per year in kg (snapshot-based)."""
        co2_factor = BENCHMARK_CO2_FACTORS.get(self.benchmark_country, 0.3)
        # Bucket-based
        if len(self._monthly_buckets) >= 12:
            annual_pv = sum(
                b.get("self_consumption", 0.0) + b.get("feed_in", 0.0)
                for b in self._monthly_buckets.values()
            )
            if 0 < annual_pv < 100_000:
                return annual_pv * co2_factor
        # Fallback: extrapolation
        if self._benchmark_start_date is None:
            return None
        days = max(1, (date.today() - self._benchmark_start_date).days)
        pv_since_start = (
            (self._total_self_consumption_kwh - self._benchmark_start_self_consumption)
            + (self._total_feed_in_kwh - self._benchmark_start_feed_in)
        )
        if pv_since_start <= 0:
            return None
        daily_pv = pv_since_start / days
        annual_pv = daily_pv * 365
        if annual_pv > 100_000:
            return None
        return annual_pv * co2_factor

    @property
    def benchmark_annual_grid_import_kwh(self) -> float | None:
        """Annual grid import extrapolated from benchmark period."""
        if len(self._monthly_buckets) >= 12:
            grid = sum(b.get("grid_import", 0.0) for b in self._monthly_buckets.values())
            if 0 < grid < 100_000:
                return grid
        # Fallback: extrapolation
        if self._benchmark_start_date is None:
            return None
        days = max(1, (date.today() - self._benchmark_start_date).days)
        grid_since_start = self._tracked_grid_import_kwh - self._benchmark_start_grid_import
        if grid_since_start <= 0:
            return None
        annual = grid_since_start / days * 365
        if annual > 100_000:
            return None
        return annual

    @property
    def benchmark_annual_pv_production_kwh(self) -> float | None:
        """Hochgerechnete PV-Jahresproduktion (snapshot-basiert)."""
        # Bucket-based
        if len(self._monthly_buckets) >= 12:
            pv = sum(
                b.get("self_consumption", 0.0) + b.get("feed_in", 0.0)
                for b in self._monthly_buckets.values()
            )
            if 0 < pv < 100_000:
                return pv
        # Fallback: extrapolation
        if self._benchmark_start_date is None:
            return None
        days = max(1, (date.today() - self._benchmark_start_date).days)
        pv_since_start = (
            (self._total_self_consumption_kwh - self._benchmark_start_self_consumption)
            + (self._total_feed_in_kwh - self._benchmark_start_feed_in)
        )
        if pv_since_start <= 0:
            return None
        annual = pv_since_start / days * 365
        if annual > 100_000:
            return None
        return annual

    @property
    def total_installed_kwp(self) -> float:
        """Summe der installierten kWp aller Strings."""
        return sum(kwp for _, _, _, kwp in self.pv_strings if kwp > 0)

    @property
    def benchmark_specific_yield(self) -> float | None:
        """Spezifischer Ertrag in kWh/kWp (Jahresproduktion / installierte Leistung).

        Fallback auf gemessene Peaks wenn keine kWp konfiguriert.
        """
        annual = self.benchmark_annual_pv_production_kwh
        if annual is None:
            return None
        kwp = self.total_installed_kwp
        if kwp <= 0:
            peak_kw = self.get_total_peak_kw()
            kwp = peak_kw if peak_kw else 0.0
        if kwp <= 0:
            return None
        return round(annual / kwp, 0)

    @property
    def benchmark_efficiency_score(self) -> int | None:
        """Efficiency score 0-100.

        Weights:
        - Autarky rate (35): How independent from grid
        - Specific yield (25): How well the system is utilized (kWh/kWp vs 900 reference)
        - Self-consumption ratio (20): Reduced weight, large systems are penalized unfairly
        - Consumption vs average (20): Reduced weight, heat pump users are penalized unfairly
        """
        autarky = self.autarky_rate
        comparison = self.benchmark_consumption_vs_avg
        if autarky is None and comparison is None:
            return None

        # Autarky rate (35 points) — 100% = 35, 0% = 0
        autarky_score = 0.0
        if autarky is not None:
            autarky_score = min(35, autarky * 0.35)

        # Specific yield (25 points) — 900 kWh/kWp = 25, 0 = 0
        yield_score = 0.0
        specific = self.benchmark_specific_yield
        if specific is not None and specific > 0:
            yield_score = min(25, (specific / 900) * 25)

        # Self-consumption ratio (20 points) — 100% = 20, 0% = 0
        ratio_score = 0.0
        sc_ratio = self.self_consumption_ratio
        if sc_ratio is not None:
            ratio_score = min(20, sc_ratio * 0.2)

        # Consumption vs average (20 points) — -50% = 20, 0% = 10, +50% = 0
        consumption_score = 0.0
        if comparison is not None:
            consumption_score = max(0, min(20, 10 - comparison * 0.2))

        return int(autarky_score + yield_score + ratio_score + consumption_score)

    @property
    def benchmark_rating(self) -> str | None:
        """Text rating based on efficiency score."""
        score = self.benchmark_efficiency_score
        if score is None:
            return None
        if score >= 80:
            return "Hervorragend"
        if score >= 60:
            return "Sehr gut"
        if score >= 40:
            return "Gut"
        if score >= 20:
            return "Durchschnittlich"
        return "Verbesserungspotenzial"

    @property
    def days_tracking(self) -> int:
        """Tage seit erstem Tracking (unabhängig von Installationsdatum)."""
        if self._first_seen_date:
            return (date.today() - self._first_seen_date).days
        return 0

    @property
    def days_since_installation(self) -> int:
        """Tage seit Installation (oder erstem Tracking)."""
        # Priorität: Konfiguriertes Installationsdatum
        if self.installation_date:
            try:
                if isinstance(self.installation_date, str):
                    install_date = datetime.fromisoformat(self.installation_date).date()
                else:
                    install_date = self.installation_date
                return (date.today() - install_date).days
            except (ValueError, TypeError):
                pass

        # Fallback: Erstes Tracking-Datum
        return self.days_tracking

    @property
    def average_daily_savings(self) -> float:
        """Durchschnittliche tägliche Ersparnis."""
        days = self.days_since_installation
        if days <= 0:
            return 0.0
        return self.total_savings / days

    @property
    def average_monthly_savings(self) -> float:
        """Durchschnittliche monatliche Ersparnis."""
        return self.average_daily_savings * 30.44

    @property
    def average_yearly_savings(self) -> float:
        """Durchschnittliche jährliche Ersparnis."""
        return self.average_daily_savings * 365

    @property
    def estimated_remaining_days(self) -> int | None:
        """Geschätzte verbleibende Tage bis Amortisation."""
        if self.is_amortised:
            return 0
        daily_avg = self.average_daily_savings
        if daily_avg <= 0:
            return None
        return int(self.remaining_cost / daily_avg)

    @property
    def estimated_payback_date(self) -> date | None:
        """Geschätztes Amortisationsdatum."""
        remaining = self.estimated_remaining_days
        if remaining is None:
            return None
        if remaining == 0:
            return date.today()
        from datetime import timedelta
        return date.today() + timedelta(days=remaining)

    @property
    def status_text(self) -> str:
        """Status-Text für Anzeige."""
        if self.is_amortised:
            profit = self.total_savings - self.installation_cost
            return f"Amortisiert! +{profit:.2f}€ Gewinn"
        else:
            return f"{self.amortisation_percent:.1f}% amortisiert"

    # =========================================================================
    # STROMVERBRAUCH-EMPFEHLUNG (AMPEL)
    # =========================================================================

    @property
    def consumption_recommendation(self) -> str:
        """
        Berechnet Stromverbrauch-Empfehlung basierend auf:
        - PV-Leistung (aktuell)
        - Batterie-Ladestand
        - Strompreis (EPEX Quantile wenn verfügbar, sonst absoluter Preis)
        - Tageszeit
        - PV-Prognose (Solcast wenn verfügbar)

        Returns: 'green', 'yellow', 'red'
        """
        score = 0  # Positiv = gut zu verbrauchen, Negativ = nicht verbrauchen

        # === PV-Leistung (basierend auf Peak-Leistung) ===
        # Berechne Schwellwerte als Prozent der Peak-Leistung
        pv_very_high = self.pv_peak_power * 0.6   # 60% = sehr viel PV
        pv_high = self.pv_peak_power * 0.3        # 30% = viel PV
        pv_low = self.pv_peak_power * 0.05        # 5% = kaum PV

        if self._pv_power >= pv_very_high:
            score += 4  # Sehr viel PV -> hervorragend
        elif self._pv_power >= pv_high:
            score += 2  # Viel PV -> gut
        elif self._pv_power >= pv_low:
            score += 0  # Mittlere PV -> neutral
        else:
            score -= 1  # Kaum PV -> schlecht

        # === Batterie-Ladestand ===
        if self.battery_soc_entity:
            if self._battery_soc >= self.battery_soc_high:
                score += 2  # Batterie voll -> gut verbrauchen
            elif self._battery_soc <= self.battery_soc_low:
                score -= 2  # Batterie leer -> nicht verbrauchen
            else:
                # Mittlerer Bereich
                pass

        # === Strompreis (Quantile + absoluter Schwellwert) ===
        price = self.current_electricity_price
        is_below_threshold = price <= self.price_low_threshold
        is_above_threshold = price >= self.price_high_threshold

        if self.epex_quantile_entity and 0 <= self._epex_quantile <= 1:
            # EPEX verfügbar: Kombiniere Quantile mit absolutem Preis
            if self._epex_quantile <= 0.2 and is_below_threshold:
                score += 3  # Sehr günstig (relativ + absolut)
            elif self._epex_quantile <= 0.2:
                score += 2  # Relativ günstig - immer noch guter Deal!
            elif is_below_threshold:
                score += 2  # Absolut günstig
            elif self._epex_quantile >= 0.8 or is_above_threshold:
                score -= 3  # Teuer
            elif self._epex_quantile >= 0.6:
                score -= 1  # Relativ teuer
        else:
            # Fallback: Nur absoluter Preis
            if is_below_threshold:
                score += 2  # Günstiger Strom
            elif is_above_threshold:
                score -= 2  # Teurer Strom

        # === Tageszeit ===
        hour = datetime.now().hour
        if 10 <= hour <= 15:
            score += 1  # Kernzeit PV -> gut
        elif hour < 6 or hour > 21:
            score -= 1  # Nacht -> eher schlecht

        # === PV-Prognose (Solcast hat Priorität) ===
        forecast = self._solcast_forecast_today if self.solcast_forecast_entity else self._pv_forecast
        if forecast > 0:
            if forecast >= 10:
                score += 1  # Gute Prognose
            elif forecast < 3:
                score -= 1  # Schlechte Prognose

        # === Auswertung (5 Stufen) ===
        if score >= 5:
            return RECOMMENDATION_DARK_GREEN  # Perfekt!
        elif score >= 3:
            return RECOMMENDATION_GREEN  # Jetzt verbrauchen
        elif score >= 0:
            return RECOMMENDATION_YELLOW  # Neutral
        elif score >= -2:
            return RECOMMENDATION_ORANGE  # Eher ungünstig
        else:
            return RECOMMENDATION_RED  # Vermeiden (≤-3)

    @property
    def consumption_recommendation_text(self) -> str:
        """Textuelle Empfehlung mit Begründung.

        Konzept für Nicht-Techniker:
        - Der Präfix sagt klar was zu tun ist
        - Die Gründe erklären warum
        - Die Farbe (separates Attribut) visualisiert die Dringlichkeit
        """
        rec = self.consumption_recommendation
        reasons = self._get_recommendation_reasons()

        # Klare Handlungsempfehlung als Präfix (außer bei Neutral)
        if rec == RECOMMENDATION_DARK_GREEN:
            prefix = "Idealer Zeitpunkt"
        elif rec == RECOMMENDATION_GREEN:
            prefix = "Guter Zeitpunkt"
        elif rec == RECOMMENDATION_ORANGE:
            prefix = "Eher ungünstig"
        elif rec == RECOMMENDATION_RED:
            prefix = "Ungünstig"
        else:
            # Neutral (YELLOW): Nur Gründe anzeigen, kein Präfix
            return reasons if reasons else "Neutral"

        if reasons:
            return f"{prefix}: {reasons}"
        return prefix

    @property
    def recommendation_status(self) -> str:
        """Kurzer Status-Text für die Empfehlung (ohne Gründe)."""
        rec = self.consumption_recommendation
        if rec == RECOMMENDATION_DARK_GREEN:
            return "Idealer Zeitpunkt"
        elif rec == RECOMMENDATION_GREEN:
            return "Guter Zeitpunkt"
        elif rec == RECOMMENDATION_ORANGE:
            return "Eher ungünstig"
        elif rec == RECOMMENDATION_RED:
            return "Ungünstig"
        else:
            return "Neutral"

    @property
    def recommendation_reasons(self) -> str:
        """Gründe für die Empfehlung (ohne Status-Präfix)."""
        return self._get_recommendation_reasons()

    @property
    def pv_info(self) -> str:
        """PV-Status für Card (z.B. 'kaum PV', 'viel PV')."""
        pv_power = self._pv_power
        pv_very_high = self.pv_peak_power * 0.6
        pv_high = self.pv_peak_power * 0.3
        pv_moderate = self.pv_peak_power * 0.1
        pv_low = self.pv_peak_power * 0.05

        if pv_power >= pv_very_high:
            return "sehr viel PV"
        elif pv_power >= pv_high:
            return "viel PV"
        elif pv_power >= pv_moderate:
            return "etwas PV"
        elif pv_power <= 0:
            return "kein PV"
        elif pv_power < pv_low:
            return "kaum PV"
        return "wenig PV"

    @property
    def akku_info(self) -> str:
        """Akku-Status für Card (z.B. 'Akku voll', 'Akku leer', oder leer)."""
        if not self.battery_soc_entity:
            return ""
        if self._battery_soc >= self.battery_soc_high:
            return "Akku voll"
        elif self._battery_soc <= self.battery_soc_low:
            return "Akku leer"
        return ""

    @property
    def preis_info(self) -> str:
        """Preis-Status für Card (z.B. 'Strom günstig (25ct)', oder leer)."""
        price = self.current_electricity_price
        price_ct = price * 100  # In Cent für bessere Lesbarkeit
        is_below = price <= self.price_low_threshold
        is_above = price >= self.price_high_threshold

        if self.epex_quantile_entity and 0 <= self._epex_quantile <= 1:
            if self._epex_quantile <= 0.2 and is_below:
                return f"sehr günstig ({price_ct:.1f}ct)"
            elif self._epex_quantile <= 0.2:
                return f"heute günstig ({price_ct:.1f}ct)"
            elif is_below:
                return f"Strom günstig ({price_ct:.1f}ct)"
            elif self._epex_quantile >= 0.8 or is_above:
                return f"Strom teuer ({price_ct:.1f}ct)"
            elif self._epex_quantile >= 0.6:
                return f"heute teuer ({price_ct:.1f}ct)"
        else:
            if is_below:
                return f"Strom günstig ({price_ct:.1f}ct)"
            elif is_above:
                return f"Strom teuer ({price_ct:.1f}ct)"
        return ""

    @property
    def pv_tipp(self) -> str:
        """PV-Prognose Tipp für Card."""
        return self.next_pv_peak_text

    @property
    def preis_tipp(self) -> str:
        """Preis-Prognose Tipp für Card."""
        return self.next_cheap_hour_text

    @property
    def consumption_recommendation_color(self) -> str:
        """Farbe für die Ampel (für Dashboards)."""
        rec = self.consumption_recommendation
        if rec == RECOMMENDATION_DARK_GREEN:
            return "#00bcd4"  # Cyan
        elif rec == RECOMMENDATION_GREEN:
            return "#4caf50"  # Grün
        elif rec == RECOMMENDATION_YELLOW:
            return "#ffeb3b"  # Gelb
        elif rec == RECOMMENDATION_ORANGE:
            return "#ff9800"  # Orange
        else:
            return "#f44336"  # Rot

    def _get_recommendation_reasons(self) -> str:
        """Erstellt menschenlesbare Begründung für die Empfehlung."""
        reasons = []

        # PV-Leistung (basierend auf Peak-Leistung)
        # Für Text: tatsächliche Messung verwenden (nicht effektive nach Abzug)
        # Schwellwerte: 60% sehr viel, 30% viel, 10% etwas, <5% kaum
        pv_power_raw = self._pv_power  # Tatsächliche Messung
        pv_power_effective = self.effective_pv_power  # Mit Winter-Grundlast-Abzug (für Score)
        pv_very_high = self.pv_peak_power * 0.6
        pv_high = self.pv_peak_power * 0.3
        pv_moderate = self.pv_peak_power * 0.1
        pv_low = self.pv_peak_power * 0.05

        # Text basiert auf tatsächlicher Messung
        if pv_power_raw >= pv_very_high:
            reasons.append("sehr viel PV")
        elif pv_power_raw >= pv_high:
            reasons.append("viel PV")
        elif pv_power_raw >= pv_moderate:
            reasons.append("etwas PV")
        elif pv_power_raw <= 0:
            reasons.append("kein PV")
        elif pv_power_raw < pv_low:
            reasons.append("kaum PV")

        # Batterie
        if self.battery_soc_entity:
            if self._battery_soc >= self.battery_soc_high:
                reasons.append("Akku voll")
            elif self._battery_soc <= self.battery_soc_low:
                reasons.append("Akku leer")

        # Strompreis - kombiniere EPEX Quantile mit absolutem Schwellwert
        price = self.current_electricity_price
        price_ct = price * 100  # In Cent für bessere Lesbarkeit
        is_below_threshold = price <= self.price_low_threshold
        is_above_threshold = price >= self.price_high_threshold

        if self.epex_quantile_entity and 0 <= self._epex_quantile <= 1:
            # EPEX verfügbar: Quantile + absoluter Preis
            if self._epex_quantile <= 0.2 and is_below_threshold:
                reasons.append(f"sehr günstig ({price_ct:.1f}ct)")
            elif self._epex_quantile <= 0.2:
                reasons.append(f"heute günstig ({price_ct:.1f}ct)")  # Relativ günstig, aber über Schwelle
            elif is_below_threshold:
                reasons.append(f"Strom günstig ({price_ct:.1f}ct)")
            elif self._epex_quantile >= 0.8 or is_above_threshold:
                reasons.append(f"Strom teuer ({price_ct:.1f}ct)")
            elif self._epex_quantile >= 0.6:
                reasons.append(f"heute teuer ({price_ct:.1f}ct)")  # Relativ teuer
        else:
            # Kein EPEX: Nur absoluter Preis
            if is_below_threshold:
                reasons.append(f"Strom günstig ({price_ct:.1f}ct)")
            elif is_above_threshold:
                reasons.append(f"Strom teuer ({price_ct:.1f}ct)")

        return ", ".join(reasons) if reasons else ""

    @property
    def consumption_recommendation_score(self) -> int:
        """Detaillierter Score für die Empfehlung."""
        score = 0

        # PV-Leistung (basierend auf Peak-Leistung, mit Winter-Grundlast-Abzug)
        pv_power = self.effective_pv_power
        pv_very_high = self.pv_peak_power * 0.6
        pv_high = self.pv_peak_power * 0.3
        pv_moderate = self.pv_peak_power * 0.1
        pv_low = self.pv_peak_power * 0.05

        if pv_power >= pv_very_high:
            score += 4
        elif pv_power >= pv_high:
            score += 2
        elif pv_power >= pv_moderate:
            score += 1  # Etwas PV = +1
        elif pv_power >= pv_low:
            score += 0
        else:
            score -= 1

        if self.battery_soc_entity:
            if self._battery_soc >= self.battery_soc_high:
                score += 2
            elif self._battery_soc <= self.battery_soc_low:
                score -= 2

        # Strompreis (Quantile + absoluter Schwellwert)
        price = self.current_electricity_price
        is_below_threshold = price <= self.price_low_threshold
        is_above_threshold = price >= self.price_high_threshold

        if self.epex_quantile_entity and 0 <= self._epex_quantile <= 1:
            if self._epex_quantile <= 0.2 and is_below_threshold:
                score += 3  # Sehr günstig
            elif self._epex_quantile <= 0.2:
                score += 2  # Relativ günstig - guter Zeitpunkt!
            elif is_below_threshold:
                score += 2  # Absolut günstig
            elif self._epex_quantile >= 0.8 or is_above_threshold:
                score -= 3  # Teuer
            elif self._epex_quantile >= 0.6:
                score -= 1  # Relativ teuer
        else:
            if is_below_threshold:
                score += 2
            elif is_above_threshold:
                score -= 2

        hour = datetime.now().hour
        if 10 <= hour <= 15:
            score += 1
        elif hour < 6 or hour > 21:
            score -= 1

        forecast = self._solcast_forecast_today if self.solcast_forecast_entity else self._pv_forecast
        if forecast > 0:
            if forecast >= 10:
                score += 1
            elif forecast < 3:
                score -= 1

        return score

    # =========================================================================
    # ENTITY MANAGEMENT
    # =========================================================================

    def register_entity_listener(self, cb) -> None:
        """Sensoren registrieren sich hier für Updates."""
        if cb not in self._entity_listeners:
            self._entity_listeners.append(cb)

    def unregister_entity_listener(self, cb) -> None:
        """Entfernt einen Entity-Listener."""
        try:
            self._entity_listeners.remove(cb)
        except ValueError:
            pass  # Listener war nicht registriert

    def _notify_entities(self) -> None:
        """Informiert alle Entities über Zustandsänderungen."""
        # Tracke Auto-Charge Aktivität für Statistiken
        self.track_auto_charge_activity()

        for cb in list(self._entity_listeners):  # Copy list to avoid modification during iteration
            try:
                cb()
            except Exception as e:
                _LOGGER.debug("Entity-Listener Fehler (ignoriert): %s", e)

        # Sync to helper after every update
        self._sync_to_helper()

        # Check for notifications
        self._check_milestones()
        self._check_monthly_summary()

    def _sync_to_helper(self) -> None:
        """Synchronisiert die Gesamtersparnis zum Helper."""
        if not self.amortisation_helper:
            return

        try:
            current_savings = self.total_savings
            state = self.hass.states.get(self.amortisation_helper)

            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    helper_value = float(state.state)
                    # Nur updaten wenn sich der Wert signifikant geändert hat (> 0.01 EUR)
                    if abs(helper_value - current_savings) > 0.01:
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "input_number",
                                "set_value",
                                {
                                    "entity_id": self.amortisation_helper,
                                    "value": round(current_savings, 2),
                                },
                            )
                        )
                        _LOGGER.debug(
                            "Amortisation Helper synced: %.2f EUR → %s",
                            current_savings, self.amortisation_helper
                        )
                except (ValueError, TypeError) as e:
                    _LOGGER.warning("Helper sync error: %s", e)
        except Exception as e:
            _LOGGER.debug("Helper sync failed (ignoriert): %s", e)

    async def _restore_from_helper(self) -> bool:
        """Stellt die Gesamtersparnis vom Helper wieder her."""
        if not self.amortisation_helper or not self.restore_from_helper:
            return False

        try:
            state = self.hass.states.get(self.amortisation_helper)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                helper_value = float(state.state)

                if helper_value > 0:
                    _LOGGER.info(
                        "Restoring from helper %s: %.2f EUR",
                        self.amortisation_helper, helper_value
                    )

                    # Setze den Offset so, dass total_savings dem Helper entspricht
                    current_accumulated = self._accumulated_savings_self + self._accumulated_earnings_feed
                    self.savings_offset = max(0, helper_value - current_accumulated)

                    self._restored = True
                    self._notify_entities()
                    return True
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Restore from helper failed: %s", e)

        return False

    def _check_milestones(self) -> None:
        """Prüft und feuert Meilenstein-Events (25%, 50%, 75%, 100%)."""
        if self.installation_cost <= 0:
            return

        percent = self.amortisation_percent
        milestones = [25, 50, 75, 100]

        for milestone in milestones:
            if percent >= milestone and milestone not in self._milestones_fired:
                self._milestones_fired.add(milestone)

                if milestone == 100:
                    profit = self.total_savings - self.installation_cost
                    message = f"PV-Anlage vollständig amortisiert! +{profit:.2f}€ Gewinn!"
                    event_type = "amortisation_complete"
                else:
                    message = f"{milestone}% der PV-Anlage amortisiert! Noch {self.remaining_cost:.2f}€ bis zur Amortisation."
                    event_type = "amortisation_milestone"

                self.hass.bus.async_fire("pv_management_event", {
                    "type": event_type,
                    "milestone": milestone,
                    "total_savings": round(self.total_savings, 2),
                    "remaining": round(self.remaining_cost, 2),
                    "installation_cost": self.installation_cost,
                    "message": message,
                })
                _LOGGER.info("Meilenstein erreicht: %s", message)

    def _check_monthly_summary(self) -> None:
        """Sendet monatliche Zusammenfassung am 1. des Monats."""
        today = date.today()

        # Nur am 1. des Monats und nur einmal pro Monat
        if today.day != 1:
            return
        if self._monthly_summary_month == today.month:
            return

        self._monthly_summary_month = today.month

        # Berechne Vormonat
        from datetime import timedelta
        last_month = today - timedelta(days=1)
        month_name = last_month.strftime("%B %Y")

        # Monatliche Werte (aus dem Tracking)
        monthly_kwh = self._monthly_grid_import_kwh
        monthly_cost = self._monthly_grid_import_cost

        message = f"PV-Bericht {month_name}: {monthly_kwh:.0f} kWh Netzbezug, {self.amortisation_percent:.1f}% amortisiert"

        self.hass.bus.async_fire("pv_management_event", {
            "type": "monthly_summary",
            "month": month_name,
            "grid_import_kwh": round(monthly_kwh, 1),
            "grid_import_cost": round(monthly_cost, 2),
            "amortisation_percent": round(self.amortisation_percent, 1),
            "total_savings": round(self.total_savings, 2),
            "message": message,
        })
        _LOGGER.info("Monatliche Zusammenfassung: %s", message)

    def restore_state(self, data: dict[str, Any]) -> None:
        """Stellt den gespeicherten Zustand wieder her."""
        # Sichere Float-Konvertierung
        def safe_float(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        self._total_self_consumption_kwh = safe_float(data.get("total_self_consumption_kwh"))
        self._total_feed_in_kwh = safe_float(data.get("total_feed_in_kwh"))
        self._accumulated_savings_self = safe_float(data.get("accumulated_savings_self"))
        self._accumulated_earnings_feed = safe_float(data.get("accumulated_earnings_feed"))

        # Strompreis-Tracking Daten wiederherstellen
        self._tracked_grid_import_kwh = safe_float(data.get("tracked_grid_import_kwh"))
        self._total_grid_import_cost = safe_float(data.get("total_grid_import_cost"))

        # Daily/Monthly Tracking wiederherstellen (NEU - Fix für Persistierung)
        today = date.today()

        # Daily: Prüfen ob gleicher Tag
        daily_reset_str = data.get("daily_reset_date")
        if daily_reset_str:
            try:
                daily_reset_date = date.fromisoformat(daily_reset_str)
                if daily_reset_date == today:
                    # Gleicher Tag - Werte wiederherstellen
                    self._daily_grid_import_kwh = safe_float(data.get("daily_grid_import_kwh"))
                    self._daily_grid_import_cost = safe_float(data.get("daily_grid_import_cost"))
                    self._daily_feed_in_earnings = safe_float(data.get("daily_feed_in_earnings"))
                    self._daily_feed_in_kwh = safe_float(data.get("daily_feed_in_kwh"))
                    _LOGGER.info(
                        "Daily Strompreis-Tracking wiederhergestellt: %.2f kWh, %.2f €",
                        self._daily_grid_import_kwh, self._daily_grid_import_cost
                    )
                else:
                    # Neuer Tag - bei 0 starten
                    _LOGGER.info("Neuer Tag seit letztem Speichern, Daily-Werte zurückgesetzt")
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Konnte daily_reset_date nicht parsen: %s", e)

        # Monthly: Prüfen ob gleicher Monat
        monthly_reset_month = data.get("monthly_reset_month")
        monthly_reset_year = data.get("monthly_reset_year")
        if monthly_reset_month is not None and monthly_reset_year is not None:
            try:
                if int(monthly_reset_month) == today.month and int(monthly_reset_year) == today.year:
                    # Gleicher Monat - Werte wiederherstellen
                    self._monthly_grid_import_kwh = safe_float(data.get("monthly_grid_import_kwh"))
                    self._monthly_grid_import_cost = safe_float(data.get("monthly_grid_import_cost"))
                    _LOGGER.info(
                        "Monthly Strompreis-Tracking wiederhergestellt: %.2f kWh, %.2f €",
                        self._monthly_grid_import_kwh, self._monthly_grid_import_cost
                    )
                else:
                    # Neuer Monat - bei 0 starten
                    _LOGGER.info("Neuer Monat seit letztem Speichern, Monthly-Werte zurückgesetzt")
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Konnte monthly_reset Daten nicht parsen: %s", e)

        # Auto-Charge Statistiken wiederherstellen
        self._auto_charge_count = int(safe_float(data.get("auto_charge_count")))
        self._auto_charge_total_hours = safe_float(data.get("auto_charge_total_hours"))
        self._auto_charge_total_kwh = safe_float(data.get("auto_charge_total_kwh"))
        self._auto_charge_estimated_savings = safe_float(data.get("auto_charge_estimated_savings"))

        # WP Delta-Tracking wiederherstellen
        restored_wp = safe_float(data.get("tracked_wp_kwh"))
        self._tracked_wp_kwh = restored_wp if restored_wp < 50000 else 0.0
        wp_first_seen = data.get("wp_first_seen_date")
        if wp_first_seen:
            try:
                self._wp_first_seen_date = date.fromisoformat(wp_first_seen) if isinstance(wp_first_seen, str) else wp_first_seen
            except (ValueError, TypeError):
                pass

        # PV-String Delta-Tracking wiederherstellen
        raw = data.get("string_tracked_kwh", {})
        self._string_tracked_kwh = {k: safe_float(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
        s_first = data.get("string_first_seen_date")
        if s_first:
            try:
                self._string_first_seen_date = date.fromisoformat(s_first) if isinstance(s_first, str) else s_first
            except (ValueError, TypeError):
                pass
        raw_peak = data.get("string_peak_w", {})
        self._string_peak_w = {k: safe_float(v) for k, v in raw_peak.items()} if isinstance(raw_peak, dict) else {}

        first_seen = data.get("first_seen_date")
        if first_seen:
            try:
                if isinstance(first_seen, str):
                    self._first_seen_date = date.fromisoformat(first_seen)
                elif isinstance(first_seen, date):
                    self._first_seen_date = first_seen
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Konnte first_seen_date nicht parsen: %s", e)

        # Validierung: Werte sollten plausibel sein
        if self._total_self_consumption_kwh < 0:
            _LOGGER.warning("Negativer Eigenverbrauch restored, setze auf 0")
            self._total_self_consumption_kwh = 0.0
        if self._total_feed_in_kwh < 0:
            _LOGGER.warning("Negative Einspeisung restored, setze auf 0")
            self._total_feed_in_kwh = 0.0

        # Plausibilitätsprüfung: Eigenverbrauch + Einspeisung sollte <= PV Produktion sein
        pv_total = self._pv_production_kwh
        if pv_total > 0:
            total_tracked = self._total_self_consumption_kwh + self._total_feed_in_kwh
            # Toleranz von 5% wegen Messungenauigkeiten
            if total_tracked > pv_total * 1.05:
                _LOGGER.warning(
                    "Unplausible restored Werte: %.2f kWh self + %.2f kWh feed = %.2f kWh > %.2f kWh PV. Trigger manual re-init.",
                    self._total_self_consumption_kwh,
                    self._total_feed_in_kwh,
                    total_tracked,
                    pv_total,
                )

        # Benchmark-Snapshot wiederherstellen
        bsd = data.get("benchmark_start_date")
        if bsd:
            try:
                self._benchmark_start_date = date.fromisoformat(bsd) if isinstance(bsd, str) else bsd
            except (ValueError, TypeError):
                pass
        self._benchmark_start_self_consumption = safe_float(data.get("benchmark_start_self_consumption"))
        self._benchmark_start_grid_import = safe_float(data.get("benchmark_start_grid_import"))
        self._benchmark_start_feed_in = safe_float(data.get("benchmark_start_feed_in"))

        # Monthly Buckets wiederherstellen
        raw_buckets = data.get("monthly_buckets", {})
        if isinstance(raw_buckets, dict):
            self._monthly_buckets = {}
            for k, v in raw_buckets.items():
                try:
                    month = int(k)
                    if 1 <= month <= 12 and isinstance(v, dict):
                        self._monthly_buckets[month] = {
                            "self_consumption": safe_float(v.get("self_consumption")),
                            "grid_import": safe_float(v.get("grid_import")),
                            "feed_in": safe_float(v.get("feed_in")),
                            "wp": safe_float(v.get("wp")),
                        }
                except (ValueError, TypeError):
                    pass
        self._monthly_bucket_month = data.get("monthly_bucket_month")
        if self._monthly_bucket_month is not None:
            try:
                self._monthly_bucket_month = int(self._monthly_bucket_month)
            except (ValueError, TypeError):
                self._monthly_bucket_month = None

        self._restored = True

        # HINWEIS: _last_* Werte werden NICHT hier gesetzt!
        # Sie werden in async_start() gesetzt nachdem die Sensor-Werte geladen wurden.
        # Zu diesem Zeitpunkt sind _pv_production_kwh etc. noch 0.0!

        _LOGGER.info(
            "PV Management restored: %.2f kWh self, %.2f kWh feed, %.2f€ savings, %.2f€ earnings, first_seen=%s",
            self._total_self_consumption_kwh,
            self._total_feed_in_kwh,
            self._accumulated_savings_self,
            self._accumulated_earnings_feed,
            self._first_seen_date,
        )

        # Verzögerte Benachrichtigung aller Entities nach Restore
        # (damit alle Entities registriert sind und die korrekten Werte anzeigen)
        @callback
        def delayed_restore_notify(_now):
            _LOGGER.debug("Delayed restore notify: Aktualisiere alle Entities nach Restore")
            self._notify_entities()

        from homeassistant.helpers.event import async_call_later
        async_call_later(self.hass, 5.0, delayed_restore_notify)

    def _initialize_from_sensors(self) -> None:
        """
        Initialisiert die Werte mit den aktuellen Sensor-Totals.
        Wird aufgerufen wenn keine restored Daten vorhanden sind.

        Berechnung:
        - Eigenverbrauch = PV Produktion - Einspeisung
        - Ersparnis = Eigenverbrauch × Strompreis + Einspeisung × Einspeisevergütung
        """
        # Lese Werte direkt von Sensoren (nicht cached Werte)
        pv_total = 0.0
        export_total = 0.0

        if self.pv_production_entity:
            state = self.hass.states.get(self.pv_production_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    pv_total = float(state.state)
                except (ValueError, TypeError):
                    pass

        if self.grid_export_entity:
            state = self.hass.states.get(self.grid_export_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    export_total = float(state.state)
                except (ValueError, TypeError):
                    pass

        if pv_total <= 0:
            _LOGGER.info("Keine historischen PV-Daten verfügbar, starte bei 0")
            return

        # Eigenverbrauch = PV Produktion - Einspeisung
        self_consumption = max(0, pv_total - export_total)
        feed_in = export_total

        # Berechne historische Ersparnis mit aktuellen Preisen
        price_electricity = self.current_electricity_price
        price_feed_in = self.current_feed_in_tariff

        savings_self = self_consumption * price_electricity
        earnings_feed = feed_in * price_feed_in

        # Setze die Werte
        self._total_self_consumption_kwh = self_consumption
        self._total_feed_in_kwh = feed_in
        self._accumulated_savings_self = savings_self
        self._accumulated_earnings_feed = earnings_feed
        self._first_seen_date = date.today()

        _LOGGER.info(
            "PV Management initialisiert: PV=%.2f, Export=%.2f → "
            "Eigenverbrauch=%.2f kWh (%.2f€), Einspeisung=%.2f kWh (%.2f€)",
            pv_total, export_total,
            self_consumption, savings_self,
            feed_in, earnings_feed,
        )

        # Benachrichtige alle Entities über die initialisierten Werte
        self._notify_entities()

    def get_state_for_storage(self) -> dict[str, Any]:
        """Gibt den zu speichernden Zustand zurück."""
        today = date.today()
        return {
            "total_self_consumption_kwh": self._total_self_consumption_kwh,
            "total_feed_in_kwh": self._total_feed_in_kwh,
            "accumulated_savings_self": self._accumulated_savings_self,
            "accumulated_earnings_feed": self._accumulated_earnings_feed,
            "first_seen_date": self._first_seen_date.isoformat() if self._first_seen_date else None,
            # Strompreis-Tracking
            "tracked_grid_import_kwh": self._tracked_grid_import_kwh,
            "total_grid_import_cost": self._total_grid_import_cost,
            # Daily/Monthly Tracking (NEU - Fix für Persistierung)
            "daily_grid_import_kwh": self._daily_grid_import_kwh,
            "daily_grid_import_cost": self._daily_grid_import_cost,
            "daily_feed_in_earnings": self._daily_feed_in_earnings,
            "daily_feed_in_kwh": self._daily_feed_in_kwh,
            "daily_reset_date": today.isoformat(),
            "monthly_grid_import_kwh": self._monthly_grid_import_kwh,
            "monthly_grid_import_cost": self._monthly_grid_import_cost,
            "monthly_reset_month": today.month,
            "monthly_reset_year": today.year,
            # Auto-Charge Statistiken
            "auto_charge_count": self._auto_charge_count,
            "auto_charge_total_hours": self._auto_charge_total_hours,
            "auto_charge_total_kwh": self._auto_charge_total_kwh,
            "auto_charge_estimated_savings": self._auto_charge_estimated_savings,
            "tracked_wp_kwh": self._tracked_wp_kwh,
            "wp_first_seen_date": self._wp_first_seen_date.isoformat() if self._wp_first_seen_date else None,
            "string_tracked_kwh": self._string_tracked_kwh,
            "string_first_seen_date": self._string_first_seen_date.isoformat() if self._string_first_seen_date else None,
            "string_peak_w": self._string_peak_w,
            "benchmark_start_date": self._benchmark_start_date.isoformat() if self._benchmark_start_date else None,
            "benchmark_start_self_consumption": self._benchmark_start_self_consumption,
            "benchmark_start_grid_import": self._benchmark_start_grid_import,
            "benchmark_start_feed_in": self._benchmark_start_feed_in,
            "monthly_buckets": {str(k): v for k, v in self._monthly_buckets.items()},
            "monthly_bucket_month": self._monthly_bucket_month,
        }

    def get_string_production_kwh(self, entity_id: str) -> float:
        """Gibt die getrackte Produktion eines PV-Strings zurück."""
        return self._string_tracked_kwh.get(entity_id, 0.0)

    def get_string_daily_kwh(self, entity_id: str) -> float | None:
        """Gibt die durchschnittliche Tagesproduktion eines PV-Strings zurück."""
        if not self._string_first_seen_date:
            return None
        days = max(1, (date.today() - self._string_first_seen_date).days)
        tracked = self._string_tracked_kwh.get(entity_id, 0.0)
        return tracked / days if tracked > 0 else None

    def get_string_percentage(self, entity_id: str) -> float | None:
        """Gibt den prozentualen Anteil eines PV-Strings an der Gesamtproduktion zurück."""
        total = sum(self._string_tracked_kwh.values())
        if total <= 0:
            return None
        return self._string_tracked_kwh.get(entity_id, 0.0) / total * 100

    def get_string_peak_kw(self, power_entity_id: str) -> float | None:
        """Peak-Leistung in kW (gerundet auf 1 Nachkommastelle)."""
        if not power_entity_id:
            return None
        peak = self._string_peak_w.get(power_entity_id, 0.0)
        return round(peak / 1000, 1) if peak > 0 else None

    def get_string_specific_yield(self, energy_entity_id: str, installed_kwp: float) -> float | None:
        """Spezifischer Ertrag eines Strings in kWh/kWp."""
        if installed_kwp <= 0:
            return None
        tracked = self._string_tracked_kwh.get(energy_entity_id, 0.0)
        if tracked <= 0 or self._string_first_seen_date is None:
            return None
        days = max(1, (date.today() - self._string_first_seen_date).days)
        annual = tracked / days * 365
        return round(annual / installed_kwp, 0)

    def get_string_performance_ratio(self, power_entity_id: str, installed_kwp: float) -> float | None:
        """Performance Ratio: gemessener Peak / installierte Leistung in %."""
        if not power_entity_id or installed_kwp <= 0:
            return None
        peak_kw = self._string_peak_w.get(power_entity_id, 0.0) / 1000
        if peak_kw <= 0:
            return None
        return round(peak_kw / installed_kwp * 100, 1)

    def get_total_daily_production_kwh(self) -> float | None:
        """Durchschnittliche Tagesproduktion aller Strings zusammen."""
        if not self._string_first_seen_date or not self._string_tracked_kwh:
            return None
        days = max(1, (date.today() - self._string_first_seen_date).days)
        total = sum(self._string_tracked_kwh.values())
        return round(total / days, 2) if total > 0 else None

    def get_total_peak_kw(self) -> float | None:
        """Summe aller String-Peaks in kW."""
        if not self._string_peak_w:
            return None
        total = sum(self._string_peak_w.values())
        return round(total / 1000, 1) if total > 0 else None

    def _load_epex_forecast(self, state) -> None:
        """Lädt EPEX Preisprognose aus verschiedenen Attributen."""
        try:
            if state and state.attributes:
                # Versuche verschiedene Attribut-Namen (je nach Integration)
                for attr_name in ["data", "prices", "forecast", "today", "price_data", "raw_today"]:
                    data = state.attributes.get(attr_name)
                    if data and isinstance(data, list) and len(data) > 0:
                        self._epex_price_forecast = data
                        _LOGGER.debug("EPEX Preisprognose aus '%s' geladen: %d Einträge", attr_name, len(data))
                        return

                # Log verfügbare Attribute für Debugging
                attr_keys = list(state.attributes.keys())
                _LOGGER.debug("EPEX Sensor Attribute (keine Preisprognose gefunden): %s", attr_keys)
        except Exception as e:
            _LOGGER.debug("Konnte EPEX Preisprognose nicht laden: %s", e)

    def _load_solcast_forecast(self, state) -> None:
        """Lädt Solcast Prognose aus dem 'detailedHourly' Attribut."""
        try:
            if state and state.attributes:
                hourly = state.attributes.get("detailedHourly")
                if hourly and isinstance(hourly, list):
                    self._solcast_hourly_forecast = hourly
                    _LOGGER.debug("Solcast Prognose geladen: %d Einträge", len(hourly))
        except Exception as e:
            _LOGGER.debug("Konnte Solcast Prognose nicht laden: %s", e)

    def _process_energy_update(self) -> None:
        """Verarbeitet Energie-Updates INKREMENTELL."""
        current_pv = self._pv_production_kwh
        current_export = self._grid_export_kwh
        current_import = self._grid_import_kwh

        # Initialisierung: Alle _last_* Variablen müssen gesetzt sein
        if self._last_pv_production_kwh is None or self._last_grid_import_kwh is None:
            self._last_pv_production_kwh = current_pv
            self._last_grid_export_kwh = current_export
            self._last_grid_import_kwh = current_import
            _LOGGER.info(
                "Energie-Tracking initialisiert: PV=%.2f, Export=%.2f, Import=%.2f kWh",
                current_pv, current_export, current_import
            )
            return

        delta_pv = current_pv - self._last_pv_production_kwh
        delta_export = current_export - self._last_grid_export_kwh
        delta_import = current_import - self._last_grid_import_kwh

        # Schutz gegen unrealistisch große Deltas (z.B. nach Sensor-Reset oder Bug)
        # Max 50 kWh pro Update ist realistisch (50kW für 1 Stunde)
        MAX_DELTA_KWH = 50.0
        if delta_pv > MAX_DELTA_KWH:
            _LOGGER.warning(
                "PV Delta unrealistisch groß (%.1f kWh > %d), ignoriere und re-initialisiere",
                delta_pv, MAX_DELTA_KWH
            )
            self._last_pv_production_kwh = current_pv
            delta_pv = 0
        if delta_export > MAX_DELTA_KWH:
            _LOGGER.warning(
                "Export Delta unrealistisch groß (%.1f kWh > %d), ignoriere und re-initialisiere",
                delta_export, MAX_DELTA_KWH
            )
            self._last_grid_export_kwh = current_export
            delta_export = 0
        if delta_import > MAX_DELTA_KWH:
            _LOGGER.warning(
                "Import Delta unrealistisch groß (%.1f kWh > %d), ignoriere und re-initialisiere",
                delta_import, MAX_DELTA_KWH
            )
            self._last_grid_import_kwh = current_import
            delta_import = 0

        if delta_pv < 0:
            _LOGGER.debug("PV Delta negativ (%.3f), überspringe", delta_pv)
            self._last_pv_production_kwh = current_pv
            delta_pv = 0

        if delta_export < 0:
            _LOGGER.debug("Export Delta negativ (%.3f), überspringe", delta_export)
            self._last_grid_export_kwh = current_export
            delta_export = 0

        if delta_import < 0:
            _LOGGER.debug("Import Delta negativ (%.3f), überspringe", delta_import)
            self._last_grid_import_kwh = current_import
            delta_import = 0

        delta_self_consumption = max(0.0, delta_pv - delta_export)

        # Tägliches Tracking: Reset bei Tageswechsel
        today = date.today()
        if self._daily_tracking_date != today:
            self._daily_grid_import_cost = 0.0
            self._daily_grid_import_kwh = 0.0
            self._daily_feed_in_earnings = 0.0
            self._daily_feed_in_kwh = 0.0
            self._daily_tracking_date = today

        if delta_self_consumption > 0 or delta_export > 0:
            price_electricity = self.current_electricity_price
            price_feed_in = self.current_feed_in_tariff

            savings_delta = delta_self_consumption * price_electricity
            earnings_delta = delta_export * price_feed_in

            self._total_self_consumption_kwh += delta_self_consumption
            self._total_feed_in_kwh += delta_export
            self._accumulated_savings_self += savings_delta
            self._accumulated_earnings_feed += earnings_delta
            self._daily_feed_in_earnings += earnings_delta
            self._daily_feed_in_kwh += delta_export

            _LOGGER.debug(
                "Delta: +%.3f kWh self (%.4f€), +%.3f kWh export (%.4f€)",
                delta_self_consumption, savings_delta,
                delta_export, earnings_delta,
            )

        # Strompreis-Tracking für Durchschnittsberechnung (Netzbezug)
        if delta_import > 0:
            price_electricity = self.current_electricity_price
            import_cost = delta_import * price_electricity

            # Gesamt-Tracking
            self._tracked_grid_import_kwh += delta_import
            self._total_grid_import_cost += import_cost

            self._daily_grid_import_kwh += delta_import
            self._daily_grid_import_cost += import_cost

            # Monatliches Tracking (Reset bei Monatswechsel)
            current_month = today.month
            if self._monthly_tracking_month != current_month:
                self._monthly_grid_import_cost = 0.0
                self._monthly_grid_import_kwh = 0.0
                self._monthly_tracking_month = current_month
            self._monthly_grid_import_kwh += delta_import
            self._monthly_grid_import_cost += import_cost

            _LOGGER.debug(
                "Import Delta: +%.3f kWh × %.4f€/kWh = %.4f€ (Durchschnitt: %.2f ct/kWh)",
                delta_import, price_electricity, import_cost,
                (self._total_grid_import_cost / self._tracked_grid_import_kwh * 100) if self._tracked_grid_import_kwh > 0 else 0
            )

        # Monatlicher Bucket (Rolling 12-Month)
        current_month_bucket = today.month
        if self._monthly_bucket_month != current_month_bucket:
            self._monthly_buckets[current_month_bucket] = {
                "self_consumption": 0.0,
                "grid_import": 0.0,
                "feed_in": 0.0,
                "wp": 0.0,
            }
            self._monthly_bucket_month = current_month_bucket

        bucket = self._monthly_buckets[current_month_bucket]
        bucket["self_consumption"] += delta_self_consumption
        bucket["grid_import"] += delta_import
        bucket["feed_in"] += delta_export

        self._last_pv_production_kwh = current_pv
        self._last_grid_export_kwh = current_export
        self._last_grid_import_kwh = current_import
        self._notify_entities()

    @callback
    def _on_state_changed(self, event: Event) -> None:
        """Handler für Zustandsänderungen der überwachten Entities."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")

        if not new_state or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        try:
            value = float(new_state.state)
        except (ValueError, TypeError):
            return

        if self._first_seen_date is None:
            self._first_seen_date = date.today()

        changed = False
        recommendation_changed = False

        # Energie-Sensoren (für Amortisation)
        if entity_id == self.pv_production_entity:
            self._pv_production_kwh = value
            changed = True
        elif entity_id == self.grid_export_entity:
            self._grid_export_kwh = value
            changed = True
        elif entity_id == self.grid_import_entity:
            self._grid_import_kwh = value
            changed = True  # Wichtig für Strompreis-Tracking!
        elif entity_id == self.consumption_entity:
            self._consumption_kwh = value

        # Empfehlungs-Sensoren
        elif entity_id == self.battery_soc_entity:
            self._battery_soc = value
            recommendation_changed = True
        elif entity_id == self.pv_power_entity:
            self._pv_power = value
            recommendation_changed = True
        elif entity_id == self.pv_forecast_entity:
            self._pv_forecast = value
            recommendation_changed = True

        # EPEX Spot Sensoren
        elif entity_id == self.epex_price_entity:
            self._epex_price = value
            # Versuche Preisprognose aus 'data' Attribut zu laden
            self._load_epex_forecast(new_state)
            recommendation_changed = True
        elif entity_id == self.epex_quantile_entity:
            self._epex_quantile = value
            # Versuche auch hier Preisprognose zu laden (manche Integrationen haben sie hier)
            if not self._epex_price_forecast:
                self._load_epex_forecast(new_state)
            recommendation_changed = True

        # Solcast Sensor
        elif entity_id == self.solcast_forecast_entity:
            self._solcast_forecast_today = value
            # Versuche stündliche Prognose aus 'detailedHourly' Attribut zu laden
            self._load_solcast_forecast(new_state)
            recommendation_changed = True

        # Wärmepumpe (Delta-Tracking)
        elif entity_id == self.benchmark_heatpump_entity:
            state_obj = self.hass.states.get(entity_id)
            uom = state_obj.attributes.get("unit_of_measurement", "") if state_obj else ""
            if uom in ("Wh", "wh"):
                value = value / 1000
            if self._wp_first_seen_date is None:
                self._wp_first_seen_date = date.today()
            if self._last_wp_kwh is not None and value >= self._last_wp_kwh:
                delta = value - self._last_wp_kwh
                # Sanity check: max 200 kWh pro Update (verhindert Absolutwert als Delta)
                if delta < 200:
                    self._tracked_wp_kwh += delta
                    # WP-Bucket-Update
                    if self._monthly_bucket_month is not None and self._monthly_bucket_month in self._monthly_buckets:
                        self._monthly_buckets[self._monthly_bucket_month]["wp"] += delta
            self._last_wp_kwh = value
            self._notify_entities()

        # PV-Strings (Delta-Tracking)
        elif entity_id in self._string_entity_ids:
            if self._string_first_seen_date is None:
                self._string_first_seen_date = date.today()
            last = self._string_last_kwh.get(entity_id)
            if last is not None and value >= last:
                self._string_tracked_kwh[entity_id] = (
                    self._string_tracked_kwh.get(entity_id, 0.0) + (value - last)
                )
            self._string_last_kwh[entity_id] = value
            self._notify_entities()

        # PV-String Power Peak-Tracking
        elif entity_id in self._string_power_entity_ids:
            current_peak = self._string_peak_w.get(entity_id, 0.0)
            if value > current_peak:
                self._string_peak_w[entity_id] = value
                self._notify_entities()

        if changed:
            self._process_energy_update()
        elif recommendation_changed:
            self._notify_entities()

    async def async_start(self) -> None:
        """Startet das Tracking."""
        # Initiale Werte laden - Energie
        for entity_id, attr in [
            (self.pv_production_entity, "_pv_production_kwh"),
            (self.grid_export_entity, "_grid_export_kwh"),
            (self.grid_import_entity, "_grid_import_kwh"),
            (self.consumption_entity, "_consumption_kwh"),
        ]:
            if entity_id:
                state = self.hass.states.get(entity_id)
                if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        setattr(self, attr, float(state.state))
                    except (ValueError, TypeError):
                        pass

        # Initiale Werte laden - Empfehlung
        for entity_id, attr in [
            (self.battery_soc_entity, "_battery_soc"),
            (self.pv_power_entity, "_pv_power"),
            (self.pv_forecast_entity, "_pv_forecast"),
        ]:
            if entity_id:
                state = self.hass.states.get(entity_id)
                if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        setattr(self, attr, float(state.state))
                    except (ValueError, TypeError):
                        pass

        # Initiale Werte laden - EPEX Spot
        if self.epex_price_entity:
            state = self.hass.states.get(self.epex_price_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._epex_price = float(state.state)
                    self._load_epex_forecast(state)
                except (ValueError, TypeError):
                    pass

        if self.epex_quantile_entity:
            state = self.hass.states.get(self.epex_quantile_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._epex_quantile = float(state.state)
                    # Versuche auch hier Preisprognose zu laden
                    if not self._epex_price_forecast:
                        self._load_epex_forecast(state)
                except (ValueError, TypeError):
                    pass

        # Initiale Werte laden - Solcast
        if self.solcast_forecast_entity:
            state = self.hass.states.get(self.solcast_forecast_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._solcast_forecast_today = float(state.state)
                    self._load_solcast_forecast(state)
                except (ValueError, TypeError):
                    pass

        self._last_pv_production_kwh = self._pv_production_kwh
        self._last_grid_export_kwh = self._grid_export_kwh
        self._last_grid_import_kwh = self._grid_import_kwh
        self._last_consumption_kwh = self._consumption_kwh

        # WP-Sensor initialisieren (last-Wert + first_seen_date)
        if self.benchmark_heatpump_entity:
            state = self.hass.states.get(self.benchmark_heatpump_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    val = float(state.state)
                    uom = state.attributes.get("unit_of_measurement", "")
                    if uom in ("Wh", "wh"):
                        val = val / 1000
                    self._last_wp_kwh = val
                    if self._wp_first_seen_date is None:
                        self._wp_first_seen_date = date.today()
                except (ValueError, TypeError):
                    pass

        # PV-Strings initialisieren
        for _, entity_id, power_entity, _ in self.pv_strings:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._string_last_kwh[entity_id] = float(state.state)
                except (ValueError, TypeError):
                    pass
            if power_entity:
                p_state = self.hass.states.get(power_entity)
                if p_state and p_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        val = float(p_state.state)
                        current = self._string_peak_w.get(power_entity, 0.0)
                        if val > current:
                            self._string_peak_w[power_entity] = val
                    except (ValueError, TypeError):
                        pass
        if self.pv_strings and self._string_first_seen_date is None:
            self._string_first_seen_date = date.today()

        _LOGGER.debug(
            "async_start: Sensor-Werte geladen - PV=%.2f, Export=%.2f, _restored=%s, _total_self=%.2f",
            self._pv_production_kwh,
            self._grid_export_kwh,
            self._restored,
            self._total_self_consumption_kwh,
        )

        # Benchmark-Snapshot auto-initialisieren (frischer Start)
        if self.benchmark_enabled and self._benchmark_start_date is None:
            self._benchmark_start_date = date.today()
            self._benchmark_start_self_consumption = self._total_self_consumption_kwh
            self._benchmark_start_grid_import = self._tracked_grid_import_kwh
            self._benchmark_start_feed_in = self._total_feed_in_kwh
            _LOGGER.info(
                "Benchmark-Snapshot initialisiert: date=%s, self=%.2f, grid=%.2f, feed=%.2f",
                self._benchmark_start_date,
                self._benchmark_start_self_consumption,
                self._benchmark_start_grid_import,
                self._benchmark_start_feed_in,
            )

        # Versuche zuerst vom Helper zu restoren (falls konfiguriert)
        if self.restore_from_helper and self.amortisation_helper:
            restored = await self._restore_from_helper()
            if restored:
                _LOGGER.info("Amortisation erfolgreich von Helper wiederhergestellt")

        # NICHT sofort initialisieren! Warte bis restore_state() sicher gelaufen ist.
        # Verwende async_call_later für robustere Verzögerung.
        @callback
        def delayed_init_check(_now: datetime) -> None:
            """Prüfe nach Verzögerung ob Initialisierung nötig ist."""
            _LOGGER.debug(
                "delayed_init_check: _restored=%s, _total_self=%.2f",
                self._restored,
                self._total_self_consumption_kwh,
            )
            if not self._restored and self._total_self_consumption_kwh == 0:
                _LOGGER.info(
                    "Keine restored Daten gefunden nach 60s Wartezeit, initialisiere von Sensoren"
                )
                self._initialize_from_sensors()
            elif self._restored:
                _LOGGER.info(
                    "Restored Daten OK: %.2f kWh Eigenverbrauch, %.2f kWh Einspeisung",
                    self._total_self_consumption_kwh,
                    self._total_feed_in_kwh,
                )

        # Warte 60 Sekunden bevor wir prüfen - Inverter-Integration braucht oft länger
        from homeassistant.helpers.event import async_call_later
        async_call_later(self.hass, 60.0, delayed_init_check)

        @callback
        def state_listener(event: Event):
            self._on_state_changed(event)

        self._remove_listeners.append(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, state_listener)
        )

        self._notify_entities()

    async def async_stop(self) -> None:
        """Stoppt das Tracking."""
        for remove in self._remove_listeners:
            remove()
        self._remove_listeners.clear()
        self._entity_listeners.clear()  # Alle Entity-Listener entfernen

    def set_options(self, **kwargs) -> None:
        """Setzt Optionen zur Laufzeit."""
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)

    def reset_benchmark_tracking(self) -> None:
        """Setzt Benchmark/WP-Tracking zurück mit neuem Snapshot."""
        _LOGGER.info("Benchmark-Tracking wird zurückgesetzt (WP war: %.2f kWh)", self._tracked_wp_kwh)
        self._tracked_wp_kwh = 0.0
        self._wp_first_seen_date = None
        self._last_wp_kwh = None
        # Neuen Snapshot erstellen
        self._benchmark_start_date = date.today()
        self._benchmark_start_self_consumption = self._total_self_consumption_kwh
        self._benchmark_start_grid_import = self._tracked_grid_import_kwh
        self._benchmark_start_feed_in = self._total_feed_in_kwh
        # Monthly Buckets zurücksetzen
        self._monthly_buckets = {}
        self._monthly_bucket_month = None
        self._notify_entities()

    def reset_pv_strings_tracking(self) -> None:
        """Setzt PV-String-Tracking und Peaks zurück."""
        _LOGGER.info("PV-Strings-Tracking wird zurückgesetzt")
        self._string_tracked_kwh.clear()
        self._string_last_kwh.clear()
        self._string_first_seen_date = None
        self._string_peak_w.clear()
        self._notify_entities()

    def reset_grid_import_tracking(self) -> None:
        """Setzt das Strompreis-Tracking auf 0 zurück."""
        _LOGGER.info(
            "Strompreis-Tracking wird zurückgesetzt (war: %.2f kWh, %.2f €)",
            self._tracked_grid_import_kwh,
            self._total_grid_import_cost
        )
        self._tracked_grid_import_kwh = 0.0
        self._total_grid_import_cost = 0.0
        self._daily_grid_import_kwh = 0.0
        self._daily_grid_import_cost = 0.0
        self._monthly_grid_import_kwh = 0.0
        self._monthly_grid_import_cost = 0.0
        # Re-initialisiere auch den last-Wert um erneuten Sprung zu vermeiden
        self._last_grid_import_kwh = self._grid_import_kwh
        self._notify_entities()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup der Integration."""
    ctrl = PVManagementController(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_CTRL: ctrl}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await ctrl.async_start()

    # Service zum Zurücksetzen des Strompreis-Trackings registrieren
    async def handle_reset_grid_import(call):
        """Handle reset_grid_import service call."""
        for entry_data in hass.data.get(DOMAIN, {}).values():
            controller = entry_data.get(DATA_CTRL)
            if controller:
                controller.reset_grid_import_tracking()

    if not hass.services.has_service(DOMAIN, "reset_grid_import"):
        hass.services.async_register(
            DOMAIN,
            "reset_grid_import",
            handle_reset_grid_import,
        )

    entry.add_update_listener(_async_update_listener)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entlädt die Integration."""
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            ctrl = hass.data[DOMAIN][entry.entry_id].get(DATA_CTRL)
            if ctrl:
                await ctrl.async_stop()
            hass.data[DOMAIN].pop(entry.entry_id, None)
        return unload_ok
    except Exception as e:
        _LOGGER.error("Fehler beim Entladen: %s", e)
        return False


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handler für Options-Updates - aktualisiert nur die Optionen ohne Reload."""
    try:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            ctrl = hass.data[DOMAIN][entry.entry_id].get(DATA_CTRL)
            if ctrl:
                # Check if structural changes require reload
                old_benchmark = ctrl.benchmark_enabled
                old_heatpump = ctrl.benchmark_heatpump

                ctrl._load_options()
                ctrl._notify_entities()
                _LOGGER.info("PV Management Optionen aktualisiert")

                # Reload if benchmark enabled/disabled or heatpump toggled
                if ctrl.benchmark_enabled != old_benchmark or ctrl.benchmark_heatpump != old_heatpump:
                    _LOGGER.info("Benchmark config changed, reloading integration")
                    await hass.config_entries.async_reload(entry.entry_id)
    except Exception as e:
        _LOGGER.error("Fehler beim Aktualisieren der Optionen: %s", e)
