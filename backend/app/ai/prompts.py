from typing import Dict, List


# -----------------------------
# Prompt Builders (LLM-agnostic)
# -----------------------------

def creator_profile_explanation(
    niche_data: Dict,
    growth_data: Dict
) -> str:
    """
    Explain creator profile and growth score in plain English.
    """

    primary = niche_data.get("primary_niche")
    secondary = niche_data.get("secondary_niche")
    confidence = niche_data.get("confidence")

    score = growth_data.get("growth_score")
    breakdown = growth_data.get("breakdown", {})

    return f"""
You are primarily a {primary} creator, with secondary relevance in {secondary}.
This classification has a confidence of {confidence * 100:.0f}%.

Your overall growth score is {score}/100.

Here’s what that means:
- Engagement strength: {breakdown.get("engagement")} / 30
- Posting consistency: {breakdown.get("consistency")} / 20
- Audience size: {breakdown.get("audience")} / 20
- Content performance: {breakdown.get("content")} / 20
- Growth momentum: {breakdown.get("growth_trend")} / 10

This score reflects how attractive your profile is to brands today,
and how strong your growth fundamentals are.
""".strip()


def post_performance_explanation(
    post_insights: Dict
) -> str:
    """
    Explain post-level performance using modern Instagram signals.
    """

    engagement = post_insights.get("engagement_rate_by_views", 0)
    caption_context = post_insights.get("caption_context_present", False)
    cta = post_insights.get("cta_present", False)
    insights = post_insights.get("insights", [])

    advice = []

    if not caption_context:
        advice.append(
            "Consider adding a bit more context in the caption so viewers immediately understand the post."
        )

    if not cta:
        advice.append(
            "You could experiment with a light call-to-action (question, save, or comment) to encourage interaction."
        )

    engagement_pct = (
        f"{engagement * 100:.2f}"
        if isinstance(engagement, (int, float))
        else "N/A"
    )

    return f"""
This post achieved an engagement rate of {engagement_pct}%.

Key observations:
- Caption provides context: {"Yes" if caption_context else "No"}
- Call-to-action present: {"Yes" if cta else "No"}

What the data shows:
{chr(10).join(f"- {i}" for i in insights)}

Recommended next actions:
{chr(10).join(f"- {a}" for a in advice) if advice else "- Maintain this format, as it aligns well with your current performance."}
""".strip()


