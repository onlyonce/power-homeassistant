"""Async client for the official OAH Paks operating-data page."""

from __future__ import annotations

import aiohttp

from .const import OAH_URL


class OahClientError(Exception):
    """Raised when the OAH page cannot be fetched."""


class OahClient:
    """Fetch the server-rendered OAH page."""

    def __init__(self, session: aiohttp.ClientSession, *, timeout_seconds: float = 30) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def async_fetch(self) -> str:
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
        if response.status != 200:
            raise OahClientError(f"OAH returned HTTP {response.status}")
        return body

