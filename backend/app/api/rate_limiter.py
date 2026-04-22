"""Simple in-memory rate limiting utilities."""

from __future__ import annotations

import time


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}
        self._check_count = 0
        self._cleanup_interval = 100
        self._max_tracked_keys = 10_000

    def _prune_stale_keys(self, window_start: float) -> None:
        self._requests = {
            request_key: active_timestamps
            for request_key, timestamps in self._requests.items()
            if (active_timestamps := [timestamp for timestamp in timestamps if timestamp > window_start])
        }

    def check(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        self._check_count += 1

        if self._check_count >= self._cleanup_interval or len(self._requests) > self._max_tracked_keys:
            self._prune_stale_keys(window_start)
            self._check_count = 0

        timestamps = self._requests.get(key, [])
        active_timestamps = [timestamp for timestamp in timestamps if timestamp > window_start]

        if len(active_timestamps) >= self.max_requests:
            self._requests[key] = active_timestamps
            return True

        active_timestamps.append(now)
        self._requests[key] = active_timestamps
        return False
