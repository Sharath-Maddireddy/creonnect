"""Enhanced Brand Readiness Score with detailed breakdown.

Provides component scores, improvement opportunities, and market positioning
for brand partnership readiness assessment.
"""

from __future__ import annotations

from backend.app.domain.account_models import (
    BrandReadinessBreakdown,
    ImprovementOpportunity,
)
from backend.app.domain.post_models import SinglePostInsights
from backend.app.utils.logger import logger


def _safe_float(value: object, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if value is None:
        return default
    try:
        result = float(value)
        return result if result == result else default
    except (TypeError, ValueError):
        return default


def _calculate_content_quality_score(posts: list[SinglePostInsights]) -> float:
    """Calculate content quality score from post analysis data."""
    if not posts:
        return 50.0  # Default neutral score

    scores = []
    for post in posts:
        post_score = 50.0  # Base score

        # Check vision analysis
        if post.vision_analysis and post.vision_analysis.signals:
            first_signal = post.vision_analysis.signals[0]

            # Composition quality
            composition = _safe_float(getattr(first_signal, "composition_score", None))
            if composition > 0:
                post_score += (composition / 10) * 2  # Up to +20

            # Lighting quality
            lighting = _safe_float(getattr(first_signal, "lighting_score", None))
            if lighting > 0:
                post_score += (lighting / 10) * 1.5  # Up to +15

            # Subject clarity
            clarity = _safe_float(getattr(first_signal, "subject_clarity_score", None))
            if clarity > 0:
                post_score += (clarity / 10) * 1.5  # Up to +15

            # Penalize for cringe
            cringe = _safe_float(getattr(first_signal, "cringe_score", None))
            if cringe > 50:
                post_score -= (cringe - 50) * 0.3  # Up to -15

        # Check content clarity score (S3)
        if post.content_clarity_score:
            clarity_score = _safe_float(getattr(post.content_clarity_score, "total_0_50", None))
            if clarity_score > 0:
                post_score += (clarity_score / 50) * 10  # Up to +10

        scores.append(max(0, min(100, post_score)))

    return round(sum(scores) / len(scores), 1) if scores else 50.0


def _calculate_brand_safety_score(posts: list[SinglePostInsights]) -> float:
    """Calculate brand safety score from post safety data."""
    if not posts:
        return 80.0  # Default optimistic score

    scores = []
    for post in posts:
        post_score = 100.0  # Start perfect

        # Check brand safety score
        safety = _safe_float(getattr(post.brand_safety_score, "total_0_50", None))
        if safety > 0:
            post_score = (safety / 50) * 100  # Convert 0-50 to 0-100

        # Penalize for flagged content
        if post.vision_analysis and post.vision_analysis.signals:
            first_signal = post.vision_analysis.signals[0]
            if getattr(first_signal, "adult_content_detected", None) is True:
                post_score -= 30
            if getattr(first_signal, "is_cringe", None) is True:
                post_score -= 15

        scores.append(max(0, min(100, post_score)))

    return round(sum(scores) / len(scores), 1) if scores else 80.0


def _calculate_engagement_score(posts: list[SinglePostInsights]) -> float:
    """Calculate engagement score from post performance."""
    if not posts:
        return 50.0

    engagement_rates = []
    for post in posts:
        er = _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
        if er > 0:
            engagement_rates.append(er)

    if not engagement_rates:
        return 50.0

    avg_er = sum(engagement_rates) / len(engagement_rates)

    # Convert engagement rate to 0-100 score
    # Industry benchmarks: <1% = poor, 1-3% = average, 3-5% = good, 5%+ = excellent
    if avg_er >= 0.06:
        return 90.0
    elif avg_er >= 0.04:
        return 80.0
    elif avg_er >= 0.03:
        return 70.0
    elif avg_er >= 0.02:
        return 60.0
    elif avg_er >= 0.01:
        return 50.0
    else:
        return 40.0


def _calculate_consistency_score(posts: list[SinglePostInsights]) -> float:
    """Calculate consistency score from posting patterns."""
    if len(posts) < 5:
        return 50.0

    # Sort posts by date
    sorted_posts = sorted(
        posts,
        key=lambda p: p.published_at or datetime.min,
        reverse=True,
    )

    # Check posting frequency consistency
    from datetime import datetime
    gaps = []
    for i in range(len(sorted_posts) - 1):
        if sorted_posts[i].published_at and sorted_posts[i + 1].published_at:
            gap = (sorted_posts[i].published_at - sorted_posts[i + 1].published_at).days
            gaps.append(gap)

    if not gaps:
        return 50.0

    # Calculate coefficient of variation for gaps
    import statistics
    try:
        mean_gap = statistics.mean(gaps)
        if mean_gap == 0:
            return 70.0

        std_gap = statistics.stdev(gaps) if len(gaps) > 1 else 0
        cv = std_gap / mean_gap

        # Lower CV = more consistent
        if cv < 0.3:
            return 90.0  # Very consistent
        elif cv < 0.5:
            return 75.0  # Consistent
        elif cv < 0.7:
            return 60.0  # Somewhat consistent
        else:
            return 45.0  # Inconsistent
    except statistics.StatisticsError:
        return 50.0


def _calculate_niche_clarity_score(
    posts: list[SinglePostInsights],
    pillar_scores: dict | None = None,
) -> float:
    """Calculate niche clarity score from content pillars."""
    # If pillar scores provided, use them
    if pillar_scores:
        niche_fit = pillar_scores.get("niche_fit", {})
        score = _safe_float(niche_fit.get("score", 50.0))
        return score

    # Otherwise, estimate from post categories
    if not posts:
        return 50.0

    categories = []
    for post in posts:
        category = (post.post_category or "").strip().lower()
        if category and category not in {"unknown", ""}:
            categories.append(category)

    if not categories:
        return 40.0  # No clear categories = low clarity

    # Calculate category concentration
    from collections import Counter
    category_counts = Counter(categories)
    total = len(categories)

    # Higher concentration = clearer niche
    top_category_pct = category_counts.most_common(1)[0][1] / total if total > 0 else 0

    if top_category_pct >= 0.7:
        return 85.0  # Very clear niche
    elif top_category_pct >= 0.5:
        return 70.0  # Clear niche
    elif top_category_pct >= 0.3:
        return 55.0  # Somewhat clear
    else:
        return 40.0  # Unclear niche


def _calculate_audience_quality_score(posts: list[SinglePostInsights]) -> float:
    """Calculate audience quality score from engagement patterns."""
    if not posts:
        return 60.0

    # Check for authentic engagement signals
    high_quality_signals = 0
    total_posts = len(posts)

    for post in posts:
        likes = _safe_float(getattr(post.core_metrics, "likes", None))
        comments = _safe_float(getattr(post.core_metrics, "comments", None))
        saves = _safe_float(getattr(post.core_metrics, "saves", None))
        shares = _safe_float(getattr(post.core_metrics, "shares", None))

        # High-quality engagement = comments + saves + shares relative to likes
        if likes > 0:
            quality_ratio = (comments + saves + shares) / likes
            if quality_ratio > 0.1:  # More than 10% quality engagement
                high_quality_signals += 1

    quality_pct = high_quality_signals / total_posts if total_posts > 0 else 0

    if quality_pct >= 0.6:
        return 85.0
    elif quality_pct >= 0.4:
        return 70.0
    elif quality_pct >= 0.2:
        return 55.0
    else:
        return 45.0


def _get_label(score: float) -> str:
    """Get human-readable label for score."""
    if score >= 85:
        return "Highly Marketable"
    elif score >= 70:
        return "Marketable"
    elif score >= 55:
        return "Developing"
    elif score >= 40:
        return "Early Stage"
    else:
        return "Needs Work"


def _identify_improvements(
    content_quality: float,
    brand_safety: float,
    engagement: float,
    consistency: float,
    niche_clarity: float,
    audience_quality: float,
) -> list[ImprovementOpportunity]:
    """Identify improvement opportunities based on scores."""
    improvements = []

    # Content Quality
    if content_quality < 70:
        improvements.append(ImprovementOpportunity(
            area="Content Quality",
            current_score=content_quality,
            potential_increase=min(20, 80 - content_quality),
            difficulty="medium",
            estimated_timeframe="2-4 weeks",
            specific_actions=[
                "Improve lighting and composition in photos/videos",
                "Add stronger opening hooks in first 3 seconds",
                "Use consistent visual style and branding",
            ],
        ))

    # Brand Safety
    if brand_safety < 80:
        improvements.append(ImprovementOpportunity(
            area="Brand Safety",
            current_score=brand_safety,
            potential_increase=min(15, 90 - brand_safety),
            difficulty="easy",
            estimated_timeframe="1-2 weeks",
            specific_actions=[
                "Review and remove any flagged content",
                "Avoid controversial topics or language",
                "Focus on family-friendly, positive messaging",
            ],
        ))

    # Engagement
    if engagement < 70:
        improvements.append(ImprovementOpportunity(
            area="Engagement Rate",
            current_score=engagement,
            potential_increase=min(15, 80 - engagement),
            difficulty="medium",
            estimated_timeframe="2-4 weeks",
            specific_actions=[
                "Add clear CTAs (comment, save, share) in captions",
                "Post at optimal times for your audience",
                "Create more save-worthy educational content",
            ],
        ))

    # Consistency
    if consistency < 70:
        improvements.append(ImprovementOpportunity(
            area="Posting Consistency",
            current_score=consistency,
            potential_increase=min(10, 80 - consistency),
            difficulty="easy",
            estimated_timeframe="1-2 weeks",
            specific_actions=[
                "Aim for 4-5 posts per week minimum",
                "Use a content calendar for scheduling",
                "Batch-create content to maintain consistency",
            ],
        ))

    # Niche Clarity
    if niche_clarity < 65:
        improvements.append(ImprovementOpportunity(
            area="Niche Clarity",
            current_score=niche_clarity,
            potential_increase=min(15, 80 - niche_clarity),
            difficulty="medium",
            estimated_timeframe="3-4 weeks",
            specific_actions=[
                "Define 2-3 core content themes",
                "Reduce off-niche content to <20%",
                "Use consistent hashtags for your niche",
            ],
        ))

    # Sort by potential increase (highest first)
    improvements.sort(key=lambda x: x.potential_increase, reverse=True)

    return improvements[:3]  # Return top 3 opportunities


def calculate_brand_readiness(
    posts: list[SinglePostInsights],
    pillar_scores: dict | None = None,
) -> BrandReadinessBreakdown:
    """Calculate comprehensive brand readiness score.

    Args:
        posts: List of posts to analyze
        pillar_scores: Optional pillar scores from account health

    Returns:
        BrandReadinessBreakdown with component scores and improvements
    """
    logger.info("[BrandReadiness] Calculating with %d posts", len(posts))

    # Calculate component scores
    content_quality = _calculate_content_quality_score(posts)
    brand_safety = _calculate_brand_safety_score(posts)
    engagement = _calculate_engagement_score(posts)
    consistency = _calculate_consistency_score(posts)
    niche_clarity = _calculate_niche_clarity_score(posts, pillar_scores)
    audience_quality = _calculate_audience_quality_score(posts)

    # Calculate weighted overall score
    weights = {
        "content_quality": 0.20,
        "brand_safety": 0.25,
        "engagement": 0.25,
        "consistency": 0.15,
        "niche_clarity": 0.10,
        "audience_quality": 0.05,
    }

    overall = round(
        content_quality * weights["content_quality"]
        + brand_safety * weights["brand_safety"]
        + engagement * weights["engagement"]
        + consistency * weights["consistency"]
        + niche_clarity * weights["niche_clarity"]
        + audience_quality * weights["audience_quality"],
        1,
    )

    # Get label
    label = _get_label(overall)

    # Identify improvements
    improvements = _identify_improvements(
        content_quality, brand_safety, engagement,
        consistency, niche_clarity, audience_quality,
    )

    # Calculate improvement potential
    total_potential = sum(imp.potential_increase for imp in improvements)

    result = BrandReadinessBreakdown(
        overall_score=overall,
        overall_label=label,
        content_quality_score=content_quality,
        brand_safety_score=brand_safety,
        engagement_score=engagement,
        consistency_score=consistency,
        niche_clarity_score=niche_clarity,
        audience_quality_score=audience_quality,
        percentile_rank=min(95, max(5, overall)),  # Approximate percentile
        improvement_opportunities=[imp.area for imp in improvements],
    )

    logger.info(
        "[BrandReadiness] Score: %s (%s) with %d improvement areas",
        overall,
        label,
        len(improvements),
    )

    return result


def get_improvement_details(
    posts: list[SinglePostInsights],
    pillar_scores: dict | None = None,
) -> list[ImprovementOpportunity]:
    """Get detailed improvement opportunities.

    Returns full ImprovementOpportunity objects with actions.
    """
    content_quality = _calculate_content_quality_score(posts)
    brand_safety = _calculate_brand_safety_score(posts)
    engagement = _calculate_engagement_score(posts)
    consistency = _calculate_consistency_score(posts)
    niche_clarity = _calculate_niche_clarity_score(posts, pillar_scores)
    audience_quality = _calculate_audience_quality_score(posts)

    return _identify_improvements(
        content_quality, brand_safety, engagement,
        consistency, niche_clarity, audience_quality,
    )
