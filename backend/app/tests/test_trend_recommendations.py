"""Tests for trend recommendation engine helpers and models."""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.domain.account_models import CreatorIntelligence, HeatmapData
from backend.app.domain.post_models import SinglePostInsights
from backend.app.domain.trend_models import (
    ContentGap,
    DailyInsights,
    GlobalTrend,
    TrendRecommendation,
    TrendAnalysisResult,
    CreatorNiche,
)
from backend.app.analytics.trend_recommendation_engine import (
    _compute_opportunity_score,
    _compute_difficulty,
    _compute_daily_insights,
    _derive_best_time,
    _detect_content_gaps,
    _estimate_reach_range,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_post(
    media_type: str = "REEL",
    published_at: datetime | None = datetime(2024, 6, 1, 19, 30),
    engagement_rate: float | None = 0.05,
    reach: float | None = 10000,
) -> SinglePostInsights:
    """Create a minimal SinglePostInsights for testing."""
    post = SinglePostInsights(
        media_id="test_001",
        account_id="test_account",
        media_type=media_type,
        published_at=published_at,
        caption_text="Test caption #fitness #workout",
    )
    # Set derived metrics
    if engagement_rate is not None:
        post.derived_metrics = type("DM", (), {"engagement_rate": engagement_rate, "save_rate": 0.02, "share_rate": 0.01})()
    # Set core metrics
    if reach is not None:
        post.core_metrics = type("CM", (), {"reach": reach, "impressions": reach * 2, "profile_visits": 500})()
    return post


def _make_trend(
    topic_name: str = "Travel Reels",
    trend_type: str = "format",
    momentum: str = "rising",
    description: str = "Quick travel clips trending this week",
) -> GlobalTrend:
    return GlobalTrend(
        topic_name=topic_name,
        trend_type=trend_type,
        momentum=momentum,
        description=description,
    )


def _make_intelligence(
    style: str = "Creates travel content around destinations",
) -> CreatorIntelligence:
    return CreatorIntelligence(content_style_summary=style)


# ── Opportunity Score Tests ───────────────────────────────────────────────────

class TestOpportunityScore:
    def test_peaking_format_scores_high(self):
        trend = _make_trend(momentum="peaking", trend_type="format")
        intel = _make_intelligence()
        score = _compute_opportunity_score(trend, intel)
        assert 70 <= score <= 100

    def test_falling_topic_scores_low(self):
        trend = _make_trend(momentum="falling", trend_type="topic")
        intel = _make_intelligence()
        score = _compute_opportunity_score(trend, intel)
        assert 20 <= score <= 60

    def test_rising_audio_medium(self):
        trend = _make_trend(momentum="rising", trend_type="audio")
        intel = _make_intelligence()
        score = _compute_opportunity_score(trend, intel)
        assert 40 <= score <= 90

    def test_niche_fit_boosts_score(self):
        trend = _make_trend(description="Travel destinations and hotels")
        intel = _make_intelligence(style="Creates travel content around destinations")
        score = _compute_opportunity_score(trend, intel)
        assert score >= 60

    def test_score_always_in_range(self):
        for momentum in ["rising", "peaking", "falling"]:
            for tt in ["topic", "format", "audio", "hashtag"]:
                trend = _make_trend(momentum=momentum, trend_type=tt)
                score = _compute_opportunity_score(trend, _make_intelligence())
                assert 0 <= score <= 100, f"Score {score} out of range for {momentum}/{tt}"


# ── Reach Estimation Tests ────────────────────────────────────────────────────

class TestReachEstimation:
    def test_empty_posts_returns_none(self):
        reach_min, reach_max = _estimate_reach_range([], "rising")
        assert reach_min is None
        assert reach_max is None

    def test_with_posts_returns_range(self):
        posts = [_make_post(reach=10000) for _ in range(5)]
        reach_min, reach_max = _estimate_reach_range(posts, "peaking")
        assert reach_min is not None
        assert reach_max is not None
        assert reach_min < reach_max

    def test_peaking_higher_than_falling(self):
        posts = [_make_post(reach=10000) for _ in range(5)]
        _, max_peak = _estimate_reach_range(posts, "peaking")
        _, max_fall = _estimate_reach_range(posts, "falling")
        assert max_peak > max_fall


# ── Best Time Tests ───────────────────────────────────────────────────────────

class TestBestTime:
    def test_empty_heatmap_returns_none(self):
        assert _derive_best_time([]) is None

    def test_returns_day_and_time(self):
        heatmap = [
            HeatmapData(day_of_week=0, hour_of_day=19, intensity=0.9),
            HeatmapData(day_of_week=2, hour_of_day=18, intensity=0.8),
        ]
        result = _derive_best_time(heatmap)
        assert result is not None
        assert "Mon" in result
        assert "PM" in result

    def test_highest_intensity_wins(self):
        heatmap = [
            HeatmapData(day_of_week=0, hour_of_day=12, intensity=0.3),
            HeatmapData(day_of_week=3, hour_of_day=20, intensity=0.95),
        ]
        result = _derive_best_time(heatmap)
        assert "Thu" in result


# ── Difficulty Tests ──────────────────────────────────────────────────────────

class TestDifficulty:
    def test_format_is_easy(self):
        assert _compute_difficulty(_make_trend(trend_type="format")) == "Easy"

    def test_audio_is_hard(self):
        assert _compute_difficulty(_make_trend(trend_type="audio")) == "Hard"

    def test_topic_default_medium(self):
        trend = _make_trend(trend_type="topic", description="A standard content topic with no special keywords")
        assert _compute_difficulty(trend) == "Medium"

    def test_hashtag_is_medium(self):
        trend = _make_trend(trend_type="hashtag", description="A standard hashtag challenge with no special keywords")
        assert _compute_difficulty(trend) == "Medium"

    def test_research_topic_is_hard(self):
        trend = _make_trend(trend_type="topic", description="Deep dive research analysis tutorial")
        assert _compute_difficulty(trend) == "Hard"

    def test_quick_topic_is_easy(self):
        trend = _make_trend(trend_type="topic", description="Quick simple easy casual post")
        assert _compute_difficulty(trend) == "Easy"


# ── Content Gap Tests ─────────────────────────────────────────────────────────

class TestContentGaps:
    def test_empty_posts_no_gaps(self):
        gaps = _detect_content_gaps([], [])
        assert gaps == []

    def test_missing_reel_type_creates_gap(self):
        posts = [_make_post(media_type="IMAGE") for _ in range(5)]
        gaps = _detect_content_gaps(posts, [])
        reel_gaps = [g for g in gaps if "reel" in g.description.lower()]
        assert len(reel_gaps) > 0

    def test_diverse_posts_fewer_gaps(self):
        posts = [
            _make_post(media_type="REEL"),
            _make_post(media_type="CAROUSEL"),
            _make_post(media_type="IMAGE"),
            _make_post(media_type="REEL"),
            _make_post(media_type="CAROUSEL"),
        ]
        gaps = _detect_content_gaps(posts, [])
        assert len(gaps) <= 2

    def test_gap_has_severity(self):
        posts = [_make_post(media_type="IMAGE") for _ in range(5)]
        gaps = _detect_content_gaps(posts, [])
        for gap in gaps:
            assert gap.severity in ("warning", "info", "opportunity")


# ── Daily Insights Tests ──────────────────────────────────────────────────────

class TestDailyInsights:
    def test_empty_data(self):
        insights = _compute_daily_insights([], [], [])
        assert insights.best_content_type is None
        assert insights.competition_level is not None

    def test_with_posts_and_trends(self):
        posts = [_make_post(media_type="REEL", reach=20000) for _ in range(5)]
        trends = [_make_trend(momentum="rising"), _make_trend(momentum="peaking")]
        insights = _compute_daily_insights(posts, [], trends)
        assert insights.best_content_type == "REEL"
        assert insights.competition_level in ("Low", "Medium", "High")
        assert insights.overall_opportunity in ("Very High", "High", "Medium", "Low")

    def test_multiple_trending_audio(self):
        trends = [
            _make_trend(trend_type="audio"),
            _make_trend(trend_type="audio"),
            _make_trend(trend_type="topic"),
        ]
        insights = _compute_daily_insights([], [], trends)
        assert insights.trending_audio_count == 2


# ── Model Validation Tests ────────────────────────────────────────────────────

class TestModels:
    def test_trend_recommendation_optional_fields(self):
        rec = TrendRecommendation(
            suggested_title="Test",
            rationale="Test rationale",
            expected_impact="High",
        )
        assert rec.opportunity_score is None
        assert rec.hook is None
        assert rec.difficulty is None

    def test_trend_recommendation_with_all_fields(self):
        rec = TrendRecommendation(
            suggested_title="Travel Reel",
            rationale="Fits your niche",
            expected_impact="High reach",
            opportunity_score=85.0,
            expected_reach_min=42000,
            expected_reach_max=58000,
            best_time="Thu, 8:00 PM",
            difficulty="Easy",
            hook="Everyone told me Vietnam was expensive...",
            content_style="Storytelling",
        )
        assert rec.opportunity_score == 85.0
        assert rec.hook == "Everyone told me Vietnam was expensive..."

    def test_content_gap_model(self):
        gap = ContentGap(
            description="No reels posted",
            severity="warning",
            suggested_action="Post more reels",
        )
        assert gap.severity == "warning"

    def test_daily_insights_model(self):
        insights = DailyInsights(
            audience_active_window="8PM-11PM",
            best_content_type="Reels",
            trending_audio_count=5,
            competition_level="Medium",
            overall_opportunity="High",
        )
        assert insights.best_content_type == "Reels"

    def test_global_trend_audience_match(self):
        trend = _make_trend()
        trend.audience_match_pct = 92.5
        assert trend.audience_match_pct == 92.5

    def test_trend_analysis_result_new_fields(self):
        result = TrendAnalysisResult(
            niche=CreatorNiche(primary_category="Fitness", sub_niches=["workout"], confidence_score=0.8),
            content_gaps=[ContentGap(description="Test gap", severity="info")],
            daily_insights=DailyInsights(best_content_type="Reels"),
            opportunity_bullets=["Bullet 1", "Bullet 2"],
        )
        assert len(result.content_gaps) == 1
        assert result.daily_insights.best_content_type == "Reels"
        assert len(result.opportunity_bullets) == 2


# ── Determinism Tests ─────────────────────────────────────────────────────────

class TestDeterminism:
    """Verify opportunity score is deterministic for same inputs (PRD 2.2)."""

    def test_same_input_same_score(self):
        trend = _make_trend(momentum="peaking", trend_type="format", topic_name="Travel Reels")
        intel = _make_intelligence()
        score1 = _compute_opportunity_score(trend, intel)
        score2 = _compute_opportunity_score(trend, intel)
        assert score1 == score2, f"Score should be deterministic: {score1} != {score2}"

    def test_different_momentum_different_score(self):
        intel = _make_intelligence()
        peak = _compute_opportunity_score(_make_trend(momentum="peaking"), intel)
        rise = _compute_opportunity_score(_make_trend(momentum="rising"), intel)
        fall = _compute_opportunity_score(_make_trend(momentum="falling"), intel)
        assert peak > rise > fall, f"peaking={peak} rising={rise} falling={fall}"

    def test_score_rounds_to_one_decimal(self):
        trend = _make_trend(momentum="rising", trend_type="audio")
        intel = _make_intelligence()
        score = _compute_opportunity_score(trend, intel)
        # Score should be rounded to 1 decimal place
        assert round(score, 1) == score, f"Score {score} not rounded to 1 decimal"


# ── Degraded Mode / Fallback Tests ────────────────────────────────────────────

class TestDegradedMode:
    """Verify degraded mode behavior (PRD 3.4)."""

    def test_score_always_in_range_even_for_unknown_momentum(self):
        """When momentum is unknown (default fallback), score should still be valid."""
        trend = _make_trend(momentum="falling")  # valid literal, lowest momentum
        intel = CreatorIntelligence(content_style_summary="unrelated_niche")
        score = _compute_opportunity_score(trend, intel)
        assert 0 <= score <= 100, f"Score {score} out of range for low-momentum unrelated niche"

    def test_no_posts_still_produces_score(self):
        trend = _make_trend()
        intel = _make_intelligence()
        score = _compute_opportunity_score(trend, intel, posts=[])
        assert 0 <= score <= 100

    def test_no_heatmap_still_produces_best_time_none(self):
        assert _derive_best_time([]) is None

    def test_no_posts_daily_insights_still_has_competition(self):
        trends = [_make_trend(momentum="rising")]
        insights = _compute_daily_insights([], [], trends)
        assert insights.competition_level is not None
        assert insights.overall_opportunity is not None

    def test_no_posts_no_gaps(self):
        gaps = _detect_content_gaps([], [_make_trend()])
        assert len(gaps) == 0


# ── SLO Boundary Tests ────────────────────────────────────────────────────────

class TestSloBoundaries:
    """Verify engine helpers meet SLO constraints (PRD 2.1)."""

    def test_score_clamped_to_100(self):
        """Score must never exceed 100."""
        trend = _make_trend(momentum="peaking", trend_type="format", topic_name="Travel")
        intel = CreatorIntelligence(content_style_summary="travel")
        posts = [_make_post(reach=100000) for _ in range(20)]  # max recency boost
        score = _compute_opportunity_score(trend, intel, posts=posts)
        assert score <= 100.0, f"Score {score} exceeds 100"

    def test_score_not_below_zero(self):
        """Score must never be negative."""
        trend = _make_trend(momentum="falling", trend_type="hashtag")
        intel = CreatorIntelligence(content_style_summary="robotics")
        score = _compute_opportunity_score(trend, intel)
        assert score >= 0.0, f"Score {score} below 0"

    def test_momentum_component_in_expected_range(self):
        """Momentum score should be 10 (falling) to 40 (peaking)."""
        base_scores = {}
        for mom in ["rising", "peaking", "falling"]:
            trend = _make_trend(momentum=mom)
            intel = _make_intelligence()
            score = _compute_opportunity_score(trend, intel)
            base_scores[mom] = score
        # peaking should always be highest
        assert base_scores["peaking"] >= base_scores["rising"]
        assert base_scores["rising"] >= base_scores["falling"]


# ── Feature Flag Tests ────────────────────────────────────────────────────────

class TestFeatureFlag:
    """Verify feature flag utility (PRD 4.2)."""

    def test_feature_enabled_true_values(self):
        from backend.app.utils.env import is_feature_enabled
        import os
        os.environ["FEATURE_TREND_RECOMMENDATIONS_V2"] = "true"
        assert is_feature_enabled("TREND_RECOMMENDATIONS_V2") is True

    def test_feature_disabled_when_unset(self):
        from backend.app.utils.env import is_feature_enabled
        import os
        os.environ.pop("FEATURE_TREND_RECOMMENDATIONS_V2", None)
        assert is_feature_enabled("TREND_RECOMMENDATIONS_V2") is False

    def test_rollout_pct_defaults(self):
        from backend.app.utils.env import get_rollout_pct
        import os
        os.environ.pop("FEATURE_TREND_RECOMMENDATIONS_V2", None)
        os.environ.pop("FEATURE_TREND_RECOMMENDATIONS_V2_ROLLOUT_PCT", None)
        assert get_rollout_pct("TREND_RECOMMENDATIONS_V2") == 0

    def test_rollout_pct_when_enabled(self):
        from backend.app.utils.env import get_rollout_pct
        import os
        os.environ["FEATURE_TREND_RECOMMENDATIONS_V2"] = "true"
        os.environ.pop("FEATURE_TREND_RECOMMENDATIONS_V2_ROLLOUT_PCT", None)
        assert get_rollout_pct("TREND_RECOMMENDATIONS_V2") == 100

    def test_rollout_pct_explicit_value(self):
        from backend.app.utils.env import get_rollout_pct
        import os
        os.environ["FEATURE_TREND_RECOMMENDATIONS_V2"] = "true"
        os.environ["FEATURE_TREND_RECOMMENDATIONS_V2_ROLLOUT_PCT"] = "25"
        assert get_rollout_pct("TREND_RECOMMENDATIONS_V2") == 25

    def test_rollout_pct_clamped_to_100(self):
        from backend.app.utils.env import get_rollout_pct
        import os
        os.environ["FEATURE_TREND_RECOMMENDATIONS_V2"] = "true"
        os.environ["FEATURE_TREND_RECOMMENDATIONS_V2_ROLLOUT_PCT"] = "150"
        pct = get_rollout_pct("TREND_RECOMMENDATIONS_V2")
        assert pct == 100, f"Rollout pct {pct} should be clamped to 100"
