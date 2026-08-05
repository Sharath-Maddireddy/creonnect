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
    _classify_angle_type,
    _classify_creator_level,
    _classify_format_family,
    _compute_opportunity_score,
    _compute_execution_effort,
    _compute_daily_insights,
    _derive_best_time,
    _detect_content_gaps,
    _estimate_reach_range,
    _parse_opportunity_bullets,
)
from backend.app.services.trend_cache import TrendAnalysisCache
from backend.app.services.creator_trend_service import _build_heatmap_from_posts
from backend.app.services.draft_history_service import _coerce_history_post
from backend.app.analytics.global_trend_engine import fetch_global_trends


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

    def test_niche_fit_boosts_score(self):
        trend = _make_trend(description="Travel destinations and hotels")
        intel = _make_intelligence(style="Creates travel content around destinations")
        score = _compute_opportunity_score(trend, intel)
        assert score >= 60

    def test_score_always_in_range(self):
        for momentum in ["rising", "peaking", "falling"]:
            for tt in ["topic", "format", "hashtag"]:
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


# ── Execution Effort Tests ───────────────────────────────────────────────────

class TestExecutionEffort:
    def test_format_is_quick(self):
        effort, reason = _compute_execution_effort(_make_trend(trend_type="format"))
        assert effort == "Quick"
        assert reason

    def test_topic_default_is_planned(self):
        trend = _make_trend(trend_type="topic", description="A standard content topic with no special keywords")
        effort, _ = _compute_execution_effort(trend)
        assert effort == "Planned"

    def test_hashtag_is_quick(self):
        trend = _make_trend(trend_type="hashtag", description="A standard hashtag challenge with no special keywords")
        effort, _ = _compute_execution_effort(trend)
        assert effort == "Quick"

    def test_research_topic_is_production_heavy(self):
        trend = _make_trend(trend_type="topic", description="Deep dive research analysis tutorial")
        effort, _ = _compute_execution_effort(trend)
        assert effort == "Production-heavy"

    def test_quick_topic_is_quick(self):
        trend = _make_trend(trend_type="topic", description="Quick simple easy casual post")
        effort, _ = _compute_execution_effort(trend)
        assert effort == "Quick"


class TestRecommendationClassification:
    def test_format_family_detects_carousel(self):
        trend = _make_trend(trend_type="topic", description="A swipe carousel breakdown")
        rec = TrendRecommendation(
            suggested_title="Carousel breakdown of the trend",
            rationale="Use a slide-by-slide explanation",
            expected_impact="Higher saves",
            content_style="Educational",
        )
        assert _classify_format_family(trend, rec) == "carousel"

    def test_format_family_detects_photo(self):
        trend = _make_trend(trend_type="topic", description="Static lookbook photo trend")
        rec = TrendRecommendation(
            suggested_title="Photo lookbook",
            rationale="A single image look can still win here",
            expected_impact="Better discovery",
        )
        assert _classify_format_family(trend, rec) == "photo"

    def test_angle_type_detects_personal_story(self):
        trend = _make_trend(description="POV lifestyle story format")
        rec = TrendRecommendation(
            suggested_title="My honest experience trying this trend",
            rationale="A personal journey angle fits your niche",
            expected_impact="Stronger connection",
            content_style="POV/Lifestyle",
        )
        assert _classify_angle_type(trend, rec) == "personal_story"

    def test_angle_type_detects_brand_friendly(self):
        trend = _make_trend(description="Shopping comparison trend")
        rec = TrendRecommendation(
            suggested_title="Best products in this trend",
            rationale="A storefront comparison makes this brand-friendly",
            expected_impact="Better conversion",
        )
        assert _classify_angle_type(trend, rec) == "brand_friendly"

    def test_creator_level_maps_easy_to_beginner(self):
        assert _classify_creator_level("Easy", _make_trend(), None) == "beginner"

    def test_creator_level_maps_hard_to_advanced(self):
        assert _classify_creator_level("Hard", _make_trend(), None) == "advanced"


# ── Content Gap Tests ─────────────────────────────────────────────────────────

class TestContentGaps:
    def test_empty_posts_no_gaps(self):
        gaps = _detect_content_gaps([], [])
        assert gaps == []

    def test_insufficient_recent_posts_produces_no_opportunities(self):
        gaps = _detect_content_gaps([_make_post(media_type="IMAGE") for _ in range(4)], [])
        assert gaps == []

    def test_missing_reel_type_creates_gap(self):
        posts = [_make_post(media_type="IMAGE") for _ in range(5)]
        gaps = _detect_content_gaps(posts, [])
        reel_gaps = [g for g in gaps if "reel" in g.description.lower()]
        assert reel_gaps == []

    def test_relevant_missing_format_has_evidence_and_priority(self):
        posts = [_make_post(media_type="IMAGE") for _ in range(5)]
        gaps = _detect_content_gaps(posts, [_make_trend(trend_type="format")])
        reel_gaps = [gap for gap in gaps if "reel" in gap.description.lower()]
        assert len(reel_gaps) == 1
        assert reel_gaps[0].evidence
        assert reel_gaps[0].priority_score is not None
        assert gaps == sorted(gaps, key=lambda gap: gap.priority_score or 0, reverse=True)

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
            format_family="reel",
            angle_type="personal_story",
            creator_level="beginner",
            is_trending=True,
        )
        assert rec.opportunity_score == 85.0
        assert rec.hook == "Everyone told me Vietnam was expensive..."
        assert rec.format_family == "reel"
        assert rec.angle_type == "personal_story"
        assert rec.creator_level == "beginner"
        assert rec.is_trending is True

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
        trend = _make_trend(momentum="rising", trend_type="format")
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


class TestOpportunityBulletsParsing:
    def test_structured_parser_ignores_keyword_in_rationale_text(self):
        raw = """
recommendations
  -
    suggested_title: Travel idea
    rationale: Mention the word opportunity_bullets in prose without breaking parsing
    expected_impact: Higher reach
opportunity_bullets
  - Travel reels are underutilized
  - Storytelling hooks outperform static posts
"""
        bullets = _parse_opportunity_bullets(raw)
        assert bullets == [
            "Travel reels are underutilized",
            "Storytelling hooks outperform static posts",
        ]


class TestTrendCache:
    def test_invalidate_uses_versioned_key_pattern(self, monkeypatch):
        seen_patterns: list[str] = []

        class FakeRedis:
            def scan_iter(self, match):
                seen_patterns.append(match)
                return []

        monkeypatch.setattr("backend.app.services.trend_cache.get_redis", lambda: FakeRedis())
        TrendAnalysisCache.invalidate("acct_123")
        assert seen_patterns == ["trend_cache:v3:acct_123:*"]

    def test_cache_key_changes_when_post_content_changes(self):
        first = SinglePostInsights(media_id="post-1", account_id="acct", caption_text="first caption")
        second = SinglePostInsights(media_id="post-1", account_id="acct", caption_text="updated caption")

        assert TrendAnalysisCache.get_cache_key("acct", [first]) != TrendAnalysisCache.get_cache_key("acct", [second])


class TestHeatmapEvidence:
    def test_missing_engagement_rate_does_not_create_a_timing_signal(self):
        post = SinglePostInsights(
            media_id="post-1",
            account_id="acct",
            published_at=datetime(2024, 6, 1, 19, 30),
        )

        assert _build_heatmap_from_posts([post]) == []

    def test_history_does_not_promote_predicted_er_to_observed_engagement(self):
        post = _coerce_history_post(
            {
                "post_id": "post-1",
                "scores": {"predicted_er": 0.09},
            },
            account_id="acct",
            follower_count=1_000,
        )

        assert post is not None
        assert post.derived_metrics.engagement_rate is None


@pytest.mark.asyncio
async def test_global_trends_require_live_signals(monkeypatch):
    async def _no_signals(*_args, **_kwargs):
        return []

    class UnexpectedLLM:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("LLM should not run without live evidence")

    monkeypatch.setattr("backend.app.analytics.global_trend_engine.fetch_live_trend_signals", _no_signals)
    monkeypatch.setattr("backend.app.analytics.global_trend_engine.LLMClient", UnexpectedLLM)

    result = await fetch_global_trends(
        CreatorNiche(primary_category="Fitness", sub_niches=["workouts"], confidence_score=0.8)
    )

    assert result == []


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
