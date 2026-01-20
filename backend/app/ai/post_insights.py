from typing import Dict
from datetime import datetime

from backend.app.ai.schemas import CreatorPostAIInput, CreatorProfileAIInput


# ------------------------------------------------
# Helper functions
# ------------------------------------------------

def _engagement_rate(likes: int, comments: int, followers: int) -> float:
    if followers <= 0:
        return 0.0
    return round((likes + comments) / followers * 100, 2)


def _has_cta(caption: str) -> bool:
    if not caption:
        return False

    cta_keywords = [
        "comment", "share", "save", "follow",
        "link in bio", "dm", "tell me", "what do you think"
    ]
    text = caption.lower()
    return any(k in text for k in cta_keywords)


# ------------------------------------------------
# Public API: Modern Post Insights
# ------------------------------------------------

def analyze_post(
    post: CreatorPostAIInput,
    creator_profile: CreatorProfileAIInput
) -> Dict:
    """
    Analyze a single Instagram post or reel using
    2025+ best practices (context-first, engagement-driven).
    """

    # -----------------------------
    # Engagement analysis
    # -----------------------------

    post_engagement = _engagement_rate(
        post.likes,
        post.comments,
        creator_profile.followers_count
    )

    avg_engagement = _engagement_rate(
        creator_profile.historical_engagement.get("avg_likes", 0),
        creator_profile.historical_engagement.get("avg_comments", 0),
        creator_profile.followers_count
    )

    if post_engagement > avg_engagement:
        engagement_verdict = "above your recent average"
    elif post_engagement < avg_engagement:
        engagement_verdict = "below your recent average"
    else:
        engagement_verdict = "in line with your recent average"

    # -----------------------------
    # Caption context (not “hook”)
    # -----------------------------

    caption_text = post.caption_text or ""
    caption_word_count = len(caption_text.split())

    provides_context = caption_word_count >= 3

    # -----------------------------
    # CTA (optional optimization)
    # -----------------------------

    cta_present = _has_cta(caption_text)

    # -----------------------------
    # Hashtags (contextual signal)
    # -----------------------------

    hashtag_count = len(post.hashtags)

    # -----------------------------
    # Timing (descriptive only)
    # -----------------------------

    posted_time = post.posted_at
    posting_hour = posted_time.hour
    weekday = posted_time.strftime("%A")

    # -----------------------------
    # Insight generation
    # -----------------------------

    insights = []

    # Engagement insight
    insights.append(
        f"This post performed {engagement_verdict} "
        f"({post_engagement}% vs {avg_engagement}%)."
    )

    # Caption insight (modern)
    if not provides_context:
        insights.append(
            "The caption provides minimal context. While short captions are fine, "
            "adding a bit more clarity can help viewers quickly understand the content."
        )
    else:
        insights.append(
            "Caption length provides enough context for the content."
        )

    # CTA insight (soft recommendation)
    if not cta_present:
        insights.append(
            "There is no call-to-action. Adding a light prompt (question, save, or comment) "
            "can increase interactions, which Instagram tends to reward."
        )

    # Hashtag insight (2025+ aligned)
    if hashtag_count == 0:
        insights.append(
            "No hashtags were used. Adding 1–5 relevant hashtags can help Instagram "
            "categorize the content for search and recommendations."
        )
    elif hashtag_count > 5:
        insights.append(
            "Using many hashtags is no longer necessary. A smaller set of highly relevant "
            "hashtags generally performs better."
        )
    else:
        insights.append(
            "Hashtag usage is aligned with current best practices."
        )

    # Timing insight (non-prescriptive)
    insights.append(
        f"Posted on {weekday} around {posting_hour}:00. "
        "Track performance over time to identify which posting windows work best for your audience."
    )

    # -----------------------------
    # Final structured output
    # -----------------------------

    return {
        "post_id": post.post_id,
        "engagement_rate": post_engagement,
        "caption_context": provides_context,
        "cta_present": cta_present,
        "hashtag_count": hashtag_count,
        "posting_time": {
            "weekday": weekday,
            "hour": posting_hour
        },
        "insights": insights
    }
