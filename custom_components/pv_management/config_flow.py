from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_NAME, CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
    CONF_BATTERY_SOC_ENTITY, CONF_PV_POWER_ENTITY, CONF_PV_FORECAST_ENTITY,
    CONF_ELECTRICITY_PRICE, CONF_ELECTRICITY_PRICE_ENTITY, CONF_ELECTRICITY_PRICE_UNIT,
    CONF_FEED_IN_TARIFF, CONF_FEED_IN_TARIFF_ENTITY, CONF_FEED_IN_TARIFF_UNIT,
    CONF_INSTALLATION_COST, CONF_INSTALLATION_DATE,
    CONF_BATTERY_SOC_HIGH, CONF_BATTERY_SOC_LOW,
    CONF_PRICE_HIGH_THRESHOLD, CONF_PRICE_LOW_THRESHOLD, CONF_PV_POWER_HIGH,
    CONF_PV_PEAK_POWER, CONF_WINTER_BASE_LOAD, CONF_SAVINGS_OFFSET,
    CONF_EPEX_PRICE_ENTITY, CONF_EPEX_QUANTILE_ENTITY, CONF_SOLCAST_FORECAST_ENTITY,
    CONF_AUTO_CHARGE_WINTER_ONLY, CONF_AUTO_CHARGE_PV_THRESHOLD, CONF_AUTO_CHARGE_PRICE_QUANTILE,
    CONF_AUTO_CHARGE_MIN_SOC, CONF_AUTO_CHARGE_MIN_PRICE_DIFF,
    CONF_AUTO_CHARGE_POWER,
    CONF_BATTERY_TARGET_SOC,  # Gemeinsame Einstellung für Ziel/Halte-SOC
    CONF_DISCHARGE_WINTER_ONLY, CONF_DISCHARGE_PRICE_QUANTILE,
    CONF_DISCHARGE_ALLOW_SOC, CONF_DISCHARGE_SUMMER_SOC,
    CONF_AMORTISATION_HELPER, CONF_RESTORE_FROM_HELPER,  # NEU: Helper Sync
    CONF_FIXED_PRICE_COMPARE,  # NEU: Fixpreis-Vergleich
    DEFAULT_NAME, DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    DEFAULT_BATTERY_SOC_HIGH, DEFAULT_BATTERY_SOC_LOW,
    DEFAULT_PRICE_HIGH_THRESHOLD, DEFAULT_PRICE_LOW_THRESHOLD, DEFAULT_PV_POWER_HIGH,
    DEFAULT_PV_PEAK_POWER, DEFAULT_WINTER_BASE_LOAD,
    DEFAULT_AUTO_CHARGE_WINTER_ONLY, DEFAULT_AUTO_CHARGE_PV_THRESHOLD, DEFAULT_AUTO_CHARGE_PRICE_QUANTILE,
    DEFAULT_AUTO_CHARGE_MIN_SOC, DEFAULT_AUTO_CHARGE_MIN_PRICE_DIFF,
    DEFAULT_AUTO_CHARGE_POWER,
    DEFAULT_BATTERY_TARGET_SOC,  # Gemeinsamer Default
    DEFAULT_DISCHARGE_WINTER_ONLY, DEFAULT_DISCHARGE_PRICE_QUANTILE,
    DEFAULT_DISCHARGE_ALLOW_SOC, DEFAULT_DISCHARGE_SUMMER_SOC,
    DEFAULT_FIXED_PRICE_COMPARE,  # NEU
    RANGE_COST, RANGE_OFFSET, RANGE_BATTERY_SOC, RANGE_PV_POWER,
    PRICE_UNIT_EUR, PRICE_UNIT_CENT,
    CONF_BENCHMARK_ENABLED, CONF_BENCHMARK_HOUSEHOLD_SIZE, CONF_BENCHMARK_COUNTRY,
    CONF_BENCHMARK_HEATPUMP, CONF_BENCHMARK_HEATPUMP_ENTITY,
    DEFAULT_BENCHMARK_ENABLED, DEFAULT_BENCHMARK_HOUSEHOLD_SIZE, DEFAULT_BENCHMARK_COUNTRY,
    DEFAULT_BENCHMARK_HEATPUMP, RANGE_HOUSEHOLD_SIZE,
)


class PVManagementConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow für PV Management."""

    VERSION = 2

    async def async_step_user(self, user_input=None):
        """Erster Schritt: Basis-Konfiguration."""
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,

                # === ENERGIE-SENSOREN ===
                vol.Required(CONF_PV_PRODUCTION_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_GRID_EXPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_GRID_IMPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_CONSUMPTION_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),

                # === PREISE ===
                vol.Required(CONF_ELECTRICITY_PRICE_UNIT, default=DEFAULT_ELECTRICITY_PRICE_UNIT):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                vol.Required(CONF_ELECTRICITY_PRICE, default=DEFAULT_ELECTRICITY_PRICE):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=100.0, step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                vol.Required(CONF_FEED_IN_TARIFF_UNIT, default=DEFAULT_FEED_IN_TARIFF_UNIT):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                vol.Required(CONF_FEED_IN_TARIFF, default=DEFAULT_FEED_IN_TARIFF):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=50.0, step=0.001,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # === AMORTISATION ===
                vol.Required(CONF_INSTALLATION_COST, default=DEFAULT_INSTALLATION_COST):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_COST["min"], max=RANGE_COST["max"], step=RANGE_COST["step"],
                            unit_of_measurement="€",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_INSTALLATION_DATE): selector.DateSelector(),

                # === AMORTISATION HELPER (Pflicht für Persistenz) ===
                vol.Required(CONF_AMORTISATION_HELPER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="input_number")
                ),
                vol.Optional(CONF_RESTORE_FROM_HELPER, default=False): selector.BooleanSelector(),
            })
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return PVManagementOptionsFlow()


class PVManagementOptionsFlow(config_entries.OptionsFlow):
    """Options Flow mit Menü-Struktur."""

    def __init__(self):
        self._data = {}

    def _get_val(self, key, default=None):
        """Holt aktuellen Wert aus Options oder Data."""
        # Zuerst in temporären Daten schauen
        if key in self._data:
            return self._data[key]
        # Dann in Options
        if key in self.config_entry.options:
            return self.config_entry.options[key]
        # Dann in Data
        if key in self.config_entry.data:
            return self.config_entry.data[key]
        return default

    async def async_step_init(self, user_input=None):
        """Hauptmenü mit Kategorien."""
        return self.async_show_menu(
            step_id="init",
            menu_options={
                "sensors": "Sensoren",
                "prices": "Strompreise",
                "integrations": "Integrationen (EPEX/Solcast)",
                "helper": "Amortisation Helper",
                "battery": "Batterie-Steuerung",
                "advanced": "Erweiterte Einstellungen",
                "benchmark": "Energie-Benchmark",
                "save": "Speichern & Schließen",
            },
        )

    async def _save_and_return_to_menu(self, user_input):
        """Speichert die Options und zeigt das Menü wieder an."""
        self._data.update(user_input)
        # Sofort speichern
        final_data = {}
        final_data.update(self.config_entry.options)
        final_data.update(self._data)
        self.hass.config_entries.async_update_entry(self.config_entry, options=final_data)
        return await self.async_step_init()

    async def async_step_sensors(self, user_input=None):
        """Energie-Sensoren konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema({
                vol.Required(CONF_PV_PRODUCTION_ENTITY, default=self._get_val(CONF_PV_PRODUCTION_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_GRID_EXPORT_ENTITY, default=self._get_val(CONF_GRID_EXPORT_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_GRID_IMPORT_ENTITY, default=self._get_val(CONF_GRID_IMPORT_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_CONSUMPTION_ENTITY, default=self._get_val(CONF_CONSUMPTION_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_BATTERY_SOC_ENTITY, default=self._get_val(CONF_BATTERY_SOC_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_PV_POWER_ENTITY, default=self._get_val(CONF_PV_POWER_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_PV_FORECAST_ENTITY, default=self._get_val(CONF_PV_FORECAST_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            })
        )

    async def async_step_prices(self, user_input=None):
        """Strompreise konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="prices",
            data_schema=vol.Schema({
                # Strompreis
                vol.Required(CONF_ELECTRICITY_PRICE_UNIT, default=self._get_val(CONF_ELECTRICITY_PRICE_UNIT, DEFAULT_ELECTRICITY_PRICE_UNIT)):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                vol.Required(CONF_ELECTRICITY_PRICE, default=self._get_val(CONF_ELECTRICITY_PRICE, DEFAULT_ELECTRICITY_PRICE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=100.0, step=0.01, mode=selector.NumberSelectorMode.BOX)
                    ),
                vol.Optional(CONF_ELECTRICITY_PRICE_ENTITY, default=self._get_val(CONF_ELECTRICITY_PRICE_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),

                # Einspeisevergütung
                vol.Required(CONF_FEED_IN_TARIFF_UNIT, default=self._get_val(CONF_FEED_IN_TARIFF_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT)):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                vol.Required(CONF_FEED_IN_TARIFF, default=self._get_val(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=50.0, step=0.001, mode=selector.NumberSelectorMode.BOX)
                    ),
                vol.Optional(CONF_FEED_IN_TARIFF_ENTITY, default=self._get_val(CONF_FEED_IN_TARIFF_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),

                # Fixpreis-Vergleich (für Spot vs. Fixpreis Berechnung)
                vol.Optional(CONF_FIXED_PRICE_COMPARE, default=self._get_val(CONF_FIXED_PRICE_COMPARE, DEFAULT_FIXED_PRICE_COMPARE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=5.0, max=50.0, step=0.1,
                            unit_of_measurement="ct/kWh", mode=selector.NumberSelectorMode.BOX
                        )
                    ),

                # Amortisation
                vol.Required(CONF_INSTALLATION_COST, default=self._get_val(CONF_INSTALLATION_COST, DEFAULT_INSTALLATION_COST)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_COST["min"], max=RANGE_COST["max"], step=RANGE_COST["step"],
                            unit_of_measurement="€", mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                vol.Optional(CONF_INSTALLATION_DATE, default=self._get_val(CONF_INSTALLATION_DATE)):
                    selector.DateSelector(),
            })
        )

    async def async_step_helper(self, user_input=None):
        """Amortisation Helper konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="helper",
            data_schema=vol.Schema({
                vol.Required(CONF_AMORTISATION_HELPER, default=self._get_val(CONF_AMORTISATION_HELPER)):
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="input_number")
                    ),
                vol.Optional(CONF_RESTORE_FROM_HELPER, default=self._get_val(CONF_RESTORE_FROM_HELPER, False)):
                    selector.BooleanSelector(),
            }),
            description_placeholders={
                "info": "Der Helper speichert die Gesamtersparnis (EUR) unabhängig von der Integration."
            }
        )

    async def async_step_integrations(self, user_input=None):
        """EPEX Spot und Solcast Integrationen."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="integrations",
            data_schema=vol.Schema({
                # EPEX Spot
                vol.Optional(CONF_EPEX_PRICE_ENTITY, default=self._get_val(CONF_EPEX_PRICE_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_EPEX_QUANTILE_ENTITY, default=self._get_val(CONF_EPEX_QUANTILE_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),

                # Solcast
                vol.Optional(CONF_SOLCAST_FORECAST_ENTITY, default=self._get_val(CONF_SOLCAST_FORECAST_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            })
        )

    async def async_step_battery(self, user_input=None):
        """Batterie-Steuerung: Auto-Charge und Entlade-Steuerung kombiniert."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="battery",
            data_schema=vol.Schema({
                # === GEMEINSAME EINSTELLUNG ===
                vol.Optional(CONF_BATTERY_TARGET_SOC, default=self._get_val(CONF_BATTERY_TARGET_SOC, DEFAULT_BATTERY_TARGET_SOC)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=100.0, step=5.0, unit_of_measurement="%", mode=selector.NumberSelectorMode.SLIDER)
                    ),

                # === AUTO-CHARGE (Netzladen bei guenstigen Preisen) ===
                vol.Optional(CONF_AUTO_CHARGE_WINTER_ONLY, default=self._get_val(CONF_AUTO_CHARGE_WINTER_ONLY, DEFAULT_AUTO_CHARGE_WINTER_ONLY)):
                    selector.BooleanSelector(),

                vol.Optional(CONF_AUTO_CHARGE_PV_THRESHOLD, default=self._get_val(CONF_AUTO_CHARGE_PV_THRESHOLD, DEFAULT_AUTO_CHARGE_PV_THRESHOLD)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=50.0, step=0.5, unit_of_measurement="kWh", mode=selector.NumberSelectorMode.BOX)
                    ),

                vol.Optional(CONF_AUTO_CHARGE_PRICE_QUANTILE, default=self._get_val(CONF_AUTO_CHARGE_PRICE_QUANTILE, DEFAULT_AUTO_CHARGE_PRICE_QUANTILE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=1.0, step=0.05, mode=selector.NumberSelectorMode.SLIDER)
                    ),

                vol.Optional(CONF_AUTO_CHARGE_MIN_PRICE_DIFF, default=self._get_val(CONF_AUTO_CHARGE_MIN_PRICE_DIFF, DEFAULT_AUTO_CHARGE_MIN_PRICE_DIFF)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=30.0, step=0.5, unit_of_measurement="ct/kWh", mode=selector.NumberSelectorMode.BOX)
                    ),

                vol.Optional(CONF_AUTO_CHARGE_MIN_SOC, default=self._get_val(CONF_AUTO_CHARGE_MIN_SOC, DEFAULT_AUTO_CHARGE_MIN_SOC)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=100.0, step=5.0, unit_of_measurement="%", mode=selector.NumberSelectorMode.SLIDER)
                    ),

                vol.Optional(CONF_AUTO_CHARGE_POWER, default=self._get_val(CONF_AUTO_CHARGE_POWER, DEFAULT_AUTO_CHARGE_POWER)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=500.0, max=10000.0, step=100.0, unit_of_measurement="W", mode=selector.NumberSelectorMode.BOX)
                    ),

                # === ENTLADE-STEUERUNG (Batterie bei guenstigen Preisen halten) ===
                vol.Optional(CONF_DISCHARGE_WINTER_ONLY, default=self._get_val(CONF_DISCHARGE_WINTER_ONLY, DEFAULT_DISCHARGE_WINTER_ONLY)):
                    selector.BooleanSelector(),

                vol.Optional(CONF_DISCHARGE_PRICE_QUANTILE, default=self._get_val(CONF_DISCHARGE_PRICE_QUANTILE, DEFAULT_DISCHARGE_PRICE_QUANTILE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=1.0, step=0.05, mode=selector.NumberSelectorMode.SLIDER)
                    ),

                vol.Optional(CONF_DISCHARGE_ALLOW_SOC, default=self._get_val(CONF_DISCHARGE_ALLOW_SOC, DEFAULT_DISCHARGE_ALLOW_SOC)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=100.0, step=5.0, unit_of_measurement="%", mode=selector.NumberSelectorMode.SLIDER)
                    ),

                vol.Optional(CONF_DISCHARGE_SUMMER_SOC, default=self._get_val(CONF_DISCHARGE_SUMMER_SOC, DEFAULT_DISCHARGE_SUMMER_SOC)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=100.0, step=5.0, unit_of_measurement="%", mode=selector.NumberSelectorMode.SLIDER)
                    ),
            })
        )

    async def async_step_advanced(self, user_input=None):
        """Erweiterte Einstellungen (Schwellwerte, etc.)."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema({
                # PV-Anlage
                vol.Optional(CONF_PV_PEAK_POWER, default=self._get_val(CONF_PV_PEAK_POWER, DEFAULT_PV_PEAK_POWER)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1000.0, max=100000.0, step=100.0, unit_of_measurement="W", mode=selector.NumberSelectorMode.BOX)
                    ),

                vol.Optional(CONF_WINTER_BASE_LOAD, default=self._get_val(CONF_WINTER_BASE_LOAD, DEFAULT_WINTER_BASE_LOAD)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=10000.0, step=100.0, unit_of_measurement="W", mode=selector.NumberSelectorMode.BOX)
                    ),

                # Batterie-Schwellwerte für Empfehlungs-Ampel
                vol.Optional(CONF_BATTERY_SOC_HIGH, default=self._get_val(CONF_BATTERY_SOC_HIGH, DEFAULT_BATTERY_SOC_HIGH)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_BATTERY_SOC["min"], max=RANGE_BATTERY_SOC["max"], step=RANGE_BATTERY_SOC["step"],
                            unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
                        )
                    ),

                vol.Optional(CONF_BATTERY_SOC_LOW, default=self._get_val(CONF_BATTERY_SOC_LOW, DEFAULT_BATTERY_SOC_LOW)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_BATTERY_SOC["min"], max=RANGE_BATTERY_SOC["max"], step=RANGE_BATTERY_SOC["step"],
                            unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
                        )
                    ),

                # Preis-Schwellwerte für Empfehlungs-Ampel
                vol.Optional(CONF_PRICE_LOW_THRESHOLD, default=self._get_val(CONF_PRICE_LOW_THRESHOLD, DEFAULT_PRICE_LOW_THRESHOLD)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=1.0, step=0.01, unit_of_measurement="€/kWh", mode=selector.NumberSelectorMode.BOX)
                    ),

                vol.Optional(CONF_PRICE_HIGH_THRESHOLD, default=self._get_val(CONF_PRICE_HIGH_THRESHOLD, DEFAULT_PRICE_HIGH_THRESHOLD)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=1.0, step=0.01, unit_of_measurement="€/kWh", mode=selector.NumberSelectorMode.BOX)
                    ),
            })
        )

    async def async_step_benchmark(self, user_input=None):
        """Energie-Benchmark konfigurieren."""
        if user_input is not None:
            # Clean up optional entity if empty
            if not user_input.get(CONF_BENCHMARK_HEATPUMP_ENTITY):
                user_input.pop(CONF_BENCHMARK_HEATPUMP_ENTITY, None)
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="benchmark",
            data_schema=vol.Schema({
                vol.Optional(CONF_BENCHMARK_ENABLED, default=self._get_val(CONF_BENCHMARK_ENABLED, DEFAULT_BENCHMARK_ENABLED)):
                    selector.BooleanSelector(),
                vol.Optional(CONF_BENCHMARK_COUNTRY, default=self._get_val(CONF_BENCHMARK_COUNTRY, DEFAULT_BENCHMARK_COUNTRY)):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value="AT", label="Oesterreich"),
                                selector.SelectOptionDict(value="DE", label="Deutschland"),
                                selector.SelectOptionDict(value="CH", label="Schweiz"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                vol.Optional(CONF_BENCHMARK_HOUSEHOLD_SIZE, default=self._get_val(CONF_BENCHMARK_HOUSEHOLD_SIZE, DEFAULT_BENCHMARK_HOUSEHOLD_SIZE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_HOUSEHOLD_SIZE["min"],
                            max=RANGE_HOUSEHOLD_SIZE["max"],
                            step=RANGE_HOUSEHOLD_SIZE["step"],
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_BENCHMARK_HEATPUMP, default=self._get_val(CONF_BENCHMARK_HEATPUMP, DEFAULT_BENCHMARK_HEATPUMP)):
                    selector.BooleanSelector(),
                vol.Optional(CONF_BENCHMARK_HEATPUMP_ENTITY, default=self._get_val(CONF_BENCHMARK_HEATPUMP_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            })
        )

    async def async_step_save(self, user_input=None):
        """Speichert alle Änderungen."""
        # Alle bestehenden Optionen und Daten zusammenführen
        final_data = {}
        final_data.update(self.config_entry.options)
        final_data.update(self._data)
        return self.async_create_entry(title="", data=final_data)
