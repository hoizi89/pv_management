from __future__ import annotations

from datetime import date
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
    CONF_INSTALLATION_COST, CONF_SAVINGS_OFFSET,
    CONF_ENERGY_OFFSET_SELF, CONF_ENERGY_OFFSET_EXPORT,
    CONF_INSTALLATION_DATE,
    CONF_BATTERY_SOC_HIGH, CONF_BATTERY_SOC_LOW,
    CONF_PRICE_HIGH_THRESHOLD, CONF_PRICE_LOW_THRESHOLD, CONF_PV_POWER_HIGH,
    DEFAULT_NAME, DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET,
    DEFAULT_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_EXPORT,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    DEFAULT_BATTERY_SOC_HIGH, DEFAULT_BATTERY_SOC_LOW,
    DEFAULT_PRICE_HIGH_THRESHOLD, DEFAULT_PRICE_LOW_THRESHOLD, DEFAULT_PV_POWER_HIGH,
    RANGE_COST, RANGE_OFFSET, RANGE_ENERGY_OFFSET,
    RANGE_BATTERY_SOC, RANGE_PV_POWER,
    PRICE_UNIT_EUR, PRICE_UNIT_CENT,
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
                vol.Optional(CONF_SAVINGS_OFFSET, default=DEFAULT_SAVINGS_OFFSET):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_OFFSET["min"], max=RANGE_OFFSET["max"], step=RANGE_OFFSET["step"],
                            unit_of_measurement="€",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_ENERGY_OFFSET_SELF, default=DEFAULT_ENERGY_OFFSET_SELF):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_ENERGY_OFFSET["min"], max=RANGE_ENERGY_OFFSET["max"],
                            step=RANGE_ENERGY_OFFSET["step"],
                            unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_ENERGY_OFFSET_EXPORT, default=DEFAULT_ENERGY_OFFSET_EXPORT):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_ENERGY_OFFSET["min"], max=RANGE_ENERGY_OFFSET["max"],
                            step=RANGE_ENERGY_OFFSET["step"],
                            unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
            })
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return PVManagementOptionsFlow(config_entry)


class PVManagementOptionsFlow(config_entries.OptionsFlow):
    """Options Flow für nachträgliche Anpassungen - vereinfacht."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

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
                # === AMORTISATION (wichtigste Felder zuerst) ===
                vol.Required(CONF_INSTALLATION_COST, default=get_val(CONF_INSTALLATION_COST, DEFAULT_INSTALLATION_COST)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_COST["min"], max=RANGE_COST["max"], step=RANGE_COST["step"],
                            unit_of_measurement="€",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                vol.Optional(CONF_SAVINGS_OFFSET, default=get_val(CONF_SAVINGS_OFFSET, DEFAULT_SAVINGS_OFFSET)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_OFFSET["min"], max=RANGE_OFFSET["max"], step=RANGE_OFFSET["step"],
                            unit_of_measurement="€",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                vol.Optional(CONF_ENERGY_OFFSET_SELF, default=get_val(CONF_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_SELF)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_ENERGY_OFFSET["min"], max=RANGE_ENERGY_OFFSET["max"],
                            step=RANGE_ENERGY_OFFSET["step"],
                            unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                vol.Optional(CONF_ENERGY_OFFSET_EXPORT, default=get_val(CONF_ENERGY_OFFSET_EXPORT, DEFAULT_ENERGY_OFFSET_EXPORT)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_ENERGY_OFFSET["min"], max=RANGE_ENERGY_OFFSET["max"],
                            step=RANGE_ENERGY_OFFSET["step"],
                            unit_of_measurement="kWh",
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

                vol.Optional(CONF_PV_POWER_HIGH, default=get_val(CONF_PV_POWER_HIGH, DEFAULT_PV_POWER_HIGH)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_PV_POWER["min"], max=RANGE_PV_POWER["max"],
                            step=RANGE_PV_POWER["step"],
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
            })
        )
