"""
Deterministic signal scoring engine.

This module contains pure math utilities for computing numeric analytics
signals. It does not call AI systems and does not produce narrative output.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Literal, Mapping, Optional


def _to_float(value: Any, default: float = 0.0) -> float:
    """Safely coerce values to float."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Return numerator/denominator with divide-by-zero protection."""
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def _round(value: float, digits: int) -> float:
    """Round to a fixed precision."""
    return round(value, digits)


def _clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    """Clamp float between bounds."""
    return max(min_value, min(max_value, value))


def compute_engagement_rate_by_views(likes: Any, comments: Any, views: Any) -> float:
    """
    Compute engagement rate by views in percentage points.

    Formula:
    ((likes + comments) / views) * 100
    """
    likes_f = _to_float(likes)
    comments_f = _to_float(comments)
    views_f = _to_float(views)
    rate = _safe_ratio(likes_f + comments_f, views_f) * 100.0
    return _round(rate, 2)


def compute_views_to_followers_ratio(avg_views: Any, followers: Any) -> float:
    """
    Compute reach ratio (avg views / followers).
    """
    avg_views_f = _to_float(avg_views)
    followers_f = _to_float(followers)
    ratio = _safe_ratio(avg_views_f, followers_f)
    return _round(ratio, 2)


def compute_average(values: Iterable[Any]) -> Optional[float]:
    """Compute average of valid numeric values."""
    numeric_values = [_to_float(v, default=float("nan")) for v in values]
    cleaned = [v for v in numeric_values if v == v]  # NaN-safe filter
    if not cleaned:
        return None
    return _round(sum(cleaned) / len(cleaned), 2)


def compute_growth_signals(
    profile: Mapping[str, Any], posts: Iterable[Mapping[str, Any]]
) -> Dict[str, Optional[float]]:
    """
    Compute deterministic growth signals from profile and post inputs.
    """
    post_list = list(posts)
    engagement_rates = [
        compute_engagement_rate_by_views(
            likes=p.get("likes"),
            comments=p.get("comments"),
            views=p.get("views"),
        )
        for p in post_list
    ]

    avg_views = compute_average(p.get("views") for p in post_list)
    avg_engagement_rate_by_views = compute_average(engagement_rates)
    followers = _to_float(profile.get("followers"))

    return {
        "avg_engagement_rate_by_views": avg_engagement_rate_by_views,
        "avg_views": avg_views,
        "views_to_followers_ratio": compute_views_to_followers_ratio(
            avg_views=avg_views or 0.0,
            followers=followers,
        ),
        "posts_per_week": _round(_to_float(profile.get("posts_per_week")), 2),
    }


def _score_engagement(rate_pct: float) -> int:
    if rate_pct >= 10.0:
        return 40
    if rate_pct >= 7.0:
        return 34
    if rate_pct >= 5.0:
        return 28
    if rate_pct >= 3.0:
        return 22
    if rate_pct >= 1.5:
        return 16
    return 10


def _score_reach_ratio(ratio: float) -> int:
    if ratio >= 2.0:
        return 30
    if ratio >= 1.0:
        return 24
    if ratio >= 0.5:
        return 18
    if ratio >= 0.2:
        return 12
    return 8


def _score_consistency(posts_per_week: float) -> int:
    if posts_per_week >= 7.0:
        return 20
    if posts_per_week >= 5.0:
        return 17
    if posts_per_week >= 3.0:
        return 14
    if posts_per_week >= 1.0:
        return 10
    return 6


def compute_growth_score(
    profile: Mapping[str, Any], posts: Iterable[Mapping[str, Any]]
) -> Dict[str, Any]:
    """
    Deterministically compute a 0-100 growth score and metric breakdown.
    """
    metrics = compute_growth_signals(profile=profile, posts=posts)

    engagement_metric = _to_float(metrics.get("avg_engagement_rate_by_views"))
    reach_metric = _to_float(metrics.get("views_to_followers_ratio"))
    consistency_metric = _to_float(metrics.get("posts_per_week"))

    engagement_score = _score_engagement(engagement_metric)
    reach_score = _score_reach_ratio(reach_metric)
    consistency_score = _score_consistency(consistency_metric)

    total_score = min(engagement_score + reach_score + consistency_score, 100)

    return {
        "growth_score": total_score,
        "breakdown": {
            "engagement": engagement_score,
            "reach": reach_score,
            "consistency": consistency_score,
        },
        "metrics": metrics,
    }


def safe_div(numerator: Any, denominator: Any) -> float:
    """
    Safely divide two values with numeric coercion.

    Returns 0.0 when denominator is 0 after coercion.
    """
    num = _to_float(numerator)
    den = _to_float(denominator)
    if den == 0.0:
        return 0.0
    return num / den


def compute_ai_content_score_v1(
    signals: dict,
    metrics: dict,
) -> dict:
    """
    Compute deterministic AI Content Score v1 from precomputed signals + metrics.

    The model is fully deterministic:
    - normalize components to [0, 1]
    - apply fixed weights
    - clamp final score to [0, 100]
    - round to nearest integer
    """
    ENGAGEMENT_WEIGHT = 25.0
    REACH_WEIGHT = 20.0
    SAVE_DEPTH_WEIGHT = 15.0
    AUDIENCE_EXPANSION_WEIGHT = 10.0
    CONVERSION_WEIGHT = 10.0
    RETENTION_WEIGHT = 20.0

    engagement_vs_avg_percent = _to_float(signals.get("engagement_vs_avg_percent"))
    reach_vs_avg_percent = _to_float(signals.get("reach_vs_avg_percent"))
    save_rate = _to_float(signals.get("save_rate"))
    save_to_like_ratio = _to_float(signals.get("save_to_like_ratio"))
    non_follower_reach_ratio = _to_float(signals.get("non_follower_reach_ratio"))
    follows_per_1000_reach = _to_float(signals.get("follows_per_1000_reach"))

    engagement_norm = _clamp((engagement_vs_avg_percent + 0.5) / 1.0)
    reach_norm = _clamp((reach_vs_avg_percent + 0.5) / 1.0)

    save_rate_norm = _clamp(save_rate / 0.1)
    save_to_like_norm = _clamp(save_to_like_ratio / 0.5)
    save_depth_norm = (save_rate_norm * 0.6) + (save_to_like_norm * 0.4)

    audience_norm = _clamp(non_follower_reach_ratio / 0.7)
    conversion_norm = _clamp(follows_per_1000_reach / 20.0)

    component_scores = {
        "engagement": engagement_norm,
        "reach": reach_norm,
        "save_depth": save_depth_norm,
        "audience_expansion": audience_norm,
        "conversion": conversion_norm,
    }

    component_weights = {
        "engagement": ENGAGEMENT_WEIGHT,
        "reach": REACH_WEIGHT,
        "save_depth": SAVE_DEPTH_WEIGHT,
        "audience_expansion": AUDIENCE_EXPANSION_WEIGHT,
        "conversion": CONVERSION_WEIGHT,
    }

    raw_watch_through_rate = metrics.get("watch_through_rate")
    if raw_watch_through_rate is None:
        base_weight_total = sum(component_weights.values())
        redistribution_scale = (base_weight_total + RETENTION_WEIGHT) / base_weight_total
        for component_name, weight in list(component_weights.items()):
            component_weights[component_name] = weight * redistribution_scale
    else:
        watch_through_rate = _to_float(raw_watch_through_rate)
        if watch_through_rate >= 0.75:
            retention_norm = 1.0
        elif watch_through_rate >= 0.5:
            retention_norm = 0.6
        else:
            retention_norm = 0.3

        component_scores["retention"] = retention_norm
        component_weights["retention"] = RETENTION_WEIGHT

    weighted_score = 0.0
    for component_name, component_value in component_scores.items():
        weighted_score += component_value * component_weights[component_name]

    ai_content_score = int(round(_clamp(weighted_score, 0.0, 100.0)))

    ai_content_band: Literal["NEEDS_WORK", "AVERAGE", "STRONG", "EXCEPTIONAL"]
    if ai_content_score <= 40:
        ai_content_band = "NEEDS_WORK"
    elif ai_content_score <= 65:
        ai_content_band = "AVERAGE"
    elif ai_content_score <= 85:
        ai_content_band = "STRONG"
    else:
        ai_content_band = "EXCEPTIONAL"

    return {
        "ai_content_score": ai_content_score,
        "ai_content_band": ai_content_band,
        "ai_content_score_version": 1,
    }


def compute_post_signals(
    metrics: dict,
    benchmarks: dict,
    reach_breakdown: dict | None = None
) -> dict:
    """
    Compute deterministic post-level performance signals.

    Formulas:
    - reach_vs_avg_percent = (reach - account_avg_reach) / account_avg_reach
    - engagement_vs_avg_percent =
      (engagement_rate - account_avg_engagement_rate) / account_avg_engagement_rate
    - percentile_engagement_rate = benchmarks.percentile_engagement_rate (or 0)
    - non_follower_reach_ratio = non_follower_reach / reach
    - explore_reach_ratio = explore / reach
    - save_to_like_ratio = saves / likes
    - save_rate = saves / reach
    - follows_per_1000_reach = (follows_from_post / reach) * 1000
    """
    reach_value = _to_float(metrics.get("reach"))
    engagement_rate = _to_float(metrics.get("engagement_rate"))
    account_avg_reach = _to_float(benchmarks.get("account_avg_reach"))
    account_avg_engagement_rate = _to_float(
        benchmarks.get("account_avg_engagement_rate")
    )
    non_follower_reach = _to_float(metrics.get("non_follower_reach"))
    saves = _to_float(metrics.get("saves"))
    likes = _to_float(metrics.get("likes"))
    follows_from_post = _to_float(metrics.get("follows_from_post"))
    explore = _to_float((reach_breakdown or {}).get("explore"))
    raw_percentile = benchmarks.get("percentile_engagement_rate")
    percentile_engagement_rate: Optional[float] = None

    if raw_percentile is not None:
        percentile_engagement_rate = _to_float(raw_percentile)

        

    reach_vs_avg_percent = safe_div(
        reach_value - account_avg_reach,
        account_avg_reach,
    )
    engagement_vs_avg_percent = safe_div(
        engagement_rate - account_avg_engagement_rate,
        account_avg_engagement_rate,
    )
    non_follower_reach_ratio = safe_div(non_follower_reach, reach_value)
    explore_reach_ratio = safe_div(explore, reach_value)
    save_to_like_ratio = safe_div(saves, likes)
    save_rate = safe_div(saves, reach_value)
    follows_per_1000_reach = safe_div(follows_from_post, reach_value) * 1000.0

    watch_through_rate_raw = metrics.get("watch_through_rate")
    retention_strength_band: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None
    if watch_through_rate_raw is not None:
        watch_through_rate = _to_float(watch_through_rate_raw)
        if watch_through_rate >= 0.75:
            retention_strength_band = "HIGH"
        elif watch_through_rate >= 0.5:
            retention_strength_band = "MEDIUM"
        else:
            retention_strength_band = "LOW"

    engagement_band: Literal["LOW", "AVERAGE", "HIGH"]
    if engagement_vs_avg_percent > 0.2:
        engagement_band = "HIGH"
    elif engagement_vs_avg_percent < -0.2:
        engagement_band = "LOW"
    else:
        engagement_band = "AVERAGE"

    overall_performance_band: Literal["BOTTOM", "AVERAGE", "TOP"]
    if percentile_engagement_rate is None:
        overall_performance_band = "AVERAGE"
    elif percentile_engagement_rate >= 0.75:
        overall_performance_band = "TOP"
    elif percentile_engagement_rate <= 0.25:
        overall_performance_band = "BOTTOM"
    else:
        overall_performance_band = "AVERAGE"

    signals_dict = {
        "reach_vs_avg_percent": _round(reach_vs_avg_percent, 4),
        "engagement_vs_avg_percent": _round(engagement_vs_avg_percent, 4),
        "percentile_engagement_rate":
        _round(percentile_engagement_rate, 4)
        if percentile_engagement_rate is not None
        else None,
        "non_follower_reach_ratio": _round(non_follower_reach_ratio, 4),
        "explore_reach_ratio": _round(explore_reach_ratio, 4),
        "save_to_like_ratio": _round(save_to_like_ratio, 4),
        "save_rate": _round(save_rate, 4),
        "follows_per_1000_reach": _round(follows_per_1000_reach, 4),
        "retention_strength_band": retention_strength_band,
        "engagement_band": engagement_band,
        "overall_performance_band": overall_performance_band,
    }
    score_data = compute_ai_content_score_v1(signals=signals_dict, metrics=metrics)
    signals_dict.update(score_data)
    return signals_dict
