"""Home Assistant data coordinator for Hungarian Power."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ALL_METRICS,
    DOMAIN,
    MAVIR_CHART_IDS,
    MAVIR_CHART_PERIOD_MINUTES,
    MAVIR_HISTORY_HOURS,
    MAVIR_METRICS,
    MAVIR_REQUEST_SPACING_SECONDS,
    MAVIR_SOURCE_KEY,
    MAVIR_SOURCE_KEYS,
    MAVIR_STORAGE_VERSION,
    MAX_MAVIR_RETRY_INTERVAL_MINUTES,
    MAX_SCAN_INTERVAL_MINUTES,
    METRICS_BY_KEY,
    MIN_MAVIR_RETRY_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    stale_after_minutes,
)
from .mavir_client import MavirClient, MavirClientError, MavirRateLimited
from .mavir_xlsx import MavirParseError, parse_mavir_xlsx
from .models import (
    CoordinatorState,
    MavirChartData,
    MetricValue,
    SourceStatus,
    aggregate_source_status,
    retain_metric,
)

_LOGGER = logging.getLogger(__name__)


class HungarianPowerCoordinator(DataUpdateCoordinator[CoordinatorState]):
    """Fetch all source data once and fan it out to sensors."""

    def __init__(
        self,
        hass: HomeAssistant,
        mavir_client: MavirClient,
        scan_interval_minutes: int,
        mavir_retry_interval_minutes: int,
        entry_id: str,
    ) -> None:
        self.mavir_client = mavir_client
        self.scan_interval_minutes = min(
            max(scan_interval_minutes, MIN_SCAN_INTERVAL_MINUTES),
            MAX_SCAN_INTERVAL_MINUTES,
        )
        self.mavir_retry_interval_minutes = min(
            max(mavir_retry_interval_minutes, MIN_MAVIR_RETRY_INTERVAL_MINUTES),
            MAX_MAVIR_RETRY_INTERVAL_MINUTES,
        )
        self.stale_after_minutes = stale_after_minutes(self.scan_interval_minutes)
        self._last_known_metrics: dict[str, MetricValue] = {}
        self._source_statuses: dict[str, SourceStatus] = {}
        self._runtime_state_loaded = False
        self._store: Store[dict[str, object]] = Store(
            hass,
            MAVIR_STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}",
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=self.scan_interval_minutes),
        )

    async def _async_update_data(self) -> CoordinatorState:
        """Fetch MAVIR data, preserving usable values when one chart fails."""
        await self._async_load_runtime_state()
        cycle_started_at = datetime.now(UTC)
        errors: dict[str, str] = {}
        charts: dict[int, MavirChartData] = {}
        from_time_ms = int(
            (cycle_started_at - timedelta(hours=MAVIR_HISTORY_HOURS)).timestamp() * 1000
        )
        to_time_ms = int(cycle_started_at.timestamp() * 1000)

        chart_ids = list(MAVIR_CHART_IDS)
        self._record_attempt(MAVIR_SOURCE_KEY, cycle_started_at)
        global_mavir_retry_at = self._mavir_next_retry_at(chart_ids, cycle_started_at)
        if global_mavir_retry_at:
            _LOGGER.debug(
                "All MAVIR requests postponed until %s",
                global_mavir_retry_at.isoformat(),
            )
        mavir_requests_made = 0
        for chart_index, chart_id in enumerate(chart_ids):
            source_key = f"mavir_{chart_id}"
            if global_mavir_retry_at:
                errors[source_key] = (
                    f"MAVIR retry postponed until {global_mavir_retry_at.isoformat()}"
                )
                continue
            source_status = self._source_statuses.get(source_key)
            if (
                source_status
                and source_status.next_retry_at
                and source_status.next_retry_at > cycle_started_at
            ):
                errors[source_key] = (
                    f"MAVIR retry postponed until {source_status.next_retry_at.isoformat()}"
                )
                _LOGGER.debug(
                    "MAVIR chart %s request skipped until %s",
                    chart_id,
                    source_status.next_retry_at.isoformat(),
                )
                continue
            if mavir_requests_made:
                await asyncio.sleep(MAVIR_REQUEST_SPACING_SECONDS)
            mavir_requests_made += 1
            self._record_attempt(source_key, datetime.now(UTC))
            try:
                response = await self.mavir_client.async_fetch_chart(
                    chart_id,
                    from_time_ms=from_time_ms,
                    to_time_ms=to_time_ms,
                    period=MAVIR_CHART_PERIOD_MINUTES,
                )
                self._record_response(
                    source_key,
                    response.status_code,
                    response.response_headers,
                )
                chart = await self.hass.async_add_executor_job(
                    parse_mavir_xlsx, response.body, chart_id
                )
                charts[chart_id] = chart
                self._record_success(source_key, datetime.now(UTC))
            except (MavirClientError, MavirParseError) as err:
                self._record_failure(source_key, datetime.now(UTC), err)
                errors[source_key] = str(err)
                status = self._source_statuses[source_key]
                _LOGGER.warning(
                    "MAVIR chart %s update failed: %s; HTTP status=%s; "
                    "next retry=%s; response headers=%s",
                    chart_id,
                    err,
                    status.last_http_status,
                    status.next_retry_at.isoformat() if status.next_retry_at else "not scheduled",
                    status.response_headers or "none",
                )
                if isinstance(err, MavirRateLimited):
                    for skipped_chart_id in chart_ids[chart_index + 1 :]:
                        errors.setdefault(
                            f"mavir_{skipped_chart_id}",
                            f"MAVIR request skipped after chart {chart_id} was rate-limited",
                        )
                    self._apply_global_mavir_cooldown(chart_ids, status.next_retry_at)
                    break

        cycle_finished_at = datetime.now(UTC)
        self._record_mavir_cycle_result(
            chart_ids=chart_ids,
            successful_chart_ids=set(charts),
            errors=errors,
            finished_at=cycle_finished_at,
        )

        metrics: dict[str, MetricValue] = {}
        for definition in MAVIR_METRICS:
            chart = charts.get(definition.chart_id or -1)
            match = chart.value_for(definition.matchers) if chart else None
            error = errors.get(f"mavir_{definition.chart_id}")
            if chart is not None and match is None:
                error = (
                    f"MAVIR chart {definition.chart_id} did not provide a numeric value "
                    f"for {definition.name} in the requested window"
                )
            chart_status = self._source_statuses.get(f"mavir_{definition.chart_id}")
            metric_updated_at = (
                chart_status.last_success_at
                if chart is not None and chart_status and chart_status.last_success_at
                else cycle_finished_at
            )
            metrics[definition.key] = self._retain_metric(
                definition.key,
                value=match[0] if match else None,
                source_timestamp=match[1] if match else None,
                source=definition.source,
                now=metric_updated_at,
                error=error,
            )

        self._schedule_runtime_state_save()
        if not charts and not self._last_known_metrics:
            raise UpdateFailed("No MAVIR chart could be updated")

        # Ensure every declared metric has a state even if a future definition is added.
        for definition in ALL_METRICS:
            metrics.setdefault(
                definition.key,
                MetricValue(
                    value=None,
                    source_timestamp=None,
                    source=definition.source,
                    error=errors.get(definition.source),
                ),
            )
        return CoordinatorState(
            metrics=metrics,
            updated_at=cycle_finished_at,
            errors=errors,
            sources=dict(self._source_statuses),
            scan_interval_minutes=self.scan_interval_minutes,
            mavir_retry_interval_minutes=self.mavir_retry_interval_minutes,
            stale_after_minutes=self.stale_after_minutes,
        )

    def _retain_metric(
        self,
        key: str,
        *,
        value: float | None,
        source_timestamp: datetime | None,
        source: str,
        now: datetime,
        error: str | None = None,
    ) -> MetricValue:
        """Update one metric or return its last known real value."""
        metric = retain_metric(
            self._last_known_metrics.get(key),
            value=value,
            source_timestamp=source_timestamp,
            source=source,
            updated_at=now,
            error=error,
        )
        if metric.value is not None:
            self._last_known_metrics[key] = metric
        return metric

    async def _async_load_runtime_state(self) -> None:
        """Load persisted values and source status once per coordinator lifetime."""
        if self._runtime_state_loaded:
            return
        try:
            stored = await self._store.async_load()
        except HomeAssistantError as err:
            _LOGGER.error("Could not load Hungarian Power runtime state: %s", err)
            stored = None

        if isinstance(stored, dict):
            stored_metrics = stored.get("metrics")
            if isinstance(stored_metrics, dict):
                for key, value in stored_metrics.items():
                    metric_key = str(key)
                    if metric_key not in METRICS_BY_KEY:
                        continue
                    metric = MetricValue.from_storage(value)
                    if metric is not None and metric.value is not None:
                        self._last_known_metrics[metric_key] = metric

            stored_sources = stored.get("sources")
            if isinstance(stored_sources, dict):
                for key, value in stored_sources.items():
                    source_key = str(key)
                    if source_key not in MAVIR_SOURCE_KEYS:
                        continue
                    status = SourceStatus.from_storage(value)
                    if status is not None:
                        self._source_statuses[source_key] = status

        self._runtime_state_loaded = True

    def _serialize_runtime_state(self) -> dict[str, object]:
        """Return the persisted metric and source state."""
        return {
            "metrics": {
                key: value.to_storage()
                for key, value in self._last_known_metrics.items()
                if key in METRICS_BY_KEY
            },
            "sources": {
                key: value.to_storage()
                for key, value in self._source_statuses.items()
                if key in MAVIR_SOURCE_KEYS
            },
        }

    def _schedule_runtime_state_save(self) -> None:
        """Coalesce runtime-state writes while guaranteeing final shutdown persistence."""
        self._store.async_delay_save(self._serialize_runtime_state, delay=2)

    def _record_attempt(self, source_key: str, now: datetime) -> None:
        """Record that a source request started."""
        current = self._source_statuses.get(source_key, SourceStatus())
        self._source_statuses[source_key] = replace(current, last_attempt_at=now)

    def _record_response(
        self,
        source_key: str,
        status_code: int,
        response_headers: dict[str, str],
    ) -> None:
        """Record safe metadata from an HTTP response."""
        current = self._source_statuses.get(source_key, SourceStatus())
        self._source_statuses[source_key] = replace(
            current,
            last_http_status=status_code,
            response_headers=dict(response_headers),
        )

    def _record_success(self, source_key: str, now: datetime) -> None:
        """Record a successful source extraction and clear its cooldown."""
        current = self._source_statuses.get(source_key, SourceStatus())
        self._source_statuses[source_key] = replace(
            current,
            last_success_at=now,
            next_retry_at=None,
            last_error=None,
        )

    def _record_failure(
        self,
        source_key: str,
        now: datetime,
        error: Exception,
    ) -> None:
        """Record source failure and schedule a persisted retry after rate limiting."""
        current = self._source_statuses.get(source_key, SourceStatus())
        status_code = getattr(error, "status_code", None)
        response_headers = getattr(error, "response_headers", None)
        updated = replace(
            current,
            last_http_status=(
                status_code if isinstance(status_code, int) else current.last_http_status
            ),
            response_headers=(
                dict(response_headers)
                if isinstance(response_headers, dict)
                else current.response_headers
            ),
            last_error=str(error),
            next_retry_at=None,
        )
        if isinstance(error, MavirRateLimited):
            retry_after_seconds = getattr(error, "retry_after_seconds", None)
            retry_seconds = self.mavir_retry_interval_minutes * 60
            if isinstance(retry_after_seconds, int):
                retry_seconds = max(retry_seconds, retry_after_seconds)
            retry_seconds = min(
                retry_seconds,
                MAX_MAVIR_RETRY_INTERVAL_MINUTES * 60,
            )
            updated = replace(
                updated,
                last_rate_limited_at=now,
                next_retry_at=now + timedelta(seconds=retry_seconds),
            )
        self._source_statuses[source_key] = updated

    def _record_mavir_cycle_result(
        self,
        *,
        chart_ids: list[int],
        successful_chart_ids: set[int],
        errors: dict[str, str],
        finished_at: datetime,
    ) -> None:
        """Record when the complete set of MAVIR charts last refreshed."""
        current = self._source_statuses.get(MAVIR_SOURCE_KEY, SourceStatus())
        failed_statuses = [
            self._source_statuses.get(f"mavir_{chart_id}", SourceStatus())
            for chart_id in chart_ids
            if chart_id not in successful_chart_ids
        ]
        self._source_statuses[MAVIR_SOURCE_KEY] = aggregate_source_status(
            current,
            complete=successful_chart_ids == set(chart_ids),
            finished_at=finished_at,
            failed_statuses=failed_statuses,
            error_messages=list(errors.values()),
        )

    def _mavir_next_retry_at(
        self,
        chart_ids: list[int],
        now: datetime,
    ) -> datetime | None:
        """Return the shared MAVIR cooldown when any chart is still blocked."""
        retry_times = [
            status.next_retry_at
            for chart_id in chart_ids
            if (status := self._source_statuses.get(f"mavir_{chart_id}"))
            and status.next_retry_at
            and status.next_retry_at > now
        ]
        return max(retry_times) if retry_times else None

    def _apply_global_mavir_cooldown(
        self,
        chart_ids: list[int],
        retry_at: datetime | None,
    ) -> None:
        """Apply a shared cooldown because the limiter is keyed by public IP."""
        if retry_at is None:
            return
        for chart_id in chart_ids:
            source_key = f"mavir_{chart_id}"
            current = self._source_statuses.get(source_key, SourceStatus())
            if current.next_retry_at is None or current.next_retry_at < retry_at:
                self._source_statuses[source_key] = replace(
                    current,
                    next_retry_at=retry_at,
                )
