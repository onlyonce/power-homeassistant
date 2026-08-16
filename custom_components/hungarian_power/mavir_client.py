"""Async client for the public MAVIR RTDW export service."""

from __future__ import annotations

import aiohttp

from .const import (
    MAVIR_BASE_URL,
    MAVIR_REQUEST_BUDGET,
    MAVIR_REQUEST_WINDOW_SECONDS,
)
from .rate_budget import RequestBudget, RequestBudgetExceeded


class MavirClientError(Exception):
    """Base class for MAVIR communication failures."""


class MavirRateLimited(MavirClientError):
    """MAVIR rejected the request because of rate limiting."""


class MavirHttpError(MavirClientError):
    """MAVIR returned an unexpected HTTP response."""


class MavirClient:
    """Fetch XLSX chart exports while enforcing a shared safety budget."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        budget: RequestBudget | None = None,
        timeout_seconds: float = 30,
    ) -> None:
        self._session = session
        self._budget = budget or RequestBudget(
            MAVIR_REQUEST_BUDGET, MAVIR_REQUEST_WINDOW_SECONDS
        )
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    @property
    def remaining_requests(self) -> int:
        """Return the remaining safety-budget capacity."""
        return self._budget.remaining

    async def async_fetch_chart(
        self,
        chart_id: int,
        *,
        from_time_ms: int,
        to_time_ms: int,
        period: int,
    ) -> bytes:
        """Fetch one chart export."""
        try:
            self._budget.acquire()
        except RequestBudgetExceeded as err:
            raise MavirRateLimited(str(err)) from err

        url = f"{MAVIR_BASE_URL}/chart/{chart_id}/export"
        params = {
            "exportType": "xlsx",
            "fromTime": str(from_time_ms),
            "toTime": str(to_time_ms),
            "periodType": "min",
            "period": str(period),
        }
        headers = {
            "User-Agent": "ha-hungarian-power/0.1",
            "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

        try:
            async with self._session.get(
                url, params=params, headers=headers, timeout=self._timeout
            ) as response:
                body = await response.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MavirClientError(f"MAVIR chart {chart_id} request failed") from err

        if response.status == 429:
            raise MavirRateLimited(f"MAVIR rate-limited chart {chart_id}")
        if response.status != 200:
            raise MavirHttpError(f"MAVIR chart {chart_id} returned HTTP {response.status}")
        if not body.startswith(b"PK"):
            raise MavirHttpError(f"MAVIR chart {chart_id} did not return an XLSX workbook")
        return body

