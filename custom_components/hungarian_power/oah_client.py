"""Async client for the official OAH Paks operating-data page."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import aiohttp

from .const import OAH_URL

_DIAGNOSTIC_HEADERS = frozenset({"content-type", "retry-after"})


def _safe_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Keep only harmless response headers for diagnostics."""
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).casefold() in _DIAGNOSTIC_HEADERS
    }


@dataclass(frozen=True, slots=True)
class OahResponse:
    """Successful OAH response with response metadata."""

    body: str
    status_code: int
    response_headers: dict[str, str]


class OahClientError(Exception):
    """Raised when the OAH page cannot be fetched."""

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


class OahClient:
    """Fetch the server-rendered OAH page."""

    def __init__(self, session: aiohttp.ClientSession, *, timeout_seconds: float = 30) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def async_fetch(self) -> OahResponse:
        """Return the current OAH HTML document."""
        try:
            async with self._session.get(
                OAH_URL,
                headers={"User-Agent": "ha-hungarian-power/0.1"},
                timeout=self._timeout,
            ) as response:
                body = await response.text(errors="replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise OahClientError("OAH request failed") from err
        safe_headers = _safe_response_headers(response.headers)
        if response.status != 200:
            raise OahClientError(
                f"OAH returned HTTP {response.status}",
                status_code=response.status,
                response_headers=safe_headers,
            )
        return OahResponse(body, response.status, safe_headers)
