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
    DEFAULT_NAME, DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    DEFAULT_BATTERY_SOC_HIGH, DEFAULT_BATTERY_SOC_LOW,
    DEFAULT_PRICE_HIGH_THRESHOLD, DEFAULT_PRICE_LOW_THRESHOLD, DEFAULT_PV_POWER_HIGH,
    DEFAULT_PV_PEAK_POWER, DEFAULT_WINTER_BASE_LOAD,
    RANGE_COST, RANGE_OFFSET, RANGE_BATTERY_SOC, RANGE_PV_POWER,
    PRICE_UNIT_EUR, PRICE_UNIT_CENT,
)

# Hinweis: Für Autarkiegrad benötigst du einen Verbrauchs-Sensor in kWh (nicht Watt!)


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

                # === EMPFEHLUNGS-SENSOREN ===
                vol.Optional(CONF_BATTERY_SOC_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_PV_POWER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_PV_FORECAST_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),

                # === EPEX SPOT INTEGRATION ===
                vol.Optional(CONF_EPEX_PRICE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_EPEX_QUANTILE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),

                # === SOLCAST INTEGRATION ===
                vol.Optional(CONF_SOLCAST_FORECAST_ENTITY): selector.EntitySelector(
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
                vol.Optional(CONF_ELECTRICITY_PRICE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
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
                vol.Optional(CONF_FEED_IN_TARIFF_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
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
            })
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return PVManagementOptionsFlow()


class PVManagementOptionsFlow(config_entries.OptionsFlow):
    """Options Flow für nachträgliche Anpassungen."""

    async def async_step_init(self, user_input=None):
        """Options bearbeiten."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Aktuelle Werte holen (Options überschreiben Data)
        data = self.config_entry.data
        opts = self.config_entry.options

        # Helper um aktuellen Wert zu holen
        def get_val(key, default=None):
            return opts.get(key, data.get(key, default))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                # === ENERGIE-SENSOREN (kWh Totals, nicht Watt!) ===
                vol.Optional(CONF_GRID_EXPORT_ENTITY, default=get_val(CONF_GRID_EXPORT_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_GRID_IMPORT_ENTITY, default=get_val(CONF_GRID_IMPORT_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_CONSUMPTION_ENTITY, default=get_val(CONF_CONSUMPTION_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),

                # === AMORTISATION ===
                vol.Required(CONF_INSTALLATION_COST, default=get_val(CONF_INSTALLATION_COST, DEFAULT_INSTALLATION_COST)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_COST["min"], max=RANGE_COST["max"], step=RANGE_COST["step"],
                            unit_of_measurement="€",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_INSTALLATION_DATE, default=get_val(CONF_INSTALLATION_DATE)):
                    selector.DateSelector(),

                # Korrektur-Offset für Ersparnis (z.B. nach Rechnung)
                vol.Optional(CONF_SAVINGS_OFFSET, default=get_val(CONF_SAVINGS_OFFSET, DEFAULT_SAVINGS_OFFSET)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=-RANGE_OFFSET["max"], max=RANGE_OFFSET["max"], step=RANGE_OFFSET["step"],
                            unit_of_measurement="€",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # === PREISE ===
                vol.Required(CONF_ELECTRICITY_PRICE_UNIT, default=get_val(CONF_ELECTRICITY_PRICE_UNIT, DEFAULT_ELECTRICITY_PRICE_UNIT)):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),

                vol.Required(CONF_ELECTRICITY_PRICE, default=get_val(CONF_ELECTRICITY_PRICE, DEFAULT_ELECTRICITY_PRICE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=100.0, step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                vol.Required(CONF_FEED_IN_TARIFF_UNIT, default=get_val(CONF_FEED_IN_TARIFF_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT)):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),

                vol.Required(CONF_FEED_IN_TARIFF, default=get_val(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=50.0, step=0.001,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # === EMPFEHLUNGS-SCHWELLWERTE ===
                vol.Optional(CONF_BATTERY_SOC_HIGH, default=get_val(CONF_BATTERY_SOC_HIGH, DEFAULT_BATTERY_SOC_HIGH)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_BATTERY_SOC["min"], max=RANGE_BATTERY_SOC["max"],
                            step=RANGE_BATTERY_SOC["step"],
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                vol.Optional(CONF_BATTERY_SOC_LOW, default=get_val(CONF_BATTERY_SOC_LOW, DEFAULT_BATTERY_SOC_LOW)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_BATTERY_SOC["min"], max=RANGE_BATTERY_SOC["max"],
                            step=RANGE_BATTERY_SOC["step"],
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                vol.Optional(CONF_PV_PEAK_POWER, default=get_val(CONF_PV_PEAK_POWER, DEFAULT_PV_PEAK_POWER)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1000.0, max=100000.0,
                            step=100.0,
                            unit_of_measurement="W",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # Grundlast für Winter (z.B. Wärmepumpe) - wird von PV abgezogen (Okt-März)
                vol.Optional(CONF_WINTER_BASE_LOAD, default=get_val(CONF_WINTER_BASE_LOAD, DEFAULT_WINTER_BASE_LOAD)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=10000.0,
                            step=100.0,
                            unit_of_measurement="W",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                vol.Optional(CONF_PRICE_LOW_THRESHOLD, default=get_val(CONF_PRICE_LOW_THRESHOLD, DEFAULT_PRICE_LOW_THRESHOLD)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=1.0, step=0.01,
                            unit_of_measurement="€/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                vol.Optional(CONF_PRICE_HIGH_THRESHOLD, default=get_val(CONF_PRICE_HIGH_THRESHOLD, DEFAULT_PRICE_HIGH_THRESHOLD)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=1.0, step=0.01,
                            unit_of_measurement="€/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # === EPEX SPOT INTEGRATION ===
                vol.Optional(CONF_EPEX_PRICE_ENTITY, default=get_val(CONF_EPEX_PRICE_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_EPEX_QUANTILE_ENTITY, default=get_val(CONF_EPEX_QUANTILE_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),

                # === SOLCAST INTEGRATION ===
                vol.Optional(CONF_SOLCAST_FORECAST_ENTITY, default=get_val(CONF_SOLCAST_FORECAST_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            })
        )
