from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Any

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
    CONF_INSTALLATION_COST, CONF_INSTALLATION_DATE,
    CONF_BATTERY_SOC_HIGH, CONF_BATTERY_SOC_LOW,
    CONF_PRICE_HIGH_THRESHOLD, CONF_PRICE_LOW_THRESHOLD, CONF_PV_POWER_HIGH,
    CONF_EPEX_PRICE_ENTITY, CONF_EPEX_QUANTILE_ENTITY, CONF_SOLCAST_FORECAST_ENTITY,
    DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    DEFAULT_BATTERY_SOC_HIGH, DEFAULT_BATTERY_SOC_LOW,
    DEFAULT_PRICE_HIGH_THRESHOLD, DEFAULT_PRICE_LOW_THRESHOLD, DEFAULT_PV_POWER_HIGH,
    PRICE_UNIT_CENT,
    RECOMMENDATION_DARK_GREEN, RECOMMENDATION_GREEN, RECOMMENDATION_YELLOW, RECOMMENDATION_RED,
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

        # Flag ob Werte aus Restore geladen wurden
        self._restored = False
        self._first_seen_date: date | None = None

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

        # Empfehlungs-Schwellwerte
        self.battery_soc_high = opts.get(CONF_BATTERY_SOC_HIGH, DEFAULT_BATTERY_SOC_HIGH)
        self.battery_soc_low = opts.get(CONF_BATTERY_SOC_LOW, DEFAULT_BATTERY_SOC_LOW)
        self.price_high_threshold = opts.get(CONF_PRICE_HIGH_THRESHOLD, DEFAULT_PRICE_HIGH_THRESHOLD)
        self.price_low_threshold = opts.get(CONF_PRICE_LOW_THRESHOLD, DEFAULT_PRICE_LOW_THRESHOLD)
        self.pv_power_high = opts.get(CONF_PV_POWER_HIGH, DEFAULT_PV_POWER_HIGH)

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

    @property
    def next_cheap_hour(self) -> dict | None:
        """
        Findet die nächste günstige Stunde basierend auf EPEX Preisprognose.

        Returns: {"hour": 14, "price": 0.15, "in_hours": 2} oder None
        """
        if not self._epex_price_forecast:
            return None

        try:
            now = datetime.now()
            current_hour = now.hour

            # Finde die günstigsten Stunden in den nächsten 24h
            upcoming_prices = []

            for entry in self._epex_price_forecast:
                # EPEX Spot data format kann variieren
                # Versuche verschiedene Formate
                hour = None
                price = None

                if isinstance(entry, dict):
                    # Format: {"start_time": "2024-01-05T14:00:00", "price_eur_per_kwh": 0.15}
                    start_time = entry.get("start_time") or entry.get("start") or entry.get("time")
                    price = entry.get("price_eur_per_kwh") or entry.get("price") or entry.get("total_price")

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
                    # Berechne Stunden bis zu dieser Stunde
                    hours_until = hour - current_hour
                    if hours_until < 0:
                        hours_until += 24  # Nächster Tag

                    if hours_until <= 24:  # Nur nächste 24 Stunden
                        upcoming_prices.append({
                            "hour": hour,
                            "price": float(price),
                            "in_hours": hours_until
                        })

            if not upcoming_prices:
                return None

            # Sortiere nach Preis und nimm günstigste
            upcoming_prices.sort(key=lambda x: x["price"])
            cheapest = upcoming_prices[0]

            # Wenn die günstigste Stunde jetzt ist, nimm die nächste günstige
            if cheapest["in_hours"] == 0 and len(upcoming_prices) > 1:
                # Aktuelle Stunde ist bereits günstig - zeige nächste günstige
                for p in upcoming_prices[1:]:
                    if p["in_hours"] > 0:
                        return p

            return cheapest

        except Exception as e:
            _LOGGER.debug("Fehler bei next_cheap_hour Berechnung: %s", e)
            return None

    @property
    def next_cheap_hour_text(self) -> str:
        """Menschenlesbare Ausgabe der nächsten günstigen Stunde."""
        info = self.next_cheap_hour
        if not info:
            return "Keine Prognose"

        if info["in_hours"] == 0:
            return f"Jetzt! ({info['price']:.2f}€/kWh)"
        elif info["in_hours"] == 1:
            return f"In 1 Stunde ({info['hour']}:00, {info['price']:.2f}€/kWh)"
        else:
            return f"In {info['in_hours']}h ({info['hour']}:00, {info['price']:.2f}€/kWh)"

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
        """Gesamtersparnis."""
        return self.savings_self_consumption + self.earnings_feed_in

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
        if self._first_seen_date:
            return (date.today() - self._first_seen_date).days
        return 0

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

        # === PV-Leistung (aktuell) ===
        if self._pv_power >= self.pv_power_high:
            score += 3  # Viel PV -> sehr gut
        elif self._pv_power >= self.pv_power_high * 0.5:
            score += 1  # Mittlere PV -> gut
        elif self._pv_power < 100:
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

        # === Strompreis (EPEX Quantile hat Priorität) ===
        if self.epex_quantile_entity and 0 <= self._epex_quantile <= 1:
            # EPEX Quantile: 0 = günstigster Preis, 1 = teuerster Preis
            if self._epex_quantile <= 0.2:
                score += 3  # Sehr günstig (unterste 20%)
            elif self._epex_quantile <= 0.4:
                score += 1  # Günstig (unterste 40%)
            elif self._epex_quantile >= 0.8:
                score -= 3  # Sehr teuer (oberste 20%)
            elif self._epex_quantile >= 0.6:
                score -= 1  # Teuer (oberste 40%)
        else:
            # Fallback: Absoluter Preis
            price = self.current_electricity_price
            if price <= self.price_low_threshold:
                score += 2  # Günstiger Strom -> gut
            elif price >= self.price_high_threshold:
                score -= 2  # Teurer Strom -> schlecht

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

        # === Auswertung (4 Stufen) ===
        if score >= 5:
            return RECOMMENDATION_DARK_GREEN  # Perfekt!
        elif score >= 3:
            return RECOMMENDATION_GREEN  # Jetzt verbrauchen
        elif score <= -2:
            return RECOMMENDATION_RED  # Vermeiden
        else:
            return RECOMMENDATION_YELLOW  # Neutral

    @property
    def consumption_recommendation_text(self) -> str:
        """Textuelle Empfehlung mit Begründung."""
        rec = self.consumption_recommendation
        reasons = self._get_recommendation_reasons()

        if rec == RECOMMENDATION_DARK_GREEN:
            base = "Perfekt zum Verbrauchen!"
        elif rec == RECOMMENDATION_GREEN:
            base = "Jetzt verbrauchen!"
        elif rec == RECOMMENDATION_RED:
            base = "Verbrauch vermeiden!"
        else:
            base = "Neutral"

        if reasons:
            return f"{base} ({reasons})"
        return base

    @property
    def consumption_recommendation_color(self) -> str:
        """Farbe für die Ampel (für Dashboards)."""
        rec = self.consumption_recommendation
        if rec == RECOMMENDATION_DARK_GREEN:
            return "#00aa00"  # Dunkelgrün
        elif rec == RECOMMENDATION_GREEN:
            return "#44cc44"  # Grün
        elif rec == RECOMMENDATION_YELLOW:
            return "#ffcc00"  # Gelb
        else:
            return "#cc0000"  # Rot

    def _get_recommendation_reasons(self) -> str:
        """Erstellt menschenlesbare Begründung für die Empfehlung."""
        reasons = []

        # PV-Leistung
        if self._pv_power >= self.pv_power_high:
            reasons.append("viel PV")
        elif self._pv_power < 100:
            reasons.append("kein PV")

        # Batterie
        if self.battery_soc_entity:
            if self._battery_soc >= self.battery_soc_high:
                reasons.append("Akku voll")
            elif self._battery_soc <= self.battery_soc_low:
                reasons.append("Akku leer")

        # Strompreis (EPEX oder normal)
        if self.epex_quantile_entity and 0 <= self._epex_quantile <= 1:
            if self._epex_quantile <= 0.2:
                reasons.append("Strom sehr günstig")
            elif self._epex_quantile <= 0.4:
                reasons.append("Strom günstig")
            elif self._epex_quantile >= 0.8:
                reasons.append("Strom sehr teuer")
            elif self._epex_quantile >= 0.6:
                reasons.append("Strom teuer")
        else:
            price = self.current_electricity_price
            if price <= self.price_low_threshold:
                reasons.append("Strom günstig")
            elif price >= self.price_high_threshold:
                reasons.append("Strom teuer")

        return ", ".join(reasons) if reasons else ""

    @property
    def consumption_recommendation_score(self) -> int:
        """Detaillierter Score für die Empfehlung."""
        score = 0

        if self._pv_power >= self.pv_power_high:
            score += 3
        elif self._pv_power >= self.pv_power_high * 0.5:
            score += 1
        elif self._pv_power < 100:
            score -= 1

        if self.battery_soc_entity:
            if self._battery_soc >= self.battery_soc_high:
                score += 2
            elif self._battery_soc <= self.battery_soc_low:
                score -= 2

        # EPEX Quantile hat Priorität
        if self.epex_quantile_entity and 0 <= self._epex_quantile <= 1:
            if self._epex_quantile <= 0.2:
                score += 3
            elif self._epex_quantile <= 0.4:
                score += 1
            elif self._epex_quantile >= 0.8:
                score -= 3
            elif self._epex_quantile >= 0.6:
                score -= 1
        else:
            price = self.current_electricity_price
            if price <= self.price_low_threshold:
                score += 2
            elif price >= self.price_high_threshold:
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
        for cb in list(self._entity_listeners):  # Copy list to avoid modification during iteration
            try:
                cb()
            except Exception as e:
                _LOGGER.debug("Entity-Listener Fehler (ignoriert): %s", e)

    def restore_state(self, data: dict[str, Any]) -> None:
        """Stellt den gespeicherten Zustand wieder her."""
        self._total_self_consumption_kwh = data.get("total_self_consumption_kwh", 0.0)
        self._total_feed_in_kwh = data.get("total_feed_in_kwh", 0.0)
        self._accumulated_savings_self = data.get("accumulated_savings_self", 0.0)
        self._accumulated_earnings_feed = data.get("accumulated_earnings_feed", 0.0)

        first_seen = data.get("first_seen_date")
        if first_seen:
            try:
                self._first_seen_date = date.fromisoformat(first_seen)
            except (ValueError, TypeError):
                pass

        self._restored = True
        _LOGGER.info(
            "PV Management restored: %.2f kWh self, %.2f kWh feed, %.2f€ savings, %.2f€ earnings",
            self._total_self_consumption_kwh,
            self._total_feed_in_kwh,
            self._accumulated_savings_self,
            self._accumulated_earnings_feed,
        )

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

    def get_state_for_storage(self) -> dict[str, Any]:
        """Gibt den zu speichernden Zustand zurück."""
        return {
            "total_self_consumption_kwh": self._total_self_consumption_kwh,
            "total_feed_in_kwh": self._total_feed_in_kwh,
            "accumulated_savings_self": self._accumulated_savings_self,
            "accumulated_earnings_feed": self._accumulated_earnings_feed,
            "first_seen_date": self._first_seen_date.isoformat() if self._first_seen_date else None,
        }

    def _load_epex_forecast(self, state) -> None:
        """Lädt EPEX Preisprognose aus dem 'data' Attribut."""
        try:
            if state and state.attributes:
                data = state.attributes.get("data")
                if data and isinstance(data, list):
                    self._epex_price_forecast = data
                    _LOGGER.debug("EPEX Preisprognose geladen: %d Einträge", len(data))
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

        if self._last_pv_production_kwh is None:
            self._last_pv_production_kwh = current_pv
            self._last_grid_export_kwh = current_export
            return

        delta_pv = current_pv - self._last_pv_production_kwh
        delta_export = current_export - self._last_grid_export_kwh

        if delta_pv < 0:
            _LOGGER.debug("PV Delta negativ (%.3f), überspringe", delta_pv)
            self._last_pv_production_kwh = current_pv
            delta_pv = 0

        if delta_export < 0:
            _LOGGER.debug("Export Delta negativ (%.3f), überspringe", delta_export)
            self._last_grid_export_kwh = current_export
            delta_export = 0

        delta_self_consumption = max(0.0, delta_pv - delta_export)

        if delta_self_consumption > 0 or delta_export > 0:
            price_electricity = self.current_electricity_price
            price_feed_in = self.current_feed_in_tariff

            savings_delta = delta_self_consumption * price_electricity
            earnings_delta = delta_export * price_feed_in

            self._total_self_consumption_kwh += delta_self_consumption
            self._total_feed_in_kwh += delta_export
            self._accumulated_savings_self += savings_delta
            self._accumulated_earnings_feed += earnings_delta

            _LOGGER.debug(
                "Delta: +%.3f kWh self (%.4f€), +%.3f kWh export (%.4f€)",
                delta_self_consumption, savings_delta,
                delta_export, earnings_delta,
            )

        self._last_pv_production_kwh = current_pv
        self._last_grid_export_kwh = current_export
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
            recommendation_changed = True

        # Solcast Sensor
        elif entity_id == self.solcast_forecast_entity:
            self._solcast_forecast_today = value
            # Versuche stündliche Prognose aus 'detailedHourly' Attribut zu laden
            self._load_solcast_forecast(new_state)
            recommendation_changed = True

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

        # Wenn keine restored Daten und keine akkumulierten Werte vorhanden,
        # initialisiere mit aktuellen Sensor-Werten (historische Daten)
        if not self._restored and self._total_self_consumption_kwh == 0:
            self._initialize_from_sensors()

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup der Integration."""
    ctrl = PVManagementController(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_CTRL: ctrl}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await ctrl.async_start()

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
                ctrl._load_options()
                ctrl._notify_entities()
                _LOGGER.info("PV Management Optionen aktualisiert")
    except Exception as e:
        _LOGGER.error("Fehler beim Aktualisieren der Optionen: %s", e)
