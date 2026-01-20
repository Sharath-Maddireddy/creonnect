from typing import Dict
from backend.app.ai.schemas import CreatorProfileAIInput


# -----------------------------
# Helper Scoring Functions
# -----------------------------

def _score_engagement(avg_likes: float, avg_comments: float, followers: int) -> int:
    if followers <= 0:
        return 0

    engagement_rate = (avg_likes + avg_comments) / followers * 100

    if engagement_rate >= 6:
        return 30
    if engagement_rate >= 4:
        return 24
    if engagement_rate >= 2:
        return 18
    if engagement_rate >= 1:
        return 10
    return 5


def _score_consistency(posts_per_week: float) -> int:
    if posts_per_week >= 5:
        return 20
    if posts_per_week >= 3:
        return 16
    if posts_per_week >= 1:
        return 10
    return 4


def _score_audience_size(followers: int) -> int:
    if followers >= 100_000:
        return 20
    if followers >= 50_000:
        return 16
    if followers >= 10_000:
        return 12
    if followers >= 1_000:
        return 8
    return 4


def _score_content_performance(avg_views: float, followers: int) -> int:
    if followers <= 0 or avg_views <= 0:
        return 0

    view_ratio = avg_views / followers

    if view_ratio >= 1.2:
        return 20
    if view_ratio >= 0.8:
        return 16
    if view_ratio >= 0.5:
        return 10
    return 6


def _score_growth_trend(posts_per_week: float, engagement_rate: float) -> int:
    if posts_per_week >= 3 and engagement_rate >= 4:
        return 10
    if posts_per_week >= 2 and engagement_rate >= 2:
        return 7
    return 4


# -----------------------------
# Public Growth Score API
# -----------------------------

def calculate_growth_score(
    profile: CreatorProfileAIInput
) -> Dict:
    """
    Platform-wide Growth Score (0–100)
    """

    avg_likes = profile.historical_engagement.get("avg_likes", 0)
    avg_comments = profile.historical_engagement.get("avg_comments", 0)
    avg_views = profile.historical_engagement.get("avg_views", 0)

    followers = profile.followers_count
    posts_per_week = profile.posting_frequency_per_week

    engagement_rate = (
        (avg_likes + avg_comments) / followers * 100
        if followers > 0 else 0
    )

    engagement_score = _score_engagement(avg_likes, avg_comments, followers)
    consistency_score = _score_consistency(posts_per_week)
    audience_score = _score_audience_size(followers)
    content_score = _score_content_performance(avg_views, followers)
    trend_score = _score_growth_trend(posts_per_week, engagement_rate)

    total_score = (
        engagement_score +
        consistency_score +
        audience_score +
        content_score +
        trend_score
    )

    return {
        "growth_score": min(total_score, 100),
        "breakdown": {
            "engagement": engagement_score,
            "consistency": consistency_score,
            "audience": audience_score,
            "content": content_score,
            "growth_trend": trend_score
        }
    }
