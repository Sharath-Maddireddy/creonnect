from __future__ import annotations

from backend.app.analytics.benchmark_engine import compute_benchmark_metrics
from backend.app.domain.post_models import CoreMetrics, DerivedMetrics, SinglePostInsights


def _post(reach: int, engagement_rate: float) -> SinglePostInsights:
    return SinglePostInsights(
        core_metrics=CoreMetrics(reach=reach),
        derived_metrics=DerivedMetrics(engagement_rate=engagement_rate),
    )


def test_benchmarks_require_five_valid_historical_posts() -> None:
    target = _post(1_500, 0.05)
    history = [_post(1_000, 0.03) for _ in range(4)]

    result = compute_benchmark_metrics(target, history)

    assert result.account_avg_reach is None
    assert result.percentile_engagement_rank is None
