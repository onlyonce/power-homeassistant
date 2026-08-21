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
        "mavir_retry_interval_minutes": data.mavir_retry_interval_minutes,
        "sources": {
            key: {
                "last_attempt_at": (
                    status.last_attempt_at.isoformat()
                    if status.last_attempt_at
                    else None
                ),
                "last_success_at": (
                    status.last_success_at.isoformat()
                    if status.last_success_at
                    else None
                ),
                "last_rate_limited_at": (
                    status.last_rate_limited_at.isoformat()
                    if status.last_rate_limited_at
                    else None
                ),
                "last_http_status": status.last_http_status,
                "next_retry_at": (
                    status.next_retry_at.isoformat() if status.next_retry_at else None
                ),
                "last_error": status.last_error,
                "response_headers": dict(status.response_headers),
            }
            for key, status in data.sources.items()
        },
        "metrics": {
            key: {
                "available": value.value is not None,
                "source": value.source,
                "source_timestamp": (
                    value.source_timestamp.isoformat() if value.source_timestamp else None
                ),
                "last_updated": (
                    value.last_updated_at.isoformat() if value.last_updated_at else None
                ),
                "is_stale": value.value is not None and value.error is not None,
                "error": value.error,
            }
            for key, value in data.metrics.items()
        },
    }
