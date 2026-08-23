"""Hungarian Power Home Assistant integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import (
    CONF_MAVIR_RETRY_INTERVAL_MINUTES,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_MAVIR_RETRY_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    LEGACY_OAH_METRIC_KEYS,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hungarian Power from a config entry."""
    from homeassistant.const import Platform
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .coordinator import HungarianPowerCoordinator
    from .mavir_client import MavirClient

    session = async_get_clientsession(hass)
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL_MINUTES,
        entry.data.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES),
    )
    mavir_retry_interval = entry.options.get(
        CONF_MAVIR_RETRY_INTERVAL_MINUTES,
        entry.data.get(
            CONF_MAVIR_RETRY_INTERVAL_MINUTES,
            DEFAULT_MAVIR_RETRY_INTERVAL_MINUTES,
        ),
    )
    coordinator = HungarianPowerCoordinator(
        hass,
        MavirClient(session),
        scan_interval,
        mavir_retry_interval,
        entry.entry_id,
    )
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()

    entity_registry = er.async_get(hass)
    for metric_key in LEGACY_OAH_METRIC_KEYS:
        unique_id = f"{DOMAIN}_{metric_key}"
        if entity_id := entity_registry.async_get_entity_id(Platform.SENSOR, DOMAIN, unique_id):
            entity_registry.async_remove(entity_id)

    await hass.config_entries.async_forward_entry_setups(entry, (Platform.SENSOR,))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from homeassistant.const import Platform

    return await hass.config_entries.async_unload_platforms(entry, (Platform.SENSOR,))
