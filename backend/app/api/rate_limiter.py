"""Simple in-memory rate limiting utilities."""

from __future__ import annotations

import time


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def check(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        timestamps = self._requests.get(key, [])
        active_timestamps = [timestamp for timestamp in timestamps if timestamp > window_start]

        if len(active_timestamps) >= self.max_requests:
            self._requests[key] = active_timestamps
            return True

        active_timestamps.append(now)
        self._requests[key] = active_timestamps
        return False
