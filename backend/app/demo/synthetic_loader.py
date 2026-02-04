"""
Synthetic Creator Data Loader

Loads synthetic creator data from JSON and converts to AI schemas.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from backend.app.ai.schemas import CreatorProfileAIInput, CreatorPostAIInput


DATA_PATH = Path(__file__).parent / "synthetic_creator.json"


def load_synthetic(path: Path = None):
    """
    Load synthetic creator data from JSON file.
    Returns (CreatorProfileAIInput, List[CreatorPostAIInput])
    """
    if path is None:
        path = DATA_PATH

    with open(path) as f:
        raw = json.load(f)

    p = raw["profile"]

    # Calculate engagement rate by views (ratio)
    avg_views = p.get("avg_views", 0)
    avg_likes = p.get("avg_likes", 0)
    avg_comments = p.get("avg_comments", 0)

    if avg_views > 0:
        avg_engagement_rate = (avg_likes + avg_comments) / avg_views
    else:
        avg_engagement_rate = 0

    profile = CreatorProfileAIInput(
        creator_id=p["username"],
        username=p["username"],
        platform="instagram",
        bio_text=p.get("bio", ""),
        followers_count=p["followers"],
        following_count=p.get("following", 0),
        total_posts=p.get("total_posts", 0),
        account_type="creator",
        avg_likes=avg_likes,
        avg_comments=avg_comments,
        avg_views=avg_views,
        posts_per_week=p.get("posts_per_week", 2.0),
        historical_engagement={
            "avg_likes": avg_likes,
            "avg_comments": avg_comments,
            "avg_views": avg_views,
            "avg_engagement_rate_by_views": avg_engagement_rate
        },
        posting_frequency_per_week=p.get("posts_per_week", 2.0),
        profile_last_updated=datetime.now(timezone.utc)
    )

    posts = []
    for post in raw["posts"]:
        # Parse posted_at if it's a string
        posted_at = post.get("posted_at")
        if isinstance(posted_at, str):
            try:
                posted_at = datetime.fromisoformat(posted_at)
            except Exception:
                posted_at = datetime.now(timezone.utc)
        elif posted_at is None:
            posted_at = datetime.now(timezone.utc)

        posts.append(
            CreatorPostAIInput(
                post_id=post["post_id"],
                creator_id=p["username"],
                platform="instagram",
                post_type=post.get("post_type", "reel"),
                caption_text=post.get("caption_text", ""),
                hashtags=post.get("hashtags", []),
                likes=post.get("likes", 0),
                comments=post.get("comments", 0),
                views=post.get("views"),
                posted_at=posted_at
            )
        )

    return profile, posts
