"""Numeric helpers shared across services and routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def safe_float(value: Any) -> float | None:
    "Convert *value* to float; return None for None, bool, or un-coercible inputs."
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_float_or(value: Any, default: float = 0.0) -> float:
    """Like safe_float but returns `default` instead of None on failure."""
    result = safe_float(value)
    return result if result is not None else default


def now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
