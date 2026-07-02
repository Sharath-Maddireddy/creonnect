"""Rate limiting utilities with Redis-first counters and in-memory fallback."""

from __future__ import annotations

import hashlib
import os
import time
from threading import Lock

from backend.app.infra.redis_client import incr_with_expire
from backend.app.utils.logger import logger


class InMemoryRateLimiter:
    """Redis-backed limiter (when enabled) with safe process-local fallback.

    The class name is kept for backwards compatibility with existing imports.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        *,
        use_redis: bool | None = None,
        redis_prefix: str = "rate_limit",
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}
        self._check_count = 0
        self._cleanup_interval = 100
        self._max_tracked_keys = 10_000
        self._lock = Lock()
        if use_redis is None:
            env = (os.getenv("RATE_LIMIT_USE_REDIS", "1") or "").strip().lower()
            self._use_redis = env in {"1", "true", "yes", "on"}
        else:
            self._use_redis = bool(use_redis)
        self._redis_prefix = redis_prefix.strip() or "rate_limit"
        self._redis_disabled_logged = False
        self._namespace = self._new_namespace()

    def _new_namespace(self) -> str:
        return str(time.time_ns())

    def _redis_counter_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{self._redis_prefix}:{self._namespace}:{digest}"

    def _prune_stale_keys(self, window_start: float) -> None:
        self._requests = {
            request_key: active_timestamps
            for request_key, timestamps in self._requests.items()
            if (active_timestamps := [timestamp for timestamp in timestamps if timestamp > window_start])
        }

    def _check_in_memory(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
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

    def reset(self) -> None:
        """Reset limiter state for tests or controlled operational resets."""
        with self._lock:
            self._requests.clear()
            self._check_count = 0
            # Rotating namespace effectively resets Redis-backed counters without key scans.
            self._namespace = self._new_namespace()

    def check(self, key: str) -> bool:
        normalized_key = key.strip() if isinstance(key, str) else ""
        bucket_key = normalized_key or "anonymous"

        if self._use_redis:
            try:
                current = incr_with_expire(self._redis_counter_key(bucket_key), self.window_seconds)
                return current > self.max_requests
            except Exception as exc:  # noqa: BLE001
                if not self._redis_disabled_logged:
                    logger.warning(
                        "[RateLimiter] Redis unavailable for rate limiting; falling back to in-memory counters: %s",
                        exc,
                    )
                    self._redis_disabled_logged = True

        return self._check_in_memory(bucket_key)
