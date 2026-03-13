"""Deterministic predicted engagement rate engine."""

from __future__ import annotations

from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def compute_predicted_engagement_rate(
    tier_avg_er: float | None,
    s5_total: float | None,
) -> tuple[float | None, list[str]]:
    """Compute predicted ER using: tier_avg_ER * (S5.total / 50).

    Output unit follows `tier_avg_er`:
    - If tier_avg_er <= 1.0, treat as fraction and cap predicted to 1.0.
    - Else, treat as percent and cap predicted to 100.0.
    """

    notes: list[str] = []
    tier_avg = _to_float(tier_avg_er)
    s5 = _to_float(s5_total)

    if tier_avg is None:
        notes.append("missing tier_avg_er")
    if s5 is None:
        notes.append("missing s5_total")
    if notes:
        return None, notes

    if s5 != _clamp(s5, 0.0, 50.0):
        notes.append("s5_total clamped to 0..50")
    s5 = _clamp(s5, 0.0, 50.0)

    if tier_avg < 0:
        notes.append("tier_avg_er is negative; treating predicted as 0")
        return 0.0, notes

    predicted = tier_avg * (s5 / 50.0)
    predicted = max(0.0, predicted)

    if tier_avg <= 1.0:
        if predicted > 1.0:
            notes.append("predicted_engagement_rate capped at 1.0 (fraction unit)")
        predicted = min(predicted, 1.0)
    else:
        if predicted > 100.0:
            notes.append("predicted_engagement_rate capped at 100.0 (percent unit)")
        predicted = min(predicted, 100.0)

    return round(predicted, 6), notes
