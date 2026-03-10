"""Deterministic content scoring for a single post."""

from __future__ import annotations

from backend.app.domain.post_models import BenchmarkMetrics, DerivedMetrics


WEIGHT_ENGAGEMENT_RATE_PERCENT_VS_AVG = 0.30
WEIGHT_REACH_PERCENT_VS_AVG = 0.20
WEIGHT_SAVE_RATE = 0.15
WEIGHT_SHARE_RATE = 0.10
WEIGHT_PERCENTILE_ENGAGEMENT_RATE = 0.25

PERCENT_VS_AVG_MIN = -0.5
PERCENT_VS_AVG_MAX = 0.5
RATE_CAP = 0.10


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a float to an inclusive range."""
    return max(minimum, min(maximum, value))


def _normalize_percent_vs_avg(value: float | None) -> float | None:
    """Normalize decimal percent-vs-average values to 0..1 using -0.5..+0.5 anchors."""
    if value is None:
        return None
    span = PERCENT_VS_AVG_MAX - PERCENT_VS_AVG_MIN
    return _clamp((value - PERCENT_VS_AVG_MIN) / span, 0.0, 1.0)


def _normalize_rate(value: float | None, cap: float = RATE_CAP) -> float | None:
    """Normalize a rate metric to 0..1 with an upper cap."""
    if value is None:
        return None
    if cap <= 0:
        return None
    return _clamp(value / cap, 0.0, 1.0)


def _normalize_percentile(value: float | None) -> float | None:
    """Normalize percentile input to 0..1 and safely clamp out-of-range values."""
    if value is None:
        return None
    return _clamp(value, 0.0, 1.0)


def classify_score_band(score: int) -> str:
    """Map a 0-100 score into a deterministic performance band."""
    if score <= 40:
        return "NEEDS_WORK"
    if score <= 65:
        return "AVERAGE"
    if score <= 85:
        return "STRONG"
    return "EXCEPTIONAL"


def compute_content_score(
    derived: DerivedMetrics | None, benchmark: BenchmarkMetrics | None
) -> dict[str, int | str]:
    """Compute deterministic content score and score band from derived and benchmark metrics."""
    if derived is None:
        score = 0
        return {"score": score, "band": classify_score_band(score)}

    components: list[tuple[float, float | None]] = [
        (
            WEIGHT_ENGAGEMENT_RATE_PERCENT_VS_AVG,
            _normalize_percent_vs_avg(
                benchmark.engagement_rate_percent_vs_avg if benchmark is not None else None
            ),
        ),
        (
            WEIGHT_REACH_PERCENT_VS_AVG,
            _normalize_percent_vs_avg(
                benchmark.reach_percent_vs_avg if benchmark is not None else None
            ),
        ),
        (WEIGHT_SAVE_RATE, _normalize_rate(derived.save_rate)),
        (WEIGHT_SHARE_RATE, _normalize_rate(derived.share_rate)),
        (
            WEIGHT_PERCENTILE_ENGAGEMENT_RATE,
            _normalize_percentile(
                benchmark.percentile_engagement_rank if benchmark is not None else None
            ),
        ),
    ]

    weighted_sum = 0.0
    used_weight = 0.0

    for weight, normalized_value in components:
        if normalized_value is None:
            continue
        weighted_sum += weight * normalized_value
        used_weight += weight

    if used_weight < 0.4:
        score = 0
        return {"score": score, "band": classify_score_band(score)}

    score_0_to_1 = weighted_sum / used_weight
    score_0_to_100 = round(_clamp(score_0_to_1 * 100.0, 0.0, 100.0))
    score = int(score_0_to_100)
    return {"score": score, "band": classify_score_band(score)}
