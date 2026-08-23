"""Sensor entities for Hungarian Power."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfFrequency, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ALL_METRICS,
    DOMAIN,
    MAVIR_CHART_IDS,
    MAVIR_METRICS,
    MAVIR_SOURCE_KEY,
    METRICS_BY_KEY,
    MetricDefinition,
)
from .coordinator import HungarianPowerCoordinator
from .models import metric_is_stale, metric_source_age_minutes


def _description(metric: MetricDefinition) -> SensorEntityDescription:
    unit = UnitOfPower.MEGA_WATT if metric.unit == "MW" else UnitOfFrequency.HERTZ
    device_class = (
        SensorDeviceClass.POWER if metric.device_class == "power" else SensorDeviceClass.FREQUENCY
    )
    return SensorEntityDescription(
        key=metric.key,
        name=metric.name,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=SensorStateClass.MEASUREMENT,
        icon=metric.icon,
    )


DESCRIPTIONS = tuple(_description(metric) for metric in ALL_METRICS)
MAVIR_LAST_SUCCESS_DESCRIPTION = SensorEntityDescription(
    key="mavir_last_success",
    name="MAVIR last successful update",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:update",
)


def _device_info() -> DeviceInfo:
    """Return shared device metadata for all Hungarian Power entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, "hungarian_power")},
        name="Hungarian Power",
        manufacturer="MAVIR",
        model="Public Hungarian grid data",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: HungarianPowerCoordinator = entry.runtime_data
    entities = [
        *(HungarianPowerSensor(coordinator, description) for description in DESCRIPTIONS),
        HungarianPowerMavirLastSuccessSensor(coordinator),
    ]
    async_add_entities(entities)


class HungarianPowerSensor(CoordinatorEntity[HungarianPowerCoordinator], SensorEntity):
    """A single value extracted from the coordinator snapshot."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HungarianPowerCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self._attr_device_info = _device_info()

    @property
    def native_value(self) -> float | None:
        """Return the latest metric value."""
        if not self.coordinator.data:
            return None
        metric = self.coordinator.data.metrics.get(self.entity_description.key)
        return metric.value if metric else None

    @property
    def available(self) -> bool:
        """Keep individual entities available when another chart fails."""
        if not super().available or not self.coordinator.data:
            return False
        metric = self.coordinator.data.metrics.get(self.entity_description.key)
        return metric is not None and metric.value is not None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose source and freshness information for troubleshooting."""
        if not self.coordinator.data:
            return {}
        metric = self.coordinator.data.metrics.get(self.entity_description.key)
        if not metric:
            return {}
        definition = METRICS_BY_KEY[self.entity_description.key]
        source_status_key = f"mavir_{definition.chart_id}"
        source_status = self.coordinator.data.sources.get(source_status_key)
        source_timestamp: datetime | None = metric.source_timestamp
        now = datetime.now(UTC)
        source_age = metric_source_age_minutes(metric, now)
        return {
            "source": metric.source,
            "source_timestamp": source_timestamp.isoformat() if source_timestamp else None,
            "source_age_minutes": round(source_age, 1) if source_age is not None else None,
            "last_updated": (
                metric.last_updated_at.isoformat() if metric.last_updated_at else None
            ),
            "is_stale": metric_is_stale(
                metric,
                now=now,
                stale_after_minutes=self.coordinator.data.stale_after_minutes,
            ),
            "stale_after_minutes": self.coordinator.data.stale_after_minutes,
            "last_coordinator_update": self.coordinator.data.updated_at.isoformat(),
            "last_error": metric.error,
            "source_status_key": source_status_key,
            "last_attempt_at": (
                source_status.last_attempt_at.isoformat()
                if source_status and source_status.last_attempt_at
                else None
            ),
            "last_success_at": (
                source_status.last_success_at.isoformat()
                if source_status and source_status.last_success_at
                else None
            ),
            "last_rate_limited_at": (
                source_status.last_rate_limited_at.isoformat()
                if source_status and source_status.last_rate_limited_at
                else None
            ),
            "last_http_status": (source_status.last_http_status if source_status else None),
            "next_retry_at": (
                source_status.next_retry_at.isoformat()
                if source_status and source_status.next_retry_at
                else None
            ),
            "response_headers": (dict(source_status.response_headers) if source_status else {}),
            "scan_interval_minutes": self.coordinator.data.scan_interval_minutes,
            "mavir_retry_interval_minutes": (self.coordinator.data.mavir_retry_interval_minutes),
        }


class HungarianPowerMavirLastSuccessSensor(
    CoordinatorEntity[HungarianPowerCoordinator], SensorEntity
):
    """Expose when every required MAVIR chart last refreshed successfully."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HungarianPowerCoordinator) -> None:
        super().__init__(coordinator)
        self.entity_description = MAVIR_LAST_SUCCESS_DESCRIPTION
        self._attr_unique_id = f"{DOMAIN}_{MAVIR_LAST_SUCCESS_DESCRIPTION.key}"
        self._attr_device_info = _device_info()

    @property
    def native_value(self) -> datetime | None:
        """Return the last complete MAVIR refresh timestamp."""
        if not self.coordinator.data:
            return None
        source_status = self.coordinator.data.sources.get(MAVIR_SOURCE_KEY)
        return source_status.last_success_at if source_status else None

    @property
    def available(self) -> bool:
        """Keep the last known successful timestamp visible after later failures."""
        return self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose per-chart success and source-data freshness."""
        data = self.coordinator.data
        if not data:
            return {}
        now = datetime.now(UTC)
        source_status = data.sources.get(MAVIR_SOURCE_KEY)
        timestamps = [
            metric.source_timestamp
            for metric in data.metrics.values()
            if metric.source_timestamp is not None
        ]
        stale_metrics = [
            definition.key
            for definition in MAVIR_METRICS
            if (metric := data.metrics.get(definition.key))
            and metric_is_stale(
                metric,
                now=now,
                stale_after_minutes=data.stale_after_minutes,
            )
        ]
        unavailable_metrics = [
            definition.key
            for definition in MAVIR_METRICS
            if not (metric := data.metrics.get(definition.key)) or metric.value is None
        ]
        return {
            "latest_source_timestamp": max(timestamps).isoformat() if timestamps else None,
            "oldest_source_timestamp": min(timestamps).isoformat() if timestamps else None,
            "stale_metrics": stale_metrics,
            "unavailable_metrics": unavailable_metrics,
            "last_attempt_at": (
                source_status.last_attempt_at.isoformat()
                if source_status and source_status.last_attempt_at
                else None
            ),
            "last_error": source_status.last_error if source_status else None,
            "last_http_status": (source_status.last_http_status if source_status else None),
            "next_retry_at": (
                source_status.next_retry_at.isoformat()
                if source_status and source_status.next_retry_at
                else None
            ),
            "chart_last_success_at": {
                str(chart_id): (
                    status.last_success_at.isoformat()
                    if (status := data.sources.get(f"mavir_{chart_id}")) and status.last_success_at
                    else None
                )
                for chart_id in MAVIR_CHART_IDS
            },
            "scan_interval_minutes": data.scan_interval_minutes,
            "stale_after_minutes": data.stale_after_minutes,
            "mavir_retry_interval_minutes": data.mavir_retry_interval_minutes,
        }
