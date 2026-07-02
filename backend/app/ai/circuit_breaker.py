"""Circuit breaker pattern for OpenAI API resilience.

Prevents cascading failures when OpenAI API is down or rate-limited.
Falls back to cached results gracefully.
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

from backend.app.utils.logger import logger

T = TypeVar("T")


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # API failing, reject requests
    HALF_OPEN = "half_open"  # Test if API recovered


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""


class OpenAICircuitBreaker:
    """Circuit breaker for OpenAI API calls.

    Transitions:
    - CLOSED -> OPEN: After N failures
    - OPEN -> HALF_OPEN: After timeout seconds
    - HALF_OPEN -> CLOSED: After M successes
    - HALF_OPEN -> OPEN: On failure
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        name: str = "OpenAICircuitBreaker",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.name = name

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_monotonic: Optional[float] = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = threading.RLock()

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset_locked():
                    logger.info("[%s] Entering HALF_OPEN state, attempting reset", self.name)
                    self.state = CircuitBreakerState.HALF_OPEN
                else:
                    raise CircuitBreakerOpen(
                        f"{self.name} is OPEN. Circuit will retry in {self._seconds_until_retry_locked()}s."
                    )

        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            self._on_failure(exc)
            raise

        self._on_success()
        return result

    def _on_success(self) -> None:
        """Handle successful call."""
        with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                logger.debug(
                    "[%s] Success in HALF_OPEN state (%s/%s)",
                    self.name,
                    self.success_count,
                    self.success_threshold,
                )

                if self.success_count >= self.success_threshold:
                    logger.info("[%s] Circuit closing (recovered)", self.name)
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.last_failure_monotonic = None
            elif self.state == CircuitBreakerState.CLOSED:
                self.failure_count = 0

    def _on_failure(self, exc: Exception) -> None:
        """Handle failed call."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_monotonic = time.monotonic()

            logger.warning(
                "[%s] Call failed (%s/%s): %s",
                self.name,
                self.failure_count,
                self.failure_threshold,
                exc,
            )

            if self.state == CircuitBreakerState.HALF_OPEN:
                logger.warning("[%s] Circuit re-opening (recovery failed)", self.name)
                self.state = CircuitBreakerState.OPEN
                self.success_count = 0
                return

            if self.failure_count >= self.failure_threshold:
                logger.error(
                    "[%s] Failure threshold reached. Opening circuit for %ss.",
                    self.name,
                    self.recovery_timeout,
                )
                self.state = CircuitBreakerState.OPEN

    def _should_attempt_reset_locked(self) -> bool:
        """Check if enough time has passed to attempt recovery.

        Caller must hold ``self._lock``.
        """
        if self.last_failure_monotonic is None:
            return False
        elapsed = time.monotonic() - self.last_failure_monotonic
        should_reset = elapsed >= self.recovery_timeout
        if should_reset:
            logger.debug(
                "[%s] Recovery timeout elapsed (%.3fs >= %ss)",
                self.name,
                elapsed,
                self.recovery_timeout,
            )
        return should_reset

    def _seconds_until_retry_locked(self) -> int:
        """Get seconds until next retry is possible.

        Caller must hold ``self._lock``.
        """
        if self.last_failure_monotonic is None:
            return 0
        elapsed = time.monotonic() - self.last_failure_monotonic
        return max(0, int(self.recovery_timeout - elapsed))

    def is_closed(self) -> bool:
        """Check if circuit is in normal operating state."""
        with self._lock:
            return self.state == CircuitBreakerState.CLOSED

    def is_open(self) -> bool:
        """Check if circuit is open (rejecting requests)."""
        with self._lock:
            return self.state == CircuitBreakerState.OPEN

    def reset(self) -> None:
        """Manual reset (for testing)."""
        with self._lock:
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_monotonic = None
        logger.info("[%s] Manually reset", self.name)


# Global circuit breaker instance for OpenAI
openai_circuit_breaker = OpenAICircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    success_threshold=2,
    name="OpenAI-API",
)

