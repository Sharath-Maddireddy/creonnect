"""Unit tests for deterministic niche benchmark context helpers."""

from __future__ import annotations

from backend.app.analytics.niche_benchmark_engine import _build_commentary, compute_niche_benchmark_context
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights


def _build_post(engagement_rate: float | None, save_rate: float | None) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_niche",
        media_id="media_niche",
        media_type="IMAGE",
        core_metrics=CoreMetrics(),
        derived_metrics=DerivedMetrics(engagement_rate=engagement_rate, save_rate=save_rate),
        benchmark_metrics=BenchmarkMetrics(),
    )


def test_build_commentary_engagement_above_save_below() -> None:
    commentary = _build_commentary(
        post_engagement_rate=0.12,
        niche_avg_engagement_rate=0.10,
        post_save_rate=0.03,
        niche_avg_save_rate=0.05,
    )
    assert commentary == "Mixed signal: engagement is above niche average, but save rate is below niche average."


def test_compute_niche_benchmark_context_mixed_signal_commentary() -> None:
    target_post = _build_post(engagement_rate=0.12, save_rate=0.03)

    context = compute_niche_benchmark_context(
        target_post=target_post,
        niche_avg_engagement_rate=0.10,
        niche_avg_save_rate=0.05,
        category="fitness",
    )

    assert context["commentary"] == (
        "Mixed signal: engagement is above niche average, but save rate is below niche average."
    )
