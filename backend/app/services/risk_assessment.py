"""Risk Assessment Dashboard for proactive account monitoring.

Identifies and alerts on declining metrics, brand safety issues,
and growth risks before they impact partnerships.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.app.domain.account_models import (
    Risk,
    RiskAssessment,
    RiskCategory,
    RiskLevel,
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


def _assess_engagement_risks(
    posts: list[SinglePostInsights],
) -> list[Risk]:
    """Assess engagement-related risks."""
    risks = []

    if len(posts) < 10:
        return risks

    # Split posts into recent (last 15) and older (before that)
    sorted_posts = sorted(
        posts,
        key=lambda p: p.published_at or datetime.min,
        reverse=True,
    )

    recent_posts = sorted_posts[:15]
    older_posts = sorted_posts[15:30] if len(sorted_posts) > 15 else []

    # Calculate average engagement rates
    recent_ers = [
        _safe_float(getattr(p.derived_metrics, "engagement_rate", None))
        for p in recent_posts
        if _safe_float(getattr(p.derived_metrics, "engagement_rate", None)) > 0
    ]
    older_ers = [
        _safe_float(getattr(p.derived_metrics, "engagement_rate", None))
        for p in older_posts
        if _safe_float(getattr(p.derived_metrics, "engagement_rate", None)) > 0
    ]

    if not recent_ers or not older_ers:
        return risks

    recent_avg = sum(recent_ers) / len(recent_ers)
    older_avg = sum(older_ers) / len(older_ers)

    if older_avg > 0:
        change_pct = (recent_avg - older_avg) / older_avg

        # Engagement decline risk
        if change_pct < -0.15:  # 15% decline
            level = RiskLevel.HIGH if change_pct < -0.25 else RiskLevel.MEDIUM
            risks.append(Risk(
                id="engagement_decline",
                category=RiskCategory.ENGAGEMENT_DECLINE,
                level=level,
                title="Engagement Rate Declining",
                description=(
                    f"Your engagement rate dropped {abs(change_pct)*100:.1f}% "
                    f"from {older_avg*100:.2f}% to {recent_avg*100:.2f}%"
                ),
                metric_affected="engagement_rate",
                current_value=recent_avg,
                previous_value=older_avg,
                change_percentage=round(change_pct * 100, 1),
                recommended_actions=[
                    "Review your top-performing posts for patterns",
                    "Test new content formats or hooks",
                    "Analyze if posting times have changed",
                ],
            ))

    # Check for high variance (inconsistent performance)
    if len(recent_ers) >= 5:
        import statistics
        try:
            std_dev = statistics.stdev(recent_ers)
            mean = statistics.mean(recent_ers)
            cv = std_dev / mean if mean > 0 else 0  # Coefficient of variation

            if cv > 0.5:  # High variability
                risks.append(Risk(
                    id="inconsistent_performance",
                    category=RiskCategory.CONTENT_PERFORMANCE,
                    level=RiskLevel.MEDIUM,
                    title="Inconsistent Content Performance",
                    description=(
                        f"Your engagement rate varies significantly "
                        f"(CV: {cv:.2f}). Some posts perform much better than others."
                    ),
                    metric_affected="engagement_rate_consistency",
                    current_value=cv,
                    recommended_actions=[
                        "Identify what makes your top posts different",
                        "Create more content similar to your best performers",
                        "Consider reducing experimental content",
                    ],
                ))
        except statistics.StatisticsError:
            pass

    return risks


def _assess_save_rate_risks(
    posts: list[SinglePostInsights],
) -> list[Risk]:
    """Assess save rate related risks."""
    risks = []

    if len(posts) < 10:
        return risks

    # Calculate save rates
    save_rates = []
    for post in posts:
        likes = _safe_float(getattr(post.core_metrics, "likes", None))
        saves = _safe_float(getattr(post.core_metrics, "saves", None))
        if likes > 0:
            save_rates.append(saves / likes)

    if len(save_rates) < 5:
        return risks

    avg_save_rate = sum(save_rates) / len(save_rates)

    # Low save rate risk
    if avg_save_rate < 0.03:  # Less than 3%
        risks.append(Risk(
            id="low_save_rate",
            category=RiskCategory.CONTENT_PERFORMANCE,
            level=RiskLevel.MEDIUM,
            title="Low Save Rate",
            description=(
                f"Your save rate ({avg_save_rate*100:.1f}%) is below optimal. "
                f"High save rates indicate valuable, shareable content."
            ),
            metric_affected="save_rate",
            current_value=avg_save_rate,
            recommended_actions=[
                "Create more save-worthy content (tutorials, tips, checklists)",
                "Add 'Save this for later' CTAs in captions",
                "Post educational content that provides lasting value",
            ],
        ))

    return risks


def _assess_brand_safety_risks(
    posts: list[SinglePostInsights],
) -> list[Risk]:
    """Assess brand safety related risks."""
    risks = []

    # Check for flagged posts
    flagged_count = 0
    low_safety_count = 0

    for post in posts:
        # Check vision analysis for flags
        if post.vision_analysis and post.vision_analysis.signals:
            first_signal = post.vision_analysis.signals[0]
            if (
                getattr(first_signal, "adult_content_detected", None) is True
                or getattr(first_signal, "is_cringe", None) is True
            ):
                flagged_count += 1

        # Check brand safety score
        safety_score = _safe_float(getattr(post.brand_safety_score, "total_0_50", None))
        if 0 < safety_score < 25:  # Low safety score (on 0-50 scale)
            low_safety_count += 1

    if flagged_count > 0:
        risks.append(Risk(
            id="flagged_content",
            category=RiskCategory.BRAND_SAFETY,
            level=RiskLevel.HIGH if flagged_count > 2 else RiskLevel.MEDIUM,
            title="Flagged Content Detected",
            description=(
                f"{flagged_count} post(s) flagged by vision safety signals. "
                f"This could impact brand partnership opportunities."
            ),
            metric_affected="flagged_posts",
            current_value=flagged_count,
            recommended_actions=[
                "Review flagged posts for potential issues",
                "Consider removing or editing problematic content",
                "Implement pre-publish safety checks",
            ],
        ))

    if low_safety_count > 3:
        risks.append(Risk(
            id="brand_safety_concerns",
            category=RiskCategory.BRAND_SAFETY,
            level=RiskLevel.MEDIUM,
            title="Brand Safety Concerns",
            description=(
                f"{low_safety_count} posts have low brand safety scores. "
                f"This may limit partnership opportunities."
            ),
            metric_affected="brand_safety_score",
            current_value=low_safety_count,
            recommended_actions=[
                "Review content for potential brand-safe issues",
                "Avoid controversial topics or language",
                "Focus on family-friendly, positive content",
            ],
        ))

    return risks


def _assess_growth_risks(
    posts: list[SinglePostInsights],
) -> list[Risk]:
    """Assess growth-related risks."""
    risks = []

    # Check posting frequency
    if len(posts) < 5:
        return risks

    # Calculate posts per week
    sorted_posts = sorted(
        posts,
        key=lambda p: p.published_at or datetime.min,
        reverse=True,
    )

    if sorted_posts and sorted_posts[0].published_at and sorted_posts[-1].published_at:
        date_range = (sorted_posts[0].published_at - sorted_posts[-1].published_at).days
        if date_range > 0:
            posts_per_week = (len(posts) / date_range) * 7

            if posts_per_week < 3:
                risks.append(Risk(
                    id="low_posting_frequency",
                    category=RiskCategory.GROWTH_SLOWDOWN,
                    level=RiskLevel.MEDIUM,
                    title="Low Posting Frequency",
                    description=(
                        f"You're posting {posts_per_week:.1f} times per week. "
                        f"Consistent posting (4-7x/week) drives growth."
                    ),
                    metric_affected="posting_frequency",
                    current_value=posts_per_week,
                    recommended_actions=[
                        "Aim for at least 4-5 posts per week",
                        "Create a content calendar for consistency",
                        "Batch-create content to maintain schedule",
                    ],
                ))

    return risks


def _assess_content_quality_risks(
    posts: list[SinglePostInsights],
) -> list[Risk]:
    """Assess content quality related risks."""
    risks = []

    if len(posts) < 5:
        return risks

    # Check for low-quality signals
    low_quality_count = 0

    for post in posts:
        if post.vision_analysis and post.vision_analysis.signals:
            first_signal = post.vision_analysis.signals[0]
            cringe_score = _safe_float(getattr(first_signal, "cringe_score", None))
            if cringe_score > 60:  # High cringe score
                low_quality_count += 1

    if low_quality_count > len(posts) * 0.3:  # More than 30% low quality
        risks.append(Risk(
            id="content_quality_issues",
            category=RiskCategory.CONTENT_PERFORMANCE,
            level=RiskLevel.MEDIUM,
            title="Content Quality Concerns",
            description=(
                f"{low_quality_count} posts have quality signals that may "
                f"impact engagement and brand perception."
            ),
            metric_affected="content_quality",
            current_value=low_quality_count,
            recommended_actions=[
                "Review flagged posts for quality improvements",
                "Focus on better lighting, framing, and editing",
                "Study top-performing posts for quality benchmarks",
            ],
        ))

    return risks


def assess_account_risks(
    posts: list[SinglePostInsights],
) -> RiskAssessment:
    """Perform comprehensive risk assessment for an account.

    Args:
        posts: List of recent posts to analyze

    Returns:
        RiskAssessment with all detected risks and recommendations
    """
    logger.info("[RiskAssessment] Starting assessment with %d posts", len(posts))

    all_risks: list[Risk] = []

    # Run all risk assessments
    all_risks.extend(_assess_engagement_risks(posts))
    all_risks.extend(_assess_save_rate_risks(posts))
    all_risks.extend(_assess_brand_safety_risks(posts))
    all_risks.extend(_assess_growth_risks(posts))
    all_risks.extend(_assess_content_quality_risks(posts))

    # Determine overall risk level
    if any(r.level == RiskLevel.CRITICAL for r in all_risks):
        overall_level = RiskLevel.CRITICAL
    elif any(r.level == RiskLevel.HIGH for r in all_risks):
        overall_level = RiskLevel.HIGH
    elif any(r.level == RiskLevel.MEDIUM for r in all_risks):
        overall_level = RiskLevel.MEDIUM
    else:
        overall_level = RiskLevel.LOW

    # Collect all recommended actions
    all_actions = []
    for risk in all_risks:
        all_actions.extend(risk.recommended_actions)
    # Deduplicate while preserving order
    seen = set()
    unique_actions = []
    for action in all_actions:
        if action not in seen:
            seen.add(action)
            unique_actions.append(action)

    assessment = RiskAssessment(
        overall_risk_level=overall_level,
        risks=all_risks,
        risk_count=len(all_risks),
        recommended_actions=unique_actions[:10],  # Top 10 actions
    )

    logger.info(
        "[RiskAssessment] Completed: level=%s risks=%d",
        overall_level.value,
        len(all_risks),
    )

    return assessment
