"""Numeric helpers shared across services and routes."""

from __future__ import annotations

from typing import Any


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
