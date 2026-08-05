"""Tests for the evidence-aware Creator Intelligence Report foundation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.analytics.account_health_engine import _generate_engagement_heatmap
from backend.app.domain.account_models import (
    AccountEngagementSignals,
    AccountHealthMetadata,
    AccountHealthScore,
    BrandReadiness,
    ContentPillar,
    HashtagPerformance,
    TopPostSummary,
    DeterministicRecommendation,
)
from backend.app.domain.creator_intelligence_report_models import CreatorIntelligenceMetric
from backend.app.domain.post_models import (
    CaptionEffectivenessScore,
    CoreMetrics,
    DerivedMetrics,
    ReelAnalysis,
    SinglePostInsights,
    VisionAnalysis,
    VisualQualityScore,
)
from backend.app.services.creator_intelligence_report_service import build_creator_intelligence_report


def _post(index: int, *, engagement_rate: float | None) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="account_1",
        media_id=f"post_{index}",
        media_type="REEL",
        published_at=datetime(2025, 1, 6, 18, tzinfo=timezone.utc) + timedelta(days=index * 7),
        core_metrics=CoreMetrics(reach=1000),
        derived_metrics=DerivedMetrics(engagement_rate=engagement_rate),
    )


def test_heatmap_requires_three_posts_with_observed_engagement() -> None:
    assert _generate_engagement_heatmap([_post(0, engagement_rate=0.08), _post(1, engagement_rate=0.07)]) == []
    assert _generate_engagement_heatmap([_post(0, engagement_rate=None) for _ in range(3)]) == []

    heatmap = _generate_engagement_heatmap([_post(index, engagement_rate=0.08) for index in range(3)])

    assert len(heatmap) == 1
    assert heatmap[0].day_of_week == 0
    assert heatmap[0].hour_of_day == 18


def test_report_contains_all_metrics_and_marks_missing_inputs_unavailable() -> None:
    health = AccountHealthScore(
        ahs_score=72.5,
        ahs_band="STRONG",
        metadata=AccountHealthMetadata(post_count_used=12, time_window_days=28),
        engagement_signals=AccountEngagementSignals(virality_potential=61.0),
        top_posts=[TopPostSummary(media_id="post_1", engagement_rate=0.08)],
        top_hashtags=[HashtagPerformance(hashtag="creator", post_count=3, engagement_rate=0.07)],
        content_pillars=[ContentPillar(name="education", engagement_percentage=70.0)],
        brand_readiness=BrandReadiness(score=68.0, label="Promising"),
    )

    report = build_creator_intelligence_report(health)
    by_id = {metric.metric_id: metric for metric in report.metrics}

    assert len(report.metrics) == 26
    assert report.report_status == "partial"
    assert by_id["overall_account_grade"].value == {"score": 72.5, "band": "STRONG"}
    assert by_id["growth_potential"].status == "unavailable"
    assert by_id["growth_potential"].value is None
    assert by_id["growth_potential"].availability_guidance
    assert by_id["brand_readiness"].status == "derived"


def test_unavailable_metric_rejects_synthetic_values() -> None:
    with pytest.raises(ValidationError):
        CreatorIntelligenceMetric(
            metric_id="growth_potential",
            label="Growth Potential",
            category="account",
            status="unavailable",
            value=50,
            unavailable_reason="insufficient_follower_history",
            availability_guidance="Collect follower snapshots.",
        )


def test_growth_uses_only_snapshots_separated_by_seven_days() -> None:
    health = AccountHealthScore(metadata=AccountHealthMetadata(post_count_used=10, time_window_days=28))
    first = datetime(2026, 7, 1, tzinfo=timezone.utc)
    snapshots = [
        SimpleNamespace(observed_at=first, follower_count=1000),
        SimpleNamespace(observed_at=first + timedelta(days=7), follower_count=1100),
    ]

    report = build_creator_intelligence_report(health, follower_snapshots=snapshots)
    growth = next(metric for metric in report.metrics if metric.metric_id == "growth_potential")

    assert growth.status == "derived"
    assert growth.value["observed_growth_pct"] == 10.0
    assert growth.source_data_at == first + timedelta(days=7)
    assert growth.evidence_details[0].source == "follower_snapshots"


def test_growth_projection_requires_four_snapshots_and_twenty_eight_days() -> None:
    health = AccountHealthScore(metadata=AccountHealthMetadata(post_count_used=10, time_window_days=28))
    first = datetime(2026, 7, 1, tzinfo=timezone.utc)
    snapshots = [
        SimpleNamespace(observed_at=first + timedelta(days=days), follower_count=1000 + (days * 10))
        for days in (0, 10, 20, 30)
    ]

    report = build_creator_intelligence_report(health, follower_snapshots=snapshots)
    growth = next(metric for metric in report.metrics if metric.metric_id == "growth_potential")

    assert growth.status == "predicted"
    assert growth.value["projection"]["thirty_day_followers"] == 1600
    assert growth.value["projection"]["ninety_day_followers"] == 2200


def test_competitor_analysis_requires_a_real_cohort_of_thirty() -> None:
    health = AccountHealthScore(ahs_score=80, metadata=AccountHealthMetadata(post_count_used=10))
    peers = [SimpleNamespace(ahs_score=70 + (index % 5), predicted_engagement_rate=0.04) for index in range(30)]

    report = build_creator_intelligence_report(health, peer_cohort=peers)
    competitor_analysis = next(metric for metric in report.metrics if metric.metric_id == "competitor_analysis")

    assert competitor_analysis.status == "derived"
    assert competitor_analysis.value["cohort_size"] == 30
    assert competitor_analysis.value["account_score_percentile"] == 100.0


def test_recommendations_produce_a_deterministic_action_plan_and_checklist() -> None:
    health = AccountHealthScore(
        recommendations=[
            DeterministicRecommendation(id="hooks", text="Improve the first three seconds.", impact_level="HIGH"),
            DeterministicRecommendation(id="cadence", text="Post consistently each week.", impact_level="MEDIUM"),
        ]
    )

    report = build_creator_intelligence_report(health)
    by_id = {metric.metric_id: metric for metric in report.metrics}

    assert by_id["thirty_day_plan"].status == "derived"
    assert by_id["thirty_day_plan"].value[0]["focus"][0]["recommendation_id"] == "hooks"
    assert by_id["weekly_checklist"].value[1]["completed"] is False


def test_reel_availability_manifest_requires_observed_inputs() -> None:
    posts = [_post(index, engagement_rate=0.08) for index in range(3)]
    for post in posts:
        post.derived_metrics.watch_through_rate = 0.62
        post.reel_analysis = ReelAnalysis(total=75.0, reel_vision_status="ok")

    report = build_creator_intelligence_report(AccountHealthScore(), posts=posts)

    assert report.reel_data_availability.reel_post_count == 3
    assert report.reel_data_availability.editing_quality_available is True
    assert report.reel_data_availability.retention_available is True

    by_id = {metric.metric_id: metric for metric in report.metrics}
    assert by_id["editing_quality"].status == "derived"
    assert by_id["retention"].value["average_watch_through_rate"] == 0.62


def test_post_rankings_require_three_observed_engagement_rates() -> None:
    posts = [_post(0, engagement_rate=0.03), _post(1, engagement_rate=0.11), _post(2, engagement_rate=0.06)]

    report = build_creator_intelligence_report(AccountHealthScore(), posts=posts)
    by_id = {metric.metric_id: metric for metric in report.metrics}

    assert by_id["best_posts"].value[0]["media_id"] == "post_1"
    assert by_id["worst_posts"].value[0]["media_id"] == "post_0"


def test_content_quality_rollups_require_analyzed_posts() -> None:
    posts = [_post(index, engagement_rate=0.04 + (index * 0.01)) for index in range(3)]
    for index, post in enumerate(posts):
        post.caption_text = f"Creator hook {index}. A complete caption with a clear call to action."
        post.caption_effectiveness_score = CaptionEffectivenessScore(s2_raw_0_100=70, cta_score_0_100=60)
        post.vision_analysis = VisionAnalysis(status="ok")
        post.visual_quality_score = VisualQualityScore(
            total=35,
            composition=7,
            lighting=6,
            subject_clarity=8,
            aesthetic_quality=7,
        )
        post.reel_analysis = ReelAnalysis(hook_score=30 + index, total=70)

    report = build_creator_intelligence_report(AccountHealthScore(), posts=posts)
    by_id = {metric.metric_id: metric for metric in report.metrics}

    assert by_id["caption_quality"].value["score"] == 70.0
    assert by_id["cta_performance"].value["score"] == 60.0
    assert by_id["visual_quality"].value["score"] == 70.0
    assert by_id["best_hooks"].value[0]["media_id"] == "post_2"


def test_content_pillars_and_fatigue_use_comparable_dated_posts() -> None:
    posts = [
        _post(index, engagement_rate=0.10 if index < 3 else 0.05)
        for index in range(6)
    ]
    start = datetime(2026, 8, 1, 18, tzinfo=timezone.utc)
    for index, post in enumerate(posts):
        post.post_category = "education"
        post.published_at = start + timedelta(days=index)
        post.core_metrics.reach = 1000 + (index * 100)
        post.derived_metrics.save_rate = 0.02
        post.derived_metrics.share_rate = 0.01

    report = build_creator_intelligence_report(AccountHealthScore(), posts=posts)
    by_id = {metric.metric_id: metric for metric in report.metrics}

    assert by_id["content_pillars"].value[0]["name"] == "education"
    assert by_id["content_pillars"].value[0]["post_count"] == 6
    assert by_id["content_fatigue"].value["fatigue_detected"] is True
    assert by_id["content_fatigue"].value["engagement_decline_pct"] == 50.0
