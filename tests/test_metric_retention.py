from datetime import UTC, datetime

from custom_components.hungarian_power.mavir_client import (
    MavirRateLimited,
    _safe_response_headers,
)
from custom_components.hungarian_power.models import (
    MetricValue,
    SourceStatus,
    retain_metric,
)


def test_retain_metric_keeps_last_value_and_success_timestamp_on_failed_cycle() -> None:
    last_updated = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    previous = MetricValue(
        value=481.0,
        source_timestamp=datetime(2026, 8, 21, 7, 59, tzinfo=UTC),
        source="OAH",
        last_updated_at=last_updated,
    )

    retained = retain_metric(
        previous,
        value=None,
        source_timestamp=None,
        source="OAH",
        updated_at=datetime(2026, 8, 21, 8, 15, tzinfo=UTC),
        error="OAH measurement timestamp was not found",
    )

    assert retained.value == 481.0
    assert retained.source_timestamp == previous.source_timestamp
    assert retained.last_updated_at == last_updated
    assert retained.error == "OAH measurement timestamp was not found"


def test_retain_metric_updates_value_and_success_timestamp_when_value_is_real() -> None:
    previous = MetricValue(
        value=481.0,
        source_timestamp=datetime(2026, 8, 21, 7, 59, tzinfo=UTC),
        source="OAH",
        last_updated_at=datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
    )
    updated_at = datetime(2026, 8, 21, 8, 15, tzinfo=UTC)

    updated = retain_metric(
        previous,
        value=482.0,
        source_timestamp=datetime(2026, 8, 21, 8, 14, tzinfo=UTC),
        source="OAH",
        updated_at=updated_at,
    )

    assert updated.value == 482.0
    assert updated.source_timestamp == datetime(2026, 8, 21, 8, 14, tzinfo=UTC)
    assert updated.last_updated_at == updated_at
    assert updated.error is None


def test_metric_value_storage_round_trip_preserves_last_real_value() -> None:
    metric = MetricValue(
        value=481.0,
        source_timestamp=datetime(2026, 8, 21, 7, 59, tzinfo=UTC),
        source="OAH",
        last_updated_at=datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
        error="temporary source failure",
    )

    restored = MetricValue.from_storage(metric.to_storage())

    assert restored == metric


def test_source_status_storage_round_trip_preserves_retry_observability() -> None:
    status = SourceStatus(
        last_attempt_at=datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
        last_success_at=datetime(2026, 8, 21, 7, 45, tzinfo=UTC),
        last_rate_limited_at=datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
        last_http_status=429,
        next_retry_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
        last_error="MAVIR rate limit",
        response_headers={"retry-after": "60"},
    )

    restored = SourceStatus.from_storage(status.to_storage())

    assert restored == status


def test_rate_limited_error_parses_retry_after_and_keeps_safe_headers() -> None:
    error = MavirRateLimited(
        "MAVIR rate limit",
        status_code=429,
        response_headers={"retry-after": "120", "ratelimit-remaining": "0"},
    )

    assert error.status_code == 429
    assert error.retry_after_seconds == 120
    assert error.response_headers == {
        "retry-after": "120",
        "ratelimit-remaining": "0",
    }


def test_safe_response_headers_exclude_unrelated_headers() -> None:
    assert _safe_response_headers(
        {
            "Retry-After": "120",
            "X-RateLimit-Remaining": "0",
            "Server": "Apache",
            "Set-Cookie": "private=value",
        }
    ) == {
        "retry-after": "120",
        "x-ratelimit-remaining": "0",
    }
