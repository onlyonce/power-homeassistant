"""Diagnostics for Hungarian Power."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import HungarianPowerCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return non-sensitive integration diagnostics."""
    coordinator: HungarianPowerCoordinator = entry.runtime_data
    data = coordinator.data
    if data is None:
        return {"data": None}
    return {
        "updated_at": data.updated_at.isoformat(),
        "errors": data.errors,
        "metrics": {
            key: {
                "available": value.value is not None,
                "source": value.source,
                "source_timestamp": (
                    value.source_timestamp.isoformat() if value.source_timestamp else None
                ),
                "error": value.error,
            }
            for key, value in data.metrics.items()
        },
    }

