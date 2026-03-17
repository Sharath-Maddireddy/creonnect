"""Tests for deterministic account-level health aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.analytics.account_health_engine import _build_engagement_quality, compute_account_health_score
from backend.app.domain.post_models import (
    AudienceRelevanceScore,
    BenchmarkMetrics,
    BrandSafetyPenalty,
    BrandSafetyScore,
    CaptionEffectivenessScore,
    ContentClarityScore,
    CoreMetrics,
    DerivedMetrics,
    SinglePostInsights,
    VisualQualityScore,
    WeightedPostScore,
)


def _build_post(
    idx: int,
    *,
    s1: float = 35.0,
    s2: float = 35.0,
    s3: float = 35.0,
    s4: float = 35.0,
    s6_raw: int = 90,
    s6_total: float = 45.0,
    weighted_score: float = 75.0,
    engagement_rate: float = 0.07,
    save_rate: float = 0.02,
    share_rate: float = 0.01,
    penalty_keys: list[str] | None = None,
) -> SinglePostInsights:
    penalties = [
        BrandSafetyPenalty(key=key, penalty=25 if key == "caption_profanity" else 35, reason=f"{key} detected")
        for key in (penalty_keys or [])
    ]
    flags = {
        "profanity_detected": "caption_profanity" in (penalty_keys or []),
        "alcohol_tobacco_detected": "alcohol_tobacco_content" in (penalty_keys or []),
    }

    return SinglePostInsights(
        account_id="acct_ahs",
        media_id=f"m_{idx}",
        media_url="https://example.com/post.jpg",
        media_type="IMAGE",
        caption_text="Deterministic test caption.",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=idx),
        core_metrics=CoreMetrics(
            reach=2000 + idx,
            impressions=2200 + idx,
            likes=120,
            comments=20,
            saves=25,
            shares=15,
            profile_visits=8,
            website_taps=2,
        ),
        derived_metrics=DerivedMetrics(
            engagement_rate=engagement_rate,
            save_rate=save_rate,
            share_rate=share_rate,
        ),
        benchmark_metrics=BenchmarkMetrics(account_avg_engagement_rate=0.06),
        visual_quality_score=VisualQualityScore(total=s1),
        caption_effectiveness_score=CaptionEffectivenessScore(total_0_50=s2),
        content_clarity_score=ContentClarityScore(total=s3),
        audience_relevance_score=AudienceRelevanceScore(total_0_50=s4),
        brand_safety_score=BrandSafetyScore(
            s6_raw_0_100=s6_raw,
            total_0_50=s6_total,
            penalties=penalties,
            flags=flags,
        ),
        weighted_post_score=WeightedPostScore(score=weighted_score, normalized_score_0_50=weighted_score / 2.0),
    )


def test_happy_path_30_posts() -> None:
    posts = [
        _build_post(
            i,
            s1=41.0,
            s2=39.0,
            s3=40.0,
            s4=42.0,
            s6_raw=92,
            s6_total=46.0,
            weighted_score=84.0,
            engagement_rate=0.09,
            save_rate=0.03,
            share_rate=0.02,
        )
        for i in range(30)
    ]

    result = compute_account_health_score(
        posts,
        account_avg_engagement_rate=0.06,
        niche_avg_engagement_rate=0.055,
        follower_band="50k-100k",
    )

    assert result.ahs_score >= 75.0
    assert result.metadata.post_count_used == 30
    assert result.pillars["content_quality"].score >= 70.0


def test_low_content_quality() -> None:
    posts = [
        _build_post(
            i,
            s1=10.0,
            s2=12.0,
            s3=11.0,
            s4=30.0,
            s6_raw=90,
            s6_total=45.0,
            weighted_score=45.0,
            engagement_rate=0.05,
        )
        for i in range(20)
    ]
    result = compute_account_health_score(posts, account_avg_engagement_rate=0.06)

    assert result.pillars["content_quality"].score < 50.0
    assert result.ahs_score < 70.0
    assert any(driver.id == "content_quality_low" for driver in result.drivers)


def test_one_viral_outlier_antigravity() -> None:
    weak_posts = [
        _build_post(
            i,
            s1=12.0,
            s2=12.0,
            s3=13.0,
            s4=18.0,
            s6_raw=85,
            s6_total=42.5,
            weighted_score=35.0,
            engagement_rate=0.02,
            save_rate=0.005,
            share_rate=0.004,
        )
        for i in range(29)
    ]
    outlier = _build_post(
        99,
        s1=50.0,
        s2=50.0,
        s3=50.0,
        s4=45.0,
        s6_raw=100,
        s6_total=50.0,
        weighted_score=100.0,
        engagement_rate=0.30,
        save_rate=0.08,
        share_rate=0.05,
    )

    result = compute_account_health_score(weak_posts + [outlier], account_avg_engagement_rate=0.06)
    assert result.ahs_score < 60.0
    assert result.ahs_band != "EXCEPTIONAL"


def test_missing_history_threshold() -> None:
    posts = [_build_post(i, s1=35.0, s2=34.0, s3=36.0, engagement_rate=0.07) for i in range(5)]
    result = compute_account_health_score(posts, account_avg_engagement_rate=0.06)

    assert result.metadata.min_history_threshold_met is False
    assert result.metadata.post_count_used == 5
    assert result.ahs_score >= 0.0
    assert any("history" in driver.explanation.lower() for driver in result.drivers)


def test_brand_safety_penalty() -> None:
    safe_posts = [_build_post(i, s6_raw=92, s6_total=46.0, weighted_score=78.0, engagement_rate=0.07) for i in range(16)]
    risky_posts = [
        _build_post(
            100 + i,
            s6_raw=35,
            s6_total=17.5,
            weighted_score=55.0,
            engagement_rate=0.05,
            penalty_keys=["caption_profanity", "alcohol_tobacco_content"],
        )
        for i in range(4)
    ]

    safe_baseline = compute_account_health_score(safe_posts, account_avg_engagement_rate=0.06)
    result = compute_account_health_score(safe_posts + risky_posts, account_avg_engagement_rate=0.06)
    assert result.pillars["brand_safety"].score < safe_baseline.pillars["brand_safety"].score
    assert any(driver.id == "brand_safety_risks" for driver in result.drivers)


def test_determinism() -> None:
    posts = [_build_post(i, s1=33.0, s2=32.0, s3=34.0, engagement_rate=0.065) for i in range(12)]
    now = datetime(2026, 2, 24, tzinfo=timezone.utc)
    first = compute_account_health_score(posts, account_avg_engagement_rate=0.06, now_ts=now).model_dump(mode="python")
    second = compute_account_health_score(posts, account_avg_engagement_rate=0.06, now_ts=now).model_dump(mode="python")
    assert first == second


def test_consistency_uses_timestamp_count_for_cadence() -> None:
    posts = [_build_post(i, weighted_score=80.0, engagement_rate=0.07) for i in range(4)]
    posts[1].published_at = None
    posts[3].published_at = None

    result = compute_account_health_score(posts, account_avg_engagement_rate=0.06)
    assert result.pillars["consistency"].score == 90.0


def test_engagement_quality_fallback_uses_median_save_share_rates() -> None:
    posts = [
        _build_post(0, engagement_rate=0.07, save_rate=0.01, share_rate=0.02),
        _build_post(1, engagement_rate=0.07, save_rate=0.01, share_rate=0.02),
        _build_post(2, engagement_rate=0.07, save_rate=0.90, share_rate=0.90),
    ]
    for post in posts:
        post.derived_metrics.engagement_rate = None

    score, notes, has_signal, metrics = _build_engagement_quality(posts, account_avg_engagement_rate=0.06)

    assert score == 50.0
    assert has_signal is False
    assert any("Missing engagement_rate data" in note for note in notes)
    assert metrics["median_engagement_rate"] is None
    assert metrics["median_save_rate"] == pytest.approx(0.01)
    assert metrics["median_share_rate"] == pytest.approx(0.02)
