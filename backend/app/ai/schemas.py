"""Pydantic schemas for creator profile and post AI inputs."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, field_validator


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

    post_type: Literal["IMAGE", "REEL"] = "IMAGE"
    media_url: str = ""
    thumbnail_url: str = ""

    caption_text: str = ""
    hashtags: List[str] = []

    likes: int = 0
    comments: int = 0
    views: Optional[int] = None
    reel_duration_sec: Optional[float] = None
    share_count: Optional[int] = None
    saves: Optional[int] = None
    watch_time_pct: Optional[float] = None  # 0.0 - 1.0

    audio_name: Optional[str] = None

    posted_at: Optional[datetime] = None

    @field_validator("post_type", mode="before")
    @classmethod
    def normalize_post_type(cls, value: str | None) -> Literal["IMAGE", "REEL"]:
        normalized = value.strip().upper() if isinstance(value, str) else ""
        if normalized in {"REEL", "VIDEO", "CLIPS"}:
            return "REEL"
        return "IMAGE"

    @field_validator("media_url", "thumbnail_url", mode="before")
    @classmethod
    def normalize_media_urls(cls, value: str | None) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()


