from typing import Dict, List, Optional
from backend.app.ai.schemas import CreatorProfileAIInput, CreatorPostAIInput


# -----------------------------
# PDF-Based Scoring Functions
# -----------------------------

def _score_engagement_by_views(avg_engagement_rate_by_views: Optional[float]) -> int:
    """
    Score based on average engagement rate by views (PDF metric).
    Max: 30 points
    """
    if avg_engagement_rate_by_views is None:
        return 10  # Default if no view data

    if avg_engagement_rate_by_views >= 10:
        return 30
    if avg_engagement_rate_by_views >= 7:
        return 26
    if avg_engagement_rate_by_views >= 5:
        return 22
    if avg_engagement_rate_by_views >= 3:
        return 18
    if avg_engagement_rate_by_views >= 1:
        return 12
    return 6


def _score_views_to_followers_ratio(
    avg_views: Optional[float],
    followers: int
) -> int:
    """
    Score based on views/followers ratio.
    High ratio = content reaching beyond followers (viral potential).
    Max: 20 points
    """
    if avg_views is None or followers <= 0:
        return 5  # Default if no view data

    ratio = avg_views / followers

    if ratio >= 2.0:
        return 20  # Views 2x+ followers = viral
    if ratio >= 1.0:
        return 16  # Views match followers
    if ratio >= 0.5:
        return 12  # Half followers viewing
    if ratio >= 0.2:
        return 8
    return 4


def _score_consistency(posts_per_week: float) -> int:
    """
    Score based on posting frequency.
    Max: 20 points
    """
    if posts_per_week >= 7:
        return 20  # Daily posting
    if posts_per_week >= 5:
        return 18
    if posts_per_week >= 3:
        return 14
    if posts_per_week >= 1:
        return 10
    return 4


def _score_audience_size(followers: int) -> int:
    """
    Score based on follower count.
    Max: 20 points
    """
    if followers >= 1_000_000:
        return 20
    if followers >= 100_000:
        return 18
    if followers >= 50_000:
        return 16
    if followers >= 10_000:
        return 12
    if followers >= 1_000:
        return 8
    return 4


def _calculate_avg_engagement_rate_by_views(posts: List[CreatorPostAIInput]) -> Optional[float]:
    """Calculate average engagement rate by views across posts."""
    rates = []
    for post in posts:
        if post.views and post.views > 0:
            total_interactions = post.likes + post.comments
            rate = (total_interactions / post.views) * 100
            rates.append(rate)

    if not rates:
        return None
    return sum(rates) / len(rates)


# -----------------------------
# Public API
# -----------------------------

def compute_growth_score(
    profile: CreatorProfileAIInput,
    posts: List[CreatorPostAIInput]
) -> Dict:
    """
    Computes overall growth score using PDF-aligned metrics.
    
    Primary factors:
    - Engagement rate by views (most important)
    - Views/followers ratio (reach beyond followers)
    - Posting consistency
    - Audience size
    - Growth trend (placeholder)
    """

    followers = profile.followers_count or 0
    posts_per_week = profile.posts_per_week or profile.posting_frequency_per_week or 0

    # Calculate average engagement rate by views from posts
    avg_engagement_rate_by_views = _calculate_avg_engagement_rate_by_views(posts)

    # Get average views from profile or calculate from posts
    avg_views = profile.avg_views
    if avg_views is None and posts:
        views_list = [p.views for p in posts if p.views]
        if views_list:
            avg_views = sum(views_list) / len(views_list)

    # Calculate scores
    engagement = _score_engagement_by_views(avg_engagement_rate_by_views)
    content = _score_views_to_followers_ratio(avg_views, followers)
    consistency = _score_consistency(posts_per_week)
    audience = _score_audience_size(followers)

    # Growth trend placeholder (would need historical data)
    growth_trend = 7

    # Total score
    total = engagement + content + consistency + audience + growth_trend

    return {
        "growth_score": min(total, 100),
        "breakdown": {
            "engagement": engagement,
            "content": content,
            "consistency": consistency,
            "audience": audience,
            "growth_trend": growth_trend
        },
        "metrics": {
            "avg_engagement_rate_by_views": round(avg_engagement_rate_by_views, 2)
            if avg_engagement_rate_by_views is not None else None,
            "avg_views": round(avg_views, 0) if avg_views is not None else None,
            "views_to_followers_ratio": round(avg_views / followers, 2) if avg_views and followers > 0 else None,
            "posts_per_week": posts_per_week
        }
    }
