"""Diagnostics for Hungarian Power."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import HungarianPowerCoordinator
from .models import metric_is_stale, metric_source_age_minutes


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Return non-sensitive integration diagnostics."""
    coordinator: HungarianPowerCoordinator = entry.runtime_data
    data = coordinator.data
    if data is None:
        return {"data": None}
    now = datetime.now(UTC)
    return {
        "updated_at": data.updated_at.isoformat(),
        "errors": data.errors,
        "scan_interval_minutes": data.scan_interval_minutes,
        "mavir_retry_interval_minutes": data.mavir_retry_interval_minutes,
        "stale_after_minutes": data.stale_after_minutes,
        "sources": {
            key: {
                "last_attempt_at": (
                    status.last_attempt_at.isoformat() if status.last_attempt_at else None
                ),
                "last_success_at": (
                    status.last_success_at.isoformat() if status.last_success_at else None
                ),
                "last_rate_limited_at": (
                    status.last_rate_limited_at.isoformat() if status.last_rate_limited_at else None
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
                "source_age_minutes": (
                    round(source_age, 1)
                    if (source_age := metric_source_age_minutes(value, now)) is not None
                    else None
                ),
                "is_stale": metric_is_stale(
                    value,
                    now=now,
                    stale_after_minutes=data.stale_after_minutes,
                ),
                "error": value.error,
            }
            for key, value in data.metrics.items()
        },
    }
