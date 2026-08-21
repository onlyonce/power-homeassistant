"""Pure data models shared by the API clients and Home Assistant adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _datetime_from_storage(value: object) -> datetime | None:
    """Parse a stored ISO timestamp without allowing bad data to break startup."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _datetime_to_storage(value: datetime | None) -> str | None:
    """Serialize a timestamp for Home Assistant storage."""
    return value.isoformat() if value else None


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
    last_updated_at: datetime | None = None
    error: str | None = None

    def to_storage(self) -> dict[str, object]:
        """Return the persisted representation of this metric."""
        return {
            "value": self.value,
            "source_timestamp": _datetime_to_storage(self.source_timestamp),
            "source": self.source,
            "last_updated_at": _datetime_to_storage(self.last_updated_at),
            "error": self.error,
        }

    @classmethod
    def from_storage(cls, data: object) -> MetricValue | None:
        """Restore a metric, ignoring malformed persisted entries."""
        if not isinstance(data, dict) or not isinstance(data.get("source"), str):
            return None
        raw_value = data.get("value")
        value = (
            raw_value
            if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool)
            else None
        )
        error = data.get("error")
        return cls(
            value=float(value) if value is not None else None,
            source_timestamp=_datetime_from_storage(data.get("source_timestamp")),
            source=data["source"],
            last_updated_at=_datetime_from_storage(data.get("last_updated_at")),
            error=error if isinstance(error, str) else None,
        )


@dataclass(frozen=True, slots=True)
class SourceStatus:
    """Persisted request and retry status for one external source."""

    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_rate_limited_at: datetime | None = None
    last_http_status: int | None = None
    next_retry_at: datetime | None = None
    last_error: str | None = None
    response_headers: dict[str, str] = field(default_factory=dict)

    def to_storage(self) -> dict[str, object]:
        """Return the persisted representation of this source status."""
        return {
            "last_attempt_at": _datetime_to_storage(self.last_attempt_at),
            "last_success_at": _datetime_to_storage(self.last_success_at),
            "last_rate_limited_at": _datetime_to_storage(self.last_rate_limited_at),
            "last_http_status": self.last_http_status,
            "next_retry_at": _datetime_to_storage(self.next_retry_at),
            "last_error": self.last_error,
            "response_headers": dict(self.response_headers),
        }

    @classmethod
    def from_storage(cls, data: object) -> SourceStatus | None:
        """Restore a source status, ignoring malformed persisted entries."""
        if not isinstance(data, dict):
            return None
        raw_status = data.get("last_http_status")
        headers = data.get("response_headers")
        return cls(
            last_attempt_at=_datetime_from_storage(data.get("last_attempt_at")),
            last_success_at=_datetime_from_storage(data.get("last_success_at")),
            last_rate_limited_at=_datetime_from_storage(data.get("last_rate_limited_at")),
            last_http_status=(
                raw_status
                if isinstance(raw_status, int) and not isinstance(raw_status, bool)
                else None
            ),
            next_retry_at=_datetime_from_storage(data.get("next_retry_at")),
            last_error=(
                data["last_error"] if isinstance(data.get("last_error"), str) else None
            ),
            response_headers=(
                {str(key): str(value) for key, value in headers.items()}
                if isinstance(headers, dict)
                else {}
            ),
        )


def retain_metric(
    previous: MetricValue | None,
    *,
    value: float | None,
    source_timestamp: datetime | None,
    source: str,
    updated_at: datetime,
    error: str | None = None,
) -> MetricValue:
    """Keep the last real metric when the current extraction has no value."""
    if value is not None:
        return MetricValue(
            value=value,
            source_timestamp=source_timestamp,
            source=source,
            last_updated_at=updated_at,
            error=error,
        )

    if previous is not None and previous.value is not None:
        return MetricValue(
            value=previous.value,
            source_timestamp=previous.source_timestamp,
            source=source,
            last_updated_at=previous.last_updated_at,
            error=error,
        )

    return MetricValue(
        value=None,
        source_timestamp=None,
        source=source,
        last_updated_at=None,
        error=error,
    )


@dataclass(frozen=True, slots=True)
class CoordinatorState:
    """Coordinator payload, including partial-source errors."""

    metrics: dict[str, MetricValue]
    updated_at: datetime
    errors: dict[str, str]
    sources: dict[str, SourceStatus]
    mavir_retry_interval_minutes: int
