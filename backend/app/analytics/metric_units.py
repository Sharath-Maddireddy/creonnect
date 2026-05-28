from __future__ import annotations


def percent_from_ratio(ratio: float) -> float:
    return ratio * 100.0


def ratio_from_percent(percent: float) -> float:
    return percent / 100.0


def safe_percent(numerator: float, denominator: float) -> tuple[float, bool]:
    if denominator <= 0:
        return 0.0, False
    return (numerator / denominator) * 100.0, True
