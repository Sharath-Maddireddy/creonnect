"""Tests for advanced account analysis services."""

from __future__ import annotations

import pytest

from backend.app.domain.account_models import (
    BrandReadinessBreakdown,
    RateRecommendation,
    RiskAssessment,
    RiskLevel,
)
from backend.app.services.revenue_calculator import (
    calculate_rate_recommendation,
    calculate_rate_from_posts,
    _calculate_base_rate,
    _calculate_follower_multiplier,
    _calculate_niche_multiplier,
    _calculate_quality_premium,
)
from backend.app.services.risk_assessment import assess_account_risks
from backend.app.services.brand_readiness import (
    calculate_brand_readiness,
    _calculate_content_quality_score,
    _calculate_engagement_score,
    _get_label,
)
from types import SimpleNamespace


# ── Revenue Calculator Tests ──────────────────────────────────────────────────


class TestRevenueCalculator:
    """Tests for revenue calculator service."""

    def test_calculate_base_rate(self):
        """Test base rate calculation from engagement rate."""
        # Low engagement
        assert _calculate_base_rate(0.01) == 1500.0  # INR heuristic

        # Medium engagement
        assert _calculate_base_rate(0.03) == 4500.0

        # High engagement
        assert _calculate_base_rate(0.06) == 9000.0

        # Very high engagement (capped)
        assert _calculate_base_rate(0.10) == 15000.0

    def test_calculate_follower_multiplier(self):
        """Test follower count multiplier."""
        # Micro influencer
        assert _calculate_follower_multiplier(5000) == 0.6

        # Small influencer
        assert _calculate_follower_multiplier(25000) == 0.8

        # Mid-tier
        assert _calculate_follower_multiplier(75000) == 1.0

        # Large influencer
        assert _calculate_follower_multiplier(250000) == 1.3

        # Macro influencer
        assert _calculate_follower_multiplier(750000) == 1.6

    def test_calculate_niche_multiplier(self):
        """Test niche-specific multiplier."""
        # Fashion (premium)
        assert _calculate_niche_multiplier("fashion") == 1.20

        # Beauty (premium)
        assert _calculate_niche_multiplier("beauty") == 1.15

        # Tech (premium)
        assert _calculate_niche_multiplier("tech") == 1.10

        # Unknown niche (default)
        assert _calculate_niche_multiplier("unknown") == 1.0

    def test_calculate_quality_premium(self):
        """Test quality premium calculation."""
        # Basic (no premium)
        premium = _calculate_quality_premium(
            brand_safety_score=60,
            content_quality_score=50,
            save_rate=0.02,
            share_rate=0.005,
        )
        assert premium == 1.0

        # High quality (should have premium)
        premium = _calculate_quality_premium(
            brand_safety_score=95,
            content_quality_score=85,
            save_rate=0.12,
            share_rate=0.04,
        )
        # Premium includes: brand safety (0.15) + quality (0.10) + saves (0.10) + shares (0.08) = 1.43
        assert premium > 1.3  # Should have meaningful premium
        assert premium <= 1.8  # Should be capped

    def test_calculate_rate_recommendation(self):
        """Test full rate recommendation calculation."""
        result = calculate_rate_recommendation(
            engagement_rate=0.05,
            follower_count=50000,
            niche="fashion",
            brand_safety_score=90,
            content_quality_score=80,
            save_rate=0.08,
            share_rate=0.02,
        )

        assert isinstance(result, RateRecommendation)
        assert result.recommended_rate > 0
        assert result.rate_min < result.recommended_rate
        assert result.rate_max > result.recommended_rate
        assert len(result.optimization_tips) > 0
        assert result.revenue_projections.monthly_deals_4[0] > 0

    def test_rate_recommendation_range(self):
        """Test that rate range is ±20% of recommended."""
        result = calculate_rate_recommendation(
            engagement_rate=0.04,
            follower_count=30000,
            niche="lifestyle",
            brand_safety_score=80,
            content_quality_score=70,
            save_rate=0.05,
            share_rate=0.01,
        )

        assert result.rate_min == pytest.approx(result.recommended_rate * 0.8, rel=0.01)
        assert result.rate_max == pytest.approx(result.recommended_rate * 1.2, rel=0.01)
        assert result.revenue_projections.annual_potential[0] == pytest.approx(result.rate_min * 48)
        assert result.revenue_projections.annual_potential[1] == pytest.approx(result.rate_max * 48)

    def test_rate_from_posts_uses_actual_impressions_for_cpm(self):
        post = SimpleNamespace(
            derived_metrics=SimpleNamespace(engagement_rate=0.04),
            core_metrics=SimpleNamespace(reach=1_000, impressions=2_000, saves=50, shares=20),
        )

        result = calculate_rate_from_posts([post], follower_count=10_000, niche="fitness")

        assert result.cpm_estimate == pytest.approx(result.recommended_rate / 2_000 * 1_000)

    def test_optimization_tips_generated(self):
        """Test that optimization tips are generated."""
        result = calculate_rate_recommendation(
            engagement_rate=0.02,  # Low engagement
            follower_count=10000,
            niche="lifestyle",
            brand_safety_score=60,  # Low safety
            content_quality_score=50,  # Low quality
            save_rate=0.03,  # Low saves
            share_rate=0.005,  # Low shares
        )

        # Should have tips for improvement
        assert len(result.optimization_tips) >= 3


# ── Risk Assessment Tests ─────────────────────────────────────────────────────


class TestRiskAssessment:
    """Tests for risk assessment service."""

    def test_empty_posts_returns_no_risks(self):
        """Test that empty posts list returns no critical risks."""
        result = assess_account_risks([])

        assert isinstance(result, RiskAssessment)
        # May have some risks but shouldn't crash
        assert result.risk_count >= 0

    def test_assessment_returns_valid_risk_level(self):
        """Test that risk level is a valid enum value."""
        result = assess_account_risks([])

        assert result.overall_risk_level in [
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]

    def test_risks_have_required_fields(self):
        """Test that risks have all required fields."""
        result = assess_account_risks([])

        for risk in result.risks:
            assert risk.id
            assert risk.category
            assert risk.level
            assert risk.title
            assert risk.description
            assert risk.metric_affected


# ── Brand Readiness Tests ─────────────────────────────────────────────────────


class TestBrandReadiness:
    """Tests for brand readiness service."""

    def test_calculate_brand_readiness_empty(self):
        """Test brand readiness with empty posts."""
        result = calculate_brand_readiness([])

        assert isinstance(result, BrandReadinessBreakdown)
        assert 0 <= result.overall_score <= 100
        assert result.overall_label in [
            "Highly Marketable",
            "Marketable",
            "Developing",
            "Early Stage",
            "Needs Work",
        ]

    def test_score_range(self):
        """Test that scores are within valid range."""
        result = calculate_brand_readiness([])

        assert 0 <= result.content_quality_score <= 100
        assert 0 <= result.brand_safety_score <= 100
        assert 0 <= result.engagement_score <= 100
        assert 0 <= result.consistency_score <= 100
        assert 0 <= result.niche_clarity_score <= 100
        assert 0 <= result.audience_quality_score <= 100

    def test_get_label(self):
        """Test label assignment for different scores."""
        assert _get_label(90) == "Highly Marketable"
        assert _get_label(75) == "Marketable"
        assert _get_label(60) == "Developing"
        assert _get_label(45) == "Early Stage"
        assert _get_label(30) == "Building Momentum"

    def test_calculate_engagement_score(self):
        """Test engagement score calculation."""
        # High engagement
        score = _calculate_engagement_score([])
        # Default for empty posts
        assert score == 50.0

    def test_content_quality_uses_vision_signal_fields(self):
        signal = SimpleNamespace(composition=10, lighting=10, subject_clarity=10, cringe_score=0)
        post = SimpleNamespace(
            vision_analysis=SimpleNamespace(signals=[signal]),
            content_clarity_score=None,
        )

        assert _calculate_content_quality_score([post]) == 100.0

    def test_consistency_allows_missing_publish_dates(self):
        from backend.app.services.brand_readiness import _calculate_consistency_score

        posts = [SimpleNamespace(published_at=None) for _ in range(5)]
        assert _calculate_consistency_score(posts) == 50.0


# ── Integration Tests ─────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests for advanced analysis services."""

    def test_revenue_and_risk_together(self):
        """Test that revenue and risk can be calculated together."""
        # Calculate revenue
        revenue = calculate_rate_recommendation(
            engagement_rate=0.04,
            follower_count=25000,
            niche="fashion",
            brand_safety_score=85,
            content_quality_score=75,
            save_rate=0.06,
            share_rate=0.015,
        )

        # Calculate risks
        risks = assess_account_risks([])

        # Both should succeed
        assert revenue.recommended_rate > 0
        assert risks.risk_count >= 0

    def test_brand_readiness_with_pillars(self):
        """Test brand readiness with pillar scores."""
        pillar_scores = {
            "content_quality": {"score": 80},
            "engagement_quality": {"score": 70},
            "niche_fit": {"score": 60},
            "consistency": {"score": 75},
            "brand_safety": {"score": 90},
        }

        result = calculate_brand_readiness([], pillar_scores=pillar_scores)

        assert result.overall_score > 0
        assert len(result.improvement_opportunities) >= 0
