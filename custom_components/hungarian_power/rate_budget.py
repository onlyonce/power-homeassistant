"""Small sliding-window request budget for the MAVIR export service."""

from __future__ import annotations

from collections import deque
from time import monotonic


class RequestBudgetExceeded(Exception):
    """Raised before a request would exceed the configured safety budget."""


class RequestBudget:
    """Track requests in a sliding time window."""

    def __init__(self, maximum: int, window_seconds: float) -> None:
        self._maximum = maximum
        self._window_seconds = window_seconds
        self._requests: deque[float] = deque()

    def acquire(self) -> None:
        """Reserve one request or raise if the safety budget is exhausted."""
        now = monotonic()
        self._prune(now)
        if len(self._requests) >= self._maximum:
            raise RequestBudgetExceeded(
                f"MAVIR request safety budget exhausted ({self._maximum} requests)"
            )
        self._requests.append(now)

    @property
    def remaining(self) -> int:
        """Return the number of requests still available in this window."""
        now = monotonic()
        self._prune(now)
        return self._maximum - len(self._requests)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._requests and self._requests[0] <= cutoff:
            self._requests.popleft()

