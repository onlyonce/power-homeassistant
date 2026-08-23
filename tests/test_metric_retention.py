from datetime import UTC, datetime, timedelta

from custom_components.hungarian_power.const import stale_after_minutes
from custom_components.hungarian_power.mavir_client import (
    MavirRateLimited,
    _safe_response_headers,
)
from custom_components.hungarian_power.models import (
    MetricValue,
    SourceStatus,
    aggregate_source_status,
    metric_is_stale,
    metric_source_age_minutes,
    retain_metric,
)


def test_retain_metric_keeps_last_value_and_success_timestamp_on_failed_cycle() -> None:
    last_updated = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    previous = MetricValue(
        value=481.0,
        source_timestamp=datetime(2026, 8, 21, 7, 59, tzinfo=UTC),
        source="MAVIR",
        last_updated_at=last_updated,
    )

    retained = retain_metric(
        previous,
        value=None,
        source_timestamp=None,
        source="MAVIR",
        updated_at=datetime(2026, 8, 21, 8, 15, tzinfo=UTC),
        error="MAVIR chart update failed",
    )

    assert retained.value == 481.0
    assert retained.source_timestamp == previous.source_timestamp
    assert retained.last_updated_at == last_updated
    assert retained.error == "MAVIR chart update failed"


def test_retain_metric_updates_value_and_success_timestamp_when_value_is_real() -> None:
    previous = MetricValue(
        value=481.0,
        source_timestamp=datetime(2026, 8, 21, 7, 59, tzinfo=UTC),
        source="MAVIR",
        last_updated_at=datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
    )
    updated_at = datetime(2026, 8, 21, 8, 15, tzinfo=UTC)

    updated = retain_metric(
        previous,
        value=482.0,
        source_timestamp=datetime(2026, 8, 21, 8, 14, tzinfo=UTC),
        source="MAVIR",
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
        source="MAVIR",
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


def test_metric_becomes_stale_when_source_timestamp_exceeds_threshold() -> None:
    now = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
    metric = MetricValue(
        value=4800.0,
        source_timestamp=now - timedelta(minutes=31),
        source="MAVIR",
        last_updated_at=now,
    )

    assert metric_source_age_minutes(metric, now) == 31
    assert metric_is_stale(metric, now=now, stale_after_minutes=30)


def test_stale_threshold_tracks_polling_interval_with_resolution_floor() -> None:
    assert stale_after_minutes(10) == 30
    assert stale_after_minutes(15) == 30
    assert stale_after_minutes(31) == 62


def test_fresh_metric_without_error_is_not_stale() -> None:
    now = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
    metric = MetricValue(
        value=4800.0,
        source_timestamp=now - timedelta(minutes=29),
        source="MAVIR",
        last_updated_at=now,
    )

    assert not metric_is_stale(metric, now=now, stale_after_minutes=30)


def test_retained_metric_with_current_error_is_stale_even_when_timestamp_is_recent() -> None:
    now = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
    metric = MetricValue(
        value=4800.0,
        source_timestamp=now - timedelta(minutes=5),
        source="MAVIR",
        last_updated_at=now - timedelta(minutes=5),
        error="MAVIR chart update failed",
    )

    assert metric_is_stale(metric, now=now, stale_after_minutes=30)


def test_complete_aggregate_source_cycle_publishes_finished_timestamp() -> None:
    previous_success = datetime(2026, 8, 23, 9, 30, tzinfo=UTC)
    finished_at = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
    current = SourceStatus(
        last_attempt_at=datetime(2026, 8, 23, 9, 59, tzinfo=UTC),
        last_success_at=previous_success,
        last_error="old failure",
    )

    updated = aggregate_source_status(
        current,
        complete=True,
        finished_at=finished_at,
        failed_statuses=[],
        error_messages=[],
    )

    assert updated.last_success_at == finished_at
    assert updated.last_error is None
    assert updated.last_http_status == 200


def test_incomplete_aggregate_source_cycle_preserves_previous_success() -> None:
    previous_success = datetime(2026, 8, 23, 9, 30, tzinfo=UTC)
    retry_at = datetime(2026, 8, 23, 11, 0, tzinfo=UTC)
    current = SourceStatus(last_success_at=previous_success)
    failed = SourceStatus(
        last_http_status=429,
        next_retry_at=retry_at,
        last_error="rate limited",
        response_headers={"retry-after": "3600"},
    )

    updated = aggregate_source_status(
        current,
        complete=False,
        finished_at=datetime(2026, 8, 23, 10, 0, tzinfo=UTC),
        failed_statuses=[failed],
        error_messages=["rate limited"],
    )

    assert updated.last_success_at == previous_success
    assert updated.last_http_status == 429
    assert updated.next_retry_at == retry_at
    assert updated.last_error == "rate limited"
