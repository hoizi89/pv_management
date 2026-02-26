from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Buttons — alle Reset-Aktionen sind jetzt in den Options/Settings."""
    async_add_entities([])
