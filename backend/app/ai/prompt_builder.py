from typing import Dict, List


# ------------------------------------------------
# Prompt Builder
# ------------------------------------------------

def build_creator_explanation_prompt(context: Dict) -> Dict:
    """
    Build a structured prompt for creator performance explanations.
    Includes PDF-based metrics and RAG-retrieved knowledge.
    Returns a dict with system + user messages (LLM-agnostic).
    """

    creator = context["creator_profile"]
    ai = context["ai_analysis"]
    posts = context["recent_posts"]
    retrieved_knowledge = context.get("retrieved_knowledge", [])

    # Extract niche info
    niche_data = ai.get("niche", {})
    primary_niche = niche_data.get("primary_niche", "unknown") if isinstance(niche_data, dict) else "unknown"

    # Extract growth breakdown
    growth_breakdown = ai.get("growth_breakdown", {})

    system_message = (
        "You are an experienced creator growth advisor. "
        "You explain performance using data-driven metrics and platform knowledge. "
        "Focus on engagement rate by views (the primary Instagram metric), "
        "relative performance vs creator average, and actionable insights. "
        "Reference the relevant platform knowledge provided when giving advice. "
        "Do not invent metrics or make promises."
    )

    avg_engagement_rate_by_views = ai.get("avg_engagement_rate_by_views")
    avg_engagement_pct = (
        f"{avg_engagement_rate_by_views * 100:.2f}%"
        if isinstance(avg_engagement_rate_by_views, (int, float))
        else "N/A"
    )

    user_message = f"""
Creator Summary:
- Username: {creator['username']}
- Platform: {creator['platform']}
- Followers: {creator['followers']:,}
- Primary niche: {primary_niche}
- Growth score: {ai.get('growth_score', 'N/A')}/100
- Avg engagement by views: {avg_engagement_pct}
- Views/followers ratio: {ai.get('views_to_followers_ratio', 'N/A')}

Creator Profile:
- Platform: {creator['platform']}
- Username: {creator['username']}
- Followers: {creator['followers']:,}
- Avg Views: {creator.get('avg_views', 'N/A')}
- Posting frequency: {creator.get('posting_frequency_per_week', 'N/A')} posts/week

Key Metrics:
- Avg Engagement Rate by Views: {avg_engagement_pct}
- Views to Followers Ratio: {ai.get('views_to_followers_ratio', 'N/A')}
- Primary Niche: {primary_niche}
- Growth Score: {ai.get('growth_score', 'N/A')}/100

Growth Score Breakdown:
- Engagement: {growth_breakdown.get('engagement', 'N/A')}/30
- Content Reach: {growth_breakdown.get('content', 'N/A')}/20
- Consistency: {growth_breakdown.get('consistency', 'N/A')}/20
- Audience Size: {growth_breakdown.get('audience', 'N/A')}/20
- Growth Trend: {growth_breakdown.get('growth_trend', 'N/A')}/10

Recent Posts Summary:
{_format_posts_summary(posts)}

Post-Level Insights:
{_format_post_insights(ai.get('post_insights', []))}

---
Relevant Platform Knowledge:
{_format_rag_knowledge(retrieved_knowledge)}
---

Task:
Based on the above metrics and platform knowledge, explain the creator's current performance in clear, practical terms.
Focus on:
1. What the engagement rate by views indicates
2. How their content is performing relative to their average
3. Specific, actionable recommendations based on the platform knowledge provided
""".strip()

    return {
        "system": system_message,
        "user": user_message
    }


def _format_posts_summary(posts: list) -> str:
    """Format posts for the prompt"""
    if not posts:
        return "No recent posts available"

    lines = []
    for p in posts[:5]:  # Limit to 5 posts
        engagement_str = ""
        if isinstance(p.get("engagement_rate_by_views"), (int, float)):
            engagement_str = f", Engagement by Views: {p['engagement_rate_by_views'] * 100:.2f}%"

        lines.append(
            f"- Post {p['post_id']}: {p['likes']} likes, {p['comments']} comments, "
            f"{p.get('views', 'N/A')} views{engagement_str}"
        )

    return "\n".join(lines)


def _format_post_insights(insights: list) -> str:
    """Format post insights for the prompt"""
    if not insights:
        return "No post-level insights available"

    lines = []
    for p in insights[:3]:  # Limit to 3 posts
        if "error" in p:
            continue

        perf = p.get("relative_performance")
        perf_str = f"{perf}x average" if perf else "N/A"

        engagement = p.get("engagement_rate_by_views")
        engagement_str = (
            f"{engagement * 100:.2f}%"
            if isinstance(engagement, (int, float))
            else "N/A"
        )

        lines.append(
            f"- Post {p['post_id']}: "
            f"Engagement by Views: {engagement_str}, "
            f"Relative Performance: {perf_str}"
        )

    return "\n".join(lines) if lines else "No insights available"


def _format_rag_knowledge(knowledge: List[str]) -> str:
    """Format RAG-retrieved knowledge for the prompt"""
    if not knowledge:
        return "No additional platform knowledge retrieved."

    formatted = []
    for i, chunk in enumerate(knowledge, 1):
        # Clean up the chunk formatting
        formatted.append(f"{i}. {chunk.strip()}")

    return "\n\n".join(formatted)


