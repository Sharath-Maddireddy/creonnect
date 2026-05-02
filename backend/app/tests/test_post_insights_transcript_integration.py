from __future__ import annotations

import asyncio

from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, ReelAnalysis, SinglePostInsights
from backend.app.services.post_insights_service import build_single_post_insights


def test_build_single_post_insights_uses_reel_transcript_for_s2() -> None:
    target_post = SinglePostInsights(
        account_id="acct_1",
        media_id="reel_1",
        media_type="REEL",
        caption_text="tiny",
        core_metrics=CoreMetrics(reach=1000, impressions=1200, likes=100, comments=10),
        derived_metrics=DerivedMetrics(),
        benchmark_metrics=BenchmarkMetrics(),
        reel_analysis=ReelAnalysis(spoken_transcript="How to grow faster? Comment below"),
    )

    response = asyncio.run(
        build_single_post_insights(
            target_post=target_post,
            historical_posts=[],
            run_ai=False,
        )
    )

    s2 = response["post"].caption_effectiveness_score
    assert s2.hook_score_0_100 == 100
    assert s2.cta_score_0_100 == 100
    assert "Audio transcript factored into caption effectiveness scoring" in s2.notes
