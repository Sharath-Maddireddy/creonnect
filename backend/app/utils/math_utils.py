"""Small shared math helpers."""

from __future__ import annotations


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
