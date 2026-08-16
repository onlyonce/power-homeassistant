"""Home Assistant data coordinator for Hungarian Power."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ALL_METRICS,
    DOMAIN,
    MAVIR_CHART_PERIOD_MINUTES,
    MAVIR_HISTORY_HOURS,
    MAVIR_METRICS,
    OAH_METRICS,
)
from .mavir_client import MavirClient, MavirClientError
from .mavir_xlsx import MavirParseError, parse_mavir_xlsx
from .models import CoordinatorState, MavirChartData, MetricValue
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
    ) -> None:
        self.mavir_client = mavir_client
        self.oah_client = oah_client
        self._previous_charts: dict[int, MavirChartData] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval_minutes),
        )

    async def _async_update_data(self) -> CoordinatorState:
        """Fetch source data, preserving usable values when one source fails."""
        now = datetime.now(UTC)
        errors: dict[str, str] = {}
        successful_sources = 0
        from_time_ms = int((now - timedelta(hours=MAVIR_HISTORY_HOURS)).timestamp() * 1000)
        to_time_ms = int(now.timestamp() * 1000)

        chart_ids = sorted({metric.chart_id for metric in MAVIR_METRICS if metric.chart_id})
        for chart_id in chart_ids:
            try:
                payload = await self.mavir_client.async_fetch_chart(
                    chart_id,
                    from_time_ms=from_time_ms,
                    to_time_ms=to_time_ms,
                    period=MAVIR_CHART_PERIOD_MINUTES,
                )
                chart = await self.hass.async_add_executor_job(
                    parse_mavir_xlsx, payload, chart_id
                )
                self._previous_charts[chart_id] = chart
                successful_sources += 1
            except (MavirClientError, MavirParseError) as err:
                errors[f"mavir_{chart_id}"] = str(err)
                _LOGGER.warning("MAVIR chart %s update failed: %s", chart_id, err)

        metrics: dict[str, MetricValue] = {}
        for definition in MAVIR_METRICS:
            chart = self._previous_charts.get(definition.chart_id or -1)
            match = chart.value_for(definition.matchers) if chart else None
            metrics[definition.key] = MetricValue(
                value=match[0] if match else None,
                source_timestamp=match[1] if match else None,
                source=definition.source,
                error=errors.get(f"mavir_{definition.chart_id}"),
            )

        try:
            paks = await self.hass.async_add_executor_job(
                parse_oah_html, await self.oah_client.async_fetch()
            )
            successful_sources += 1
            for index, definition in enumerate(OAH_METRICS):
                metrics[definition.key] = MetricValue(
                    value=paks.units_mw[index],
                    source_timestamp=paks.timestamp,
                    source=definition.source,
                )
        except (OahClientError, OahParseError) as err:
            errors["oah"] = str(err)
            _LOGGER.warning("OAH update failed: %s", err)
            for definition in OAH_METRICS:
                metrics[definition.key] = MetricValue(
                    value=None,
                    source_timestamp=None,
                    source=definition.source,
                    error=str(err),
                )

        if successful_sources == 0 and not self._previous_charts:
            raise UpdateFailed("No Hungarian power data source could be updated")

        # Ensure every declared metric has a state even if a future definition is added.
        for definition in ALL_METRICS:
            metrics.setdefault(
                definition.key,
                MetricValue(None, None, definition.source, errors.get(definition.source)),
            )
        return CoordinatorState(metrics=metrics, updated_at=now, errors=errors)
