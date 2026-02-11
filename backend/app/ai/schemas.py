from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime


# -----------------------------
# Creator Profile AI Input
# -----------------------------

class CreatorProfileAIInput(BaseModel):
    creator_id: str
    platform: str  # instagram, youtube (future)

    username: str
    bio_text: str = ""

    followers_count: int
    following_count: int
    total_posts: int

    account_type: str = "creator"  # creator | business | personal

    # Aggregated metrics from recent posts
    avg_likes: float = 0.0
    avg_comments: float = 0.0
    avg_views: Optional[float] = None

    posts_per_week: float = 0.0

    historical_engagement: Dict = {}
    """
    {
        "avg_likes": float,
        "avg_comments": float,
        "avg_views": Optional[float],
        "avg_engagement_rate_by_views": Optional[float]
    }
    """

    posting_frequency_per_week: Optional[float] = None

    profile_last_updated: datetime


# -----------------------------
# Creator Post / Reel AI Input
# -----------------------------

class CreatorPostAIInput(BaseModel):
    post_id: str
    creator_id: str = ""
    platform: str = "instagram"

    post_type: str = "post"  # image | reel | video

    caption_text: str = ""
    hashtags: List[str] = []

    likes: int = 0
    comments: int = 0
    views: Optional[int] = None

    audio_name: Optional[str] = None

    posted_at: Optional[datetime] = None


