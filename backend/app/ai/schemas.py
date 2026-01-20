from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


# -----------------------------
# Creator Profile AI Input
# -----------------------------

class CreatorProfileAIInput(BaseModel):
    creator_id: str
    platform: str  # instagram, youtube (future)

    username: str
    bio_text: str

    followers_count: int
    following_count: int
    total_posts: int

    account_type: str  # creator | business | personal

    historical_engagement: dict
    """
    {
        "avg_likes": float,
        "avg_comments": float,
        "avg_views": Optional[float]
    }
    """

    posting_frequency_per_week: float

    profile_last_updated: datetime


# -----------------------------
# Creator Post / Reel AI Input
# -----------------------------

class CreatorPostAIInput(BaseModel):
    post_id: str
    creator_id: str
    platform: str  # instagram

    post_type: str  # image | reel | video

    caption_text: str
    hashtags: List[str]

    likes: int
    comments: int
    views: Optional[int]

    audio_name: Optional[str]

    posted_at: datetime
