"""Deterministic derived metric calculations for a single post."""

from __future__ import annotations

from backend.app.domain.post_models import CoreMetrics, DerivedMetrics


def _safe_divide(numerator: int | None, denominator: int | None) -> float | None:
    """Safely divide two integer metrics, returning None for invalid inputs."""
    if denominator in (None, 0):
        return None
    if numerator is None:
        return None
    return numerator / denominator


def _to_int(value: int | None) -> int:
    """Normalize nullable integer metrics to deterministic integer values."""
    return 0 if value is None else value


def compute_derived_metrics(core: CoreMetrics) -> DerivedMetrics:
    """Compute deterministic derived rates and totals from core single-post metrics."""
    engagements_total = (
        _to_int(core.likes)
        + _to_int(core.comments)
        + _to_int(core.shares)
        + _to_int(core.saves)
    )

    return DerivedMetrics(
        engagement_rate=_safe_divide(engagements_total, core.reach),
        save_rate=_safe_divide(core.saves, core.reach),
        share_rate=_safe_divide(core.shares, core.reach),
        like_rate=_safe_divide(core.likes, core.reach),
        comment_rate=_safe_divide(core.comments, core.reach),
        profile_visit_rate=_safe_divide(core.profile_visits, core.reach),
        website_tap_rate=_safe_divide(core.website_taps, core.reach),
        reach_to_impression_ratio=_safe_divide(core.reach, core.impressions),
        save_to_share_ratio=_safe_divide(core.saves, core.shares),
        engagements_total=engagements_total,
    )
