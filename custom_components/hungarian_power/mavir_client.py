"""Async client for the public MAVIR RTDW export service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import ceil

import aiohttp

from .const import (
    MAVIR_BASE_URL,
    MAVIR_REQUEST_BUDGET,
    MAVIR_REQUEST_WINDOW_SECONDS,
)
from .rate_budget import RequestBudget, RequestBudgetExceeded

_RATE_LIMIT_HEADERS = frozenset(
    {
        "retry-after",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "ratelimit-policy",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
)


def _safe_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Keep only non-sensitive rate-limit headers for diagnostics."""
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.casefold() in _RATE_LIMIT_HEADERS
    }


def _retry_after_seconds(headers: dict[str, str]) -> int | None:
    """Parse Retry-After as seconds, when the server supplies it."""
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0, ceil(float(value)))
    except (ValueError, OverflowError):
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0, ceil((retry_at - datetime.now(UTC)).total_seconds()))


@dataclass(frozen=True, slots=True)
class MavirChartResponse:
    """Successful MAVIR response with safe response metadata."""

    body: bytes
    status_code: int
    response_headers: dict[str, str]


class MavirClientError(Exception):
    """Base class for MAVIR communication failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_headers = response_headers or {}
        self.retry_after_seconds = _retry_after_seconds(self.response_headers)


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
    ) -> MavirChartResponse:
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
            safe_headers = _safe_response_headers(response.headers)
            raise MavirRateLimited(
                f"MAVIR rate-limited chart {chart_id}",
                status_code=response.status,
                response_headers=safe_headers,
            )
        safe_headers = _safe_response_headers(response.headers)
        if response.status != 200:
            raise MavirHttpError(
                f"MAVIR chart {chart_id} returned HTTP {response.status}",
                status_code=response.status,
                response_headers=safe_headers,
            )
        if not body.startswith(b"PK"):
            raise MavirHttpError(
                f"MAVIR chart {chart_id} did not return an XLSX workbook",
                status_code=response.status,
                response_headers=safe_headers,
            )
        return MavirChartResponse(body, response.status, safe_headers)
