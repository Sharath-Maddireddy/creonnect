"""Deterministic benchmark metric calculations for single-post insights."""

from __future__ import annotations

from backend.app.domain.post_models import BenchmarkMetrics, SinglePostInsights


MIN_VALID_HISTORY_POSTS = 3


def empty_benchmark_metrics() -> BenchmarkMetrics:
    """Return a BenchmarkMetrics object with all fields explicitly set to None."""
    return BenchmarkMetrics(
        account_avg_reach=None,
        account_avg_engagement_rate=None,
        percentile_engagement_rank=None,
        reach_percent_vs_avg=None,
        engagement_rate_percent_vs_avg=None,
        impressions_percent_vs_avg=None,
        likes_percent_vs_avg=None,
        comments_percent_vs_avg=None,
        shares_percent_vs_avg=None,
        saves_percent_vs_avg=None,
        profile_visits_percent_vs_avg=None,
        website_taps_percent_vs_avg=None,
    )


def _to_float(value: int | float | None) -> float | None:
    """Convert numeric-like values to float safely."""
    if value is None:
        return None
    try:
        result = float(value)
        if result != result:
            return None
        return result
    except (TypeError, ValueError):
        return None


def _is_valid_history_post(post: SinglePostInsights) -> bool:
    """Check whether a historical post has the required metrics for benchmarking."""
    core_metrics = getattr(post, "core_metrics", None)
    derived_metrics = getattr(post, "derived_metrics", None)
    if core_metrics is None or derived_metrics is None:
        return False
    return core_metrics.reach is not None and derived_metrics.engagement_rate is not None


def _mean(values: list[float]) -> float | None:
    """Compute the arithmetic mean for a non-empty list."""
    if not values:
        return None
    return sum(values) / len(values)


def _percent_vs_average(value: int | float | None, average: float | None) -> float | None:
    """Compute decimal percent-vs-average safely."""
    numeric_value = _to_float(value)
    if numeric_value is None or average is None or abs(average) < 1e-12:
        return None
    return (numeric_value - average) / average


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a float to an inclusive range."""
    return max(minimum, min(maximum, value))


def _approx_equal(a: float, b: float, tol: float = 1e-12) -> bool:
    """Compare floats with a small tolerance to avoid precision issues."""
    return abs(a - b) < tol


def _collect_core_metric_values(posts: list[SinglePostInsights], metric_name: str) -> list[float]:
    """Collect non-null numeric core metric values from posts."""
    values: list[float] = []
    for post in posts:
        core_metrics = getattr(post, "core_metrics", None)
        if core_metrics is None:
            continue
        numeric_value = _to_float(getattr(core_metrics, metric_name, None))
        if numeric_value is not None:
            values.append(numeric_value)
    return values


def compute_benchmark_metrics(
    target_post: SinglePostInsights,
    historical_posts: list[SinglePostInsights],
) -> BenchmarkMetrics:
    """Compute deterministic benchmark metrics for a single target post."""
    if not _is_valid_history_post(target_post):
        return empty_benchmark_metrics()

    target_core_metrics = getattr(target_post, "core_metrics", None)
    target_derived_metrics = getattr(target_post, "derived_metrics", None)
    if target_core_metrics is None or target_derived_metrics is None:
        return empty_benchmark_metrics()

    valid_history: list[SinglePostInsights] = [
        post for post in historical_posts if _is_valid_history_post(post)
    ]

    if len(valid_history) < MIN_VALID_HISTORY_POSTS:
        return empty_benchmark_metrics()

    core_metric_names = (
        "reach",
        "impressions",
        "likes",
        "comments",
        "shares",
        "saves",
        "profile_visits",
        "website_taps",
    )

    historical_core_averages: dict[str, float | None] = {}
    for metric_name in core_metric_names:
        metric_values = _collect_core_metric_values(valid_history, metric_name)
        historical_core_averages[metric_name] = _mean(metric_values)

    engagement_values: list[float] = []
    for post in valid_history:
        if post.derived_metrics is not None:
            rate = _to_float(post.derived_metrics.engagement_rate)
            if rate is not None:
                engagement_values.append(rate)

    avg_reach = historical_core_averages["reach"]
    avg_engagement_rate = _mean(engagement_values)

    target_engagement_rate = target_derived_metrics.engagement_rate

    reach_percent_vs_avg = _percent_vs_average(target_core_metrics.reach, avg_reach)
    engagement_rate_percent_vs_avg = _percent_vs_average(
        target_engagement_rate,
        avg_engagement_rate,
    )

    percentile_engagement_rank: float | None = None
    if target_engagement_rate is not None and engagement_values:
        lower = sum(1 for v in engagement_values if v < target_engagement_rate)
        equal = sum(1 for v in engagement_values if _approx_equal(v, target_engagement_rate))
        total = len(engagement_values)
        percentile_engagement_rank = _clamp((lower + 0.5 * equal) / total, 0.0, 1.0)

    return BenchmarkMetrics(
        account_avg_reach=avg_reach,
        account_avg_engagement_rate=avg_engagement_rate,
        percentile_engagement_rank=percentile_engagement_rank,
        reach_percent_vs_avg=reach_percent_vs_avg,
        engagement_rate_percent_vs_avg=engagement_rate_percent_vs_avg,
        impressions_percent_vs_avg=_percent_vs_average(
            target_core_metrics.impressions,
            historical_core_averages["impressions"],
        ),
        likes_percent_vs_avg=_percent_vs_average(
            target_core_metrics.likes,
            historical_core_averages["likes"],
        ),
        comments_percent_vs_avg=_percent_vs_average(
            target_core_metrics.comments,
            historical_core_averages["comments"],
        ),
        shares_percent_vs_avg=_percent_vs_average(
            target_core_metrics.shares,
            historical_core_averages["shares"],
        ),
        saves_percent_vs_avg=_percent_vs_average(
            target_core_metrics.saves,
            historical_core_averages["saves"],
        ),
        profile_visits_percent_vs_avg=_percent_vs_average(
            target_core_metrics.profile_visits,
            historical_core_averages["profile_visits"],
        ),
        website_taps_percent_vs_avg=_percent_vs_average(
            target_core_metrics.website_taps,
            historical_core_averages["website_taps"],
        ),
    )
