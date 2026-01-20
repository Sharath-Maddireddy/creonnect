from datetime import datetime
from typing import List, Dict

from backend.app.ai.schemas import (
    CreatorProfileAIInput,
    CreatorPostAIInput
)


# ------------------------------------------------
# Mapper: Raw Instagram → AI Schemas
# ------------------------------------------------

def map_profile_data(raw: Dict) -> CreatorProfileAIInput:
    """
    Map raw scraped Instagram profile data
    into CreatorProfileAIInput.
    """

    return CreatorProfileAIInput(
        creator_id=raw["username"],
        platform="instagram",
        username=raw["username"],
        bio_text=raw.get("bio", ""),

        followers_count=raw.get("followers", 0),
        following_count=raw.get("following", 0),
        total_posts=raw.get("total_posts", 0),

        account_type="creator",

        historical_engagement={
            "avg_likes": raw.get("avg_likes", 0),
            "avg_comments": raw.get("avg_comments", 0),
            "avg_views": raw.get("avg_views")
        },

        posting_frequency_per_week=raw.get("posts_per_week", 0),
        profile_last_updated=datetime.utcnow()
    )


def map_posts_data(
    raw_posts: List[Dict],
    creator_id: str
) -> List[CreatorPostAIInput]:
    """
    Map raw scraped posts into CreatorPostAIInput list.
    """

    posts = []

    for p in raw_posts:
        posts.append(
            CreatorPostAIInput(
                post_id=p["id"],
                creator_id=creator_id,
                platform="instagram",
                post_type=p.get("type", "reel"),

                caption_text=p.get("caption", ""),
                hashtags=p.get("hashtags", []),

                likes=p.get("likes", 0),
                comments=p.get("comments", 0),
                views=p.get("views"),

                audio_name=p.get("audio"),
                posted_at=p.get("posted_at", datetime.utcnow())
            )
        )

    return posts
