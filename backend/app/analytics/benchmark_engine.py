"""Deterministic benchmark metric calculations for single-post insights."""

from __future__ import annotations

from backend.app.domain.post_models import BenchmarkMetrics, SinglePostInsights


MIN_VALID_HISTORY_POSTS = 3


def _empty_benchmark_metrics() -> BenchmarkMetrics:
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


def _is_valid_history_post(post: SinglePostInsights) -> bool:
    """Check whether a historical post has the required metrics for benchmarking."""
    return (
        post.derived_metrics.engagement_rate is not None
        and post.core_metrics.reach is not None
    )


def _mean(values: list[float]) -> float | None:
    """Compute the arithmetic mean for a non-empty list."""
    if not values:
        return None
    return sum(values) / len(values)


def _percent_vs_average(value: int | float | None, average: float | None) -> float | None:
    """Compute decimal percent-vs-average safely."""
    if value is None or average in (None, 0.0):
        return None
    return (float(value) - average) / average


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a float to an inclusive range."""
    return max(minimum, min(maximum, value))


def compute_benchmark_metrics(
    target_post: SinglePostInsights,
    historical_posts: list[SinglePostInsights],
) -> BenchmarkMetrics:
    """Compute deterministic benchmark metrics for a single target post."""
    valid_history: list[SinglePostInsights] = [
        post for post in historical_posts if _is_valid_history_post(post)
    ]

    if len(valid_history) < MIN_VALID_HISTORY_POSTS:
        return _empty_benchmark_metrics()

    reach_values: list[float] = [float(post.core_metrics.reach) for post in valid_history]
    engagement_values: list[float] = [
        float(post.derived_metrics.engagement_rate) for post in valid_history
    ]

    avg_reach = _mean(reach_values)
    avg_engagement_rate = _mean(engagement_values)

    target_reach = target_post.core_metrics.reach
    target_engagement_rate = target_post.derived_metrics.engagement_rate

    reach_percent_vs_avg = _percent_vs_average(target_reach, avg_reach)
    engagement_rate_percent_vs_avg = _percent_vs_average(
        target_engagement_rate,
        avg_engagement_rate,
    )

    percentile_engagement_rank: float | None = None
    if target_engagement_rate is not None:
        lower_count = sum(1 for value in engagement_values if value < target_engagement_rate)
        percentile_engagement_rank = _clamp(lower_count / len(engagement_values), 0.0, 1.0)

    return BenchmarkMetrics(
        account_avg_reach=avg_reach,
        account_avg_engagement_rate=avg_engagement_rate,
        reach_percent_vs_avg=reach_percent_vs_avg,
        engagement_rate_percent_vs_avg=engagement_rate_percent_vs_avg,
        percentile_engagement_rank=percentile_engagement_rank,
    )
