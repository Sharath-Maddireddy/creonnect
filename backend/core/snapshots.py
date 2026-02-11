"""
Creator Snapshots Module

Generates daily snapshots of creator metrics for tracking and analysis.
"""

from datetime import date


def build_creator_snapshot(creator: dict) -> dict:
    """
    Generate a daily snapshot for a creator.
    
    Args:
        creator: dict with keys like username, followers, avg_views,
                 avg_likes, avg_comments, growth_score
    
    Returns:
        JSON-safe dict with snapshot data including calculated metrics
    """
    # Extract fields with defensive .get() access
    username = creator.get("username", "unknown")
    followers = creator.get("followers", 0)
    avg_views = creator.get("avg_views", 0)
    avg_likes = creator.get("avg_likes", 0)
    avg_comments = creator.get("avg_comments", 0)
    growth_score = creator.get("growth_score", 0)
    
    # Calculate derived metrics
    total_interactions = avg_likes + avg_comments
    engagement_rate_by_views = (avg_likes + avg_comments) / max(avg_views, 1)
    
    # Build snapshot
    snapshot = {
        "creator_id": username,
        "date": date.today().isoformat(),
        "followers": followers,
        "avg_views": avg_views,
        "avg_likes": avg_likes,
        "avg_comments": avg_comments,
        "total_interactions": total_interactions,
        "engagement_rate_by_views": round(engagement_rate_by_views, 4),
        "growth_score": growth_score
    }
    
    return snapshot


