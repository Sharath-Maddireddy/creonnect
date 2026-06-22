"""Circuit breaker pattern for OpenAI API resilience.

Prevents cascading failures when OpenAI API is down or rate-limited.
Falls back to cached results gracefully.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, TypeVar, Optional, Any

from backend.app.utils.logger import logger

T = TypeVar('T')


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"        # Normal operation
    OPEN = "open"           # API failing, reject requests
    HALF_OPEN = "half_open" # Test if API recovered


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass


class OpenAICircuitBreaker:
    """Circuit breaker for OpenAI API calls.
    
    Transitions:
    - CLOSED → OPEN: After N failures
    - OPEN → HALF_OPEN: After timeout seconds
    - HALF_OPEN → CLOSED: After M successes
    - HALF_OPEN → OPEN: On failure
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        name: str = "OpenAICircuitBreaker"
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.name = name

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitBreakerState.CLOSED

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any
    ) -> T:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result of func(*args, **kwargs)
            
        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: Any exception raised by func
        """
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                logger.info(f"[{self.name}] Entering HALF_OPEN state, attempting reset")
                self.state = CircuitBreakerState.HALF_OPEN
            else:
                raise CircuitBreakerOpen(
                    f"{self.name} is OPEN. Circuit will retry in "
                    f"{self._seconds_until_retry()}s."
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure(exc)
            raise

    def _on_success(self) -> None:
        """Handle successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            logger.debug(
                f"[{self.name}] Success in HALF_OPEN state "
                f"({self.success_count}/{self.success_threshold})"
            )

            if self.success_count >= self.success_threshold:
                logger.info(f"[{self.name}] Circuit closing (recovered)")
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def _on_failure(self, exc: Exception) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        logger.warning(
            f"[{self.name}] Call failed ({self.failure_count}/{self.failure_threshold}): {exc}"
        )

        if self.failure_count >= self.failure_threshold:
            logger.error(
                f"[{self.name}] Failure threshold reached. "
                f"Opening circuit for {self.recovery_timeout}s."
            )
            self.state = CircuitBreakerState.OPEN

        if self.state == CircuitBreakerState.HALF_OPEN:
            logger.warning(
                f"[{self.name}] Circuit re-opening (recovery failed)"
            )
            self.state = CircuitBreakerState.OPEN
            self.success_count = 0

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self.last_failure_time:
            return False
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        should_reset = elapsed >= self.recovery_timeout
        if should_reset:
            logger.debug(
                f"[{self.name}] Recovery timeout elapsed ({elapsed}s >= {self.recovery_timeout}s)"
            )
        return should_reset

    def _seconds_until_retry(self) -> int:
        """Get seconds until next retry is possible."""
        if not self.last_failure_time:
            return 0
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        remaining = max(0, int(self.recovery_timeout - elapsed))
        return remaining

    def is_closed(self) -> bool:
        """Check if circuit is in normal operating state."""
        return self.state == CircuitBreakerState.CLOSED

    def is_open(self) -> bool:
        """Check if circuit is open (rejecting requests)."""
        return self.state == CircuitBreakerState.OPEN

    def reset(self) -> None:
        """Manual reset (for testing)."""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        logger.info(f"[{self.name}] Manually reset")


# Global circuit breaker instance for OpenAI
openai_circuit_breaker = OpenAICircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    success_threshold=2,
    name="OpenAI-API"
)
