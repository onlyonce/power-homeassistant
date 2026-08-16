"""Sensor entities for Hungarian Power."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfFrequency, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALL_METRICS, DOMAIN, MetricDefinition
from .coordinator import HungarianPowerCoordinator


def _description(metric: MetricDefinition) -> SensorEntityDescription:
    unit = UnitOfPower.MEGA_WATT if metric.unit == "MW" else UnitOfFrequency.HERTZ
    device_class = (
        SensorDeviceClass.POWER
        if metric.device_class == "power"
        else SensorDeviceClass.FREQUENCY
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: HungarianPowerCoordinator = entry.runtime_data
    async_add_entities(
        HungarianPowerSensor(coordinator, description) for description in DESCRIPTIONS
    )


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "hungarian_power")},
            name="Hungarian Power",
            manufacturer="MAVIR / OAH",
            model="Public Hungarian grid data",
        )

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
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose source and freshness information for troubleshooting."""
        if not self.coordinator.data:
            return {}
        metric = self.coordinator.data.metrics.get(self.entity_description.key)
        if not metric:
            return {}
        source_timestamp: datetime | None = metric.source_timestamp
        return {
            "source": metric.source,
            "source_timestamp": source_timestamp.isoformat() if source_timestamp else None,
            "last_coordinator_update": self.coordinator.data.updated_at.isoformat(),
            "last_error": metric.error,
        }
