"""Pure data models shared by the API clients and Home Assistant adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MavirChartData:
    """Latest numeric values and timestamps extracted from one MAVIR chart."""

    chart_id: int
    timestamp: datetime | None
    columns: dict[str, float]
    column_timestamps: dict[str, datetime]
    point_count: int

    def value_for(self, matchers: tuple[str, ...]) -> tuple[float, datetime | None] | None:
        """Return the first matching latest value from the chart."""
        normalized_matchers = tuple(matcher.casefold() for matcher in matchers)
        for column, value in self.columns.items():
            normalized_column = " ".join(column.split()).casefold()
            if any(matcher in normalized_column for matcher in normalized_matchers):
                return value, self.column_timestamps.get(column, self.timestamp)
        return None


@dataclass(frozen=True, slots=True)
class PaksData:
    """Current Paks block output parsed from the OAH page."""

    timestamp: datetime
    units_mw: tuple[float | None, float | None, float | None, float | None]


@dataclass(frozen=True, slots=True)
class MetricValue:
    """A value exposed by a Home Assistant entity."""

    value: float | None
    source_timestamp: datetime | None
    source: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CoordinatorState:
    """Coordinator payload, including partial-source errors."""

    metrics: dict[str, MetricValue]
    updated_at: datetime
    errors: dict[str, str]

