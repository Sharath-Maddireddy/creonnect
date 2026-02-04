"""
Snapshot Service

Builds creator snapshot responses.
"""

from backend.app.demo.synthetic_loader import load_synthetic
from backend.app.ai.growth_score import compute_growth_score
from backend.core.snapshots import build_creator_snapshot


def build_creator_snapshot_service(creator_id: str) -> dict:
    """
    Build a daily snapshot for a creator.

    Raises:
        ValueError: if creator not found
    """
    profile, posts = load_synthetic()

    if profile.username != creator_id and creator_id != "demo":
        raise ValueError("Creator not found")

    growth = compute_growth_score(profile, posts)

    creator_data = {
        "username": profile.username,
        "followers": profile.followers_count,
        "avg_views": profile.avg_views or 0,
        "avg_likes": profile.avg_likes,
        "avg_comments": profile.avg_comments,
        "growth_score": growth.get("growth_score", 0)
    }

    return build_creator_snapshot(creator_data)
