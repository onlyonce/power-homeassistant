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
    MAVIR_CHART_PERIOD_MINUTES,
    MAVIR_HISTORY_HOURS,
    MAVIR_METRICS,
    MAVIR_REQUEST_SPACING_SECONDS,
    MAVIR_STORAGE_VERSION,
    MAX_MAVIR_RETRY_INTERVAL_MINUTES,
    MIN_MAVIR_RETRY_INTERVAL_MINUTES,
    OAH_METRICS,
)
from .mavir_client import MavirClient, MavirClientError, MavirRateLimited
from .mavir_xlsx import MavirParseError, parse_mavir_xlsx
from .models import (
    CoordinatorState,
    MavirChartData,
    MetricValue,
    SourceStatus,
    retain_metric,
)
from .oah_client import OahClient, OahClientError
from .oah_html import OahParseError, parse_oah_html

_LOGGER = logging.getLogger(__name__)


class HungarianPowerCoordinator(DataUpdateCoordinator[CoordinatorState]):
    """Fetch all source data once and fan it out to sensors."""

    def __init__(
        self,
        hass: HomeAssistant,
        mavir_client: MavirClient,
        oah_client: OahClient,
        scan_interval_minutes: int,
        mavir_retry_interval_minutes: int,
        entry_id: str,
    ) -> None:
        self.mavir_client = mavir_client
        self.oah_client = oah_client
        self.mavir_retry_interval_minutes = min(
            max(mavir_retry_interval_minutes, MIN_MAVIR_RETRY_INTERVAL_MINUTES),
            MAX_MAVIR_RETRY_INTERVAL_MINUTES,
        )
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
            update_interval=timedelta(minutes=scan_interval_minutes),
        )

    async def _async_update_data(self) -> CoordinatorState:
        """Fetch source data, preserving usable values when one source fails."""
        await self._async_load_runtime_state()
        now = datetime.now(UTC)
        errors: dict[str, str] = {}
        successful_sources = 0
        charts: dict[int, MavirChartData] = {}
        from_time_ms = int((now - timedelta(hours=MAVIR_HISTORY_HOURS)).timestamp() * 1000)
        to_time_ms = int(now.timestamp() * 1000)

        chart_ids = sorted({metric.chart_id for metric in MAVIR_METRICS if metric.chart_id})
        global_mavir_retry_at = self._mavir_next_retry_at(chart_ids, now)
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
            if source_status and source_status.next_retry_at and source_status.next_retry_at > now:
                errors[source_key] = (
                    f"MAVIR retry postponed until "
                    f"{source_status.next_retry_at.isoformat()}"
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
            self._record_attempt(source_key, now)
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
                successful_sources += 1
                self._record_success(source_key, now)
            except (MavirClientError, MavirParseError) as err:
                self._record_failure(source_key, now, err)
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

        metrics: dict[str, MetricValue] = {}
        for definition in MAVIR_METRICS:
            chart = charts.get(definition.chart_id or -1)
            match = chart.value_for(definition.matchers) if chart else None
            error = errors.get(f"mavir_{definition.chart_id}")
            if chart is not None and match is None:
                error = f"MAVIR chart {definition.chart_id} did not provide {definition.name}"
            metrics[definition.key] = self._retain_metric(
                definition.key,
                value=match[0] if match else None,
                source_timestamp=match[1] if match else None,
                source=definition.source,
                now=now,
                error=error,
            )

        oah_source_key = "oah"
        self._record_attempt(oah_source_key, now)
        try:
            oah_response = await self.oah_client.async_fetch()
            self._record_response(
                oah_source_key,
                oah_response.status_code,
                oah_response.response_headers,
            )
            paks = await self.hass.async_add_executor_job(parse_oah_html, oah_response.body)
            successful_sources += 1
            self._record_success(oah_source_key, now)
            for index, definition in enumerate(OAH_METRICS):
                value = paks.units_mw[index]
                metrics[definition.key] = self._retain_metric(
                    definition.key,
                    value=value,
                    source_timestamp=paks.timestamp,
                    source=definition.source,
                    now=now,
                    error=(
                        None
                        if value is not None
                        else f"OAH source did not provide {definition.name}"
                    ),
                )
        except (OahClientError, OahParseError) as err:
            errors["oah"] = str(err)
            self._record_failure(oah_source_key, now, err)
            _LOGGER.warning("OAH update failed: %s", err)
            for definition in OAH_METRICS:
                metrics[definition.key] = self._retain_metric(
                    definition.key,
                    value=None,
                    source_timestamp=None,
                    source=definition.source,
                    now=now,
                    error=str(err),
                )

        self._schedule_runtime_state_save()
        if successful_sources == 0 and not self._last_known_metrics:
            raise UpdateFailed("No Hungarian power data source could be updated")

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
            updated_at=now,
            errors=errors,
            sources=dict(self._source_statuses),
            mavir_retry_interval_minutes=self.mavir_retry_interval_minutes,
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
                    metric = MetricValue.from_storage(value)
                    if metric is not None and metric.value is not None:
                        self._last_known_metrics[str(key)] = metric

            stored_sources = stored.get("sources")
            if isinstance(stored_sources, dict):
                for key, value in stored_sources.items():
                    status = SourceStatus.from_storage(value)
                    if status is not None:
                        self._source_statuses[str(key)] = status

        self._runtime_state_loaded = True

    def _serialize_runtime_state(self) -> dict[str, object]:
        """Return the persisted metric and source state."""
        return {
            "metrics": {
                key: value.to_storage() for key, value in self._last_known_metrics.items()
            },
            "sources": {
                key: value.to_storage() for key, value in self._source_statuses.items()
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
