"""Revenue Optimization Calculator for creator monetization.

Provides dynamic rate recommendations based on performance metrics,
niche benchmarks, and market data.
"""

from __future__ import annotations

from backend.app.domain.account_models import (
    RateBreakdown,
    RateRecommendation,
    RevenueProjections,
)
from backend.app.domain.post_models import SinglePostInsights
from backend.app.utils.logger import logger


# ── Niche Multipliers ────────────────────────────────────────────────────────
# Based on market rate data for Instagram sponsored content

NICHE_MULTIPLIERS: dict[str, float] = {
    "fashion": 1.20,
    "beauty": 1.15,
    "tech": 1.10,
    "fitness": 1.05,
    "lifestyle": 1.00,
    "food": 0.95,
    "travel": 1.08,
    "finance": 1.12,
    "education": 0.90,
    "comedy": 0.92,
    "gaming": 0.88,
    "music": 0.85,
}


def _safe_float(value: object, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if value is None:
        return default
    try:
        result = float(value)
        return result if result == result else default  # NaN check
    except (TypeError, ValueError):
        return default


def _calculate_base_rate(engagement_rate: float) -> float:
    """Calculate base rate from engagement rate.

    Instagram sponsored post rates typically correlate with engagement rate.
    Higher engagement = higher value to brands.
    """
    # Base calculation: $X per 1% engagement rate
    # Industry benchmark: $100-200 per 1% ER for mid-tier creators
    base = engagement_rate * 15000  # $150 per 1% ER (adjustable)
    return round(max(50.0, min(5000.0, base)), 2)  # Floor at $50, ceiling at $5000


def _calculate_follower_multiplier(follower_count: int) -> float:
    """Calculate rate multiplier based on follower count.

    Larger accounts command higher rates but with diminishing returns.
    """
    if follower_count <= 0:
        return 0.5

    # Logarithmic scaling with breakpoints
    if follower_count < 10000:
        return 0.6
    elif follower_count < 50000:
        return 0.8
    elif follower_count < 100000:
        return 1.0
    elif follower_count < 500000:
        return 1.3
    elif follower_count < 1000000:
        return 1.6
    else:
        return 2.0


def _calculate_niche_multiplier(niche: str) -> float:
    """Get niche-specific rate multiplier."""
    niche_lower = (niche or "").lower().strip()
    return NICHE_MULTIPLIERS.get(niche_lower, 1.0)


def _calculate_quality_premium(
    brand_safety_score: float,
    content_quality_score: float,
    save_rate: float,
    share_rate: float,
) -> float:
    """Calculate quality premium multiplier.

    High-quality, brand-safe content commands premium rates.
    """
    premium = 1.0

    # Brand safety bonus (up to 15%)
    if brand_safety_score >= 90:
        premium += 0.15
    elif brand_safety_score >= 70:
        premium += 0.08

    # Content quality bonus (up to 10%)
    if content_quality_score >= 80:
        premium += 0.10
    elif content_quality_score >= 60:
        premium += 0.05

    # Save rate bonus (high save rate indicates valuable content)
    if save_rate >= 0.10:
        premium += 0.10
    elif save_rate >= 0.06:
        premium += 0.05

    # Share rate bonus (virality potential)
    if share_rate >= 0.03:
        premium += 0.08
    elif share_rate >= 0.015:
        premium += 0.04

    return round(min(1.8, premium), 2)  # Cap at 1.8x


def _generate_optimization_tips(
    engagement_rate: float,
    save_rate: float,
    share_rate: float,
    content_quality_score: float,
    brand_safety_score: float,
    niche: str,
) -> list[str]:
    """Generate actionable tips to increase rates."""
    tips = []

    # Engagement-based tips
    if engagement_rate < 0.03:
        tips.append("Increase engagement rate above 3% to unlock higher rates")
    elif engagement_rate >= 0.06:
        tips.append("Your engagement rate is excellent - emphasize this in brand pitches")

    # Save rate tips
    if save_rate < 0.05:
        tips.append("Create more save-worthy content (tutorials, tips, lists) to increase rates")
    elif save_rate >= 0.08:
        tips.append("Your save rate is strong - highlight this as proof of content value")

    # Share rate tips
    if share_rate < 0.01:
        tips.append("Focus on shareable content (relatable, emotional, useful) to boost rates")

    # Quality tips
    if content_quality_score < 60:
        tips.append("Improve visual quality and caption hooks to justify higher rates")

    # Brand safety tips
    if brand_safety_score < 70:
        tips.append("Address brand safety concerns to access premium brand partnerships")

    # Niche-specific tips
    niche_lower = (niche or "").lower()
    if niche_lower in ("fashion", "beauty"):
        tips.append("Fashion/beauty creators command premium rates - showcase brand partnerships")
    elif niche_lower in ("tech", "finance"):
        tips.append("Tech/finance niches have high CPMs - emphasize expertise and trust")

    # General optimization tips
    tips.append("Negotiate 3-month packages for 15-20% rate premium")
    tips.append("Bundle Reels + Stories for higher total deal value")

    return tips[:5]  # Return top 5 tips


def _calculate_revenue_projections(recommended_rate: float) -> RevenueProjections:
    """Calculate revenue projections based on deal volume."""
    # Apply ±20% range
    rate_min = recommended_rate * 0.8
    rate_max = recommended_rate * 1.2

    return RevenueProjections(
        monthly_deals_4=(round(rate_min * 4, 2), round(rate_max * 4, 2)),
        monthly_deals_8=(round(rate_min * 8, 2), round(rate_max * 8, 2)),
        annual_potential=(round(rate_min * 48, 2), round(rate_max * 96, 2)),
    )


def calculate_rate_recommendation(
    engagement_rate: float,
    follower_count: int,
    niche: str,
    brand_safety_score: float,
    content_quality_score: float,
    save_rate: float,
    share_rate: float,
) -> RateRecommendation:
    """Calculate comprehensive rate recommendation.

    Args:
        engagement_rate: Average engagement rate (0.0-1.0)
        follower_count: Current follower count
        niche: Primary content niche
        brand_safety_score: Brand safety score (0-100)
        content_quality_score: Content quality score (0-100)
        save_rate: Average save rate (0.0-1.0)
        share_rate: Average share rate (0.0-1.0)

    Returns:
        RateRecommendation with full breakdown and tips
    """
    # Calculate components
    base_rate = _calculate_base_rate(engagement_rate)
    follower_mult = _calculate_follower_multiplier(follower_count)
    niche_mult = _calculate_niche_multiplier(niche)
    quality_premium = _calculate_quality_premium(
        brand_safety_score, content_quality_score, save_rate, share_rate
    )

    # Calculate final recommended rate
    engagement_component = base_rate * 0.4  # 40% weight
    follower_component = base_rate * follower_mult * 0.3  # 30% weight
    niche_component = base_rate * niche_mult * 0.15  # 15% weight
    quality_component = base_rate * quality_premium * 0.15  # 15% weight

    recommended_rate = round(
        engagement_component + follower_component + niche_component + quality_component,
        2,
    )

    # Calculate range
    rate_min = round(recommended_rate * 0.8, 2)
    rate_max = round(recommended_rate * 1.2, 2)

    # Calculate CPM (cost per 1000 impressions)
    # Estimate impressions from engagement rate and followers
    estimated_impressions = follower_count * 0.3  # Assume 30% see sponsored content
    cpm = round((recommended_rate / estimated_impressions * 1000), 2) if estimated_impressions > 0 else 0

    # Build breakdown
    breakdown = RateBreakdown(
        base_rate=base_rate,
        engagement_component=engagement_component,
        follower_component=follower_component,
        niche_component=niche_component,
        quality_premium=quality_premium,
    )

    # Generate tips
    tips = _generate_optimization_tips(
        engagement_rate, save_rate, share_rate,
        content_quality_score, brand_safety_score, niche,
    )

    # Calculate projections
    projections = _calculate_revenue_projections(recommended_rate)

    return RateRecommendation(
        base_rate=base_rate,
        recommended_rate=recommended_rate,
        rate_min=rate_min,
        rate_max=rate_max,
        cpm_estimate=cpm,
        breakdown=breakdown,
        optimization_tips=tips,
        revenue_projections=projections,
    )


def calculate_rate_from_posts(
    posts: list[SinglePostInsights],
    follower_count: int,
    niche: str,
    brand_safety_score: float = 80.0,
    content_quality_score: float = 70.0,
) -> RateRecommendation:
    """Calculate rate recommendation from post data.

    Convenience function that extracts metrics from posts.
    """
    if not posts:
        logger.warning("[RevenueCalculator] No posts provided, using defaults")
        return calculate_rate_recommendation(
            engagement_rate=0.03,
            follower_count=follower_count,
            niche=niche,
            brand_safety_score=brand_safety_score,
            content_quality_score=content_quality_score,
            save_rate=0.05,
            share_rate=0.01,
        )

    # Extract metrics from posts
    engagement_rates = []
    save_rates = []
    share_rates = []

    for post in posts:
        er = _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
        if er > 0:
            engagement_rates.append(er)

        # Calculate save and share rates from raw metrics
        likes = _safe_float(getattr(post.core_metrics, "likes", None))
        saves = _safe_float(getattr(post.core_metrics, "saves", None))
        shares = _safe_float(getattr(post.core_metrics, "shares", None))
        reach = _safe_float(getattr(post.core_metrics, "reach", None))

        if reach > 0:
            if saves > 0:
                save_rates.append(saves / reach)
            if shares > 0:
                share_rates.append(shares / reach)

    # Calculate averages
    avg_er = sum(engagement_rates) / len(engagement_rates) if engagement_rates else 0.03
    avg_save_rate = sum(save_rates) / len(save_rates) if save_rates else 0.05
    avg_share_rate = sum(share_rates) / len(share_rates) if share_rates else 0.01

    return calculate_rate_recommendation(
        engagement_rate=avg_er,
        follower_count=follower_count,
        niche=niche,
        brand_safety_score=brand_safety_score,
        content_quality_score=content_quality_score,
        save_rate=avg_save_rate,
        share_rate=avg_share_rate,
    )
