"""
Instagram API Mapper

Converts Instagram API responses (Graph API format) into AI schemas:
- CreatorProfileAIInput
- CreatorPostAIInput
"""

import re
from datetime import datetime, timezone
from typing import List, Dict, Tuple

from backend.app.ai.schemas import CreatorProfileAIInput, CreatorPostAIInput
from backend.app.utils.logger import logger


HASHTAG_RE = re.compile(r"#\w+")


def _extract_hashtags(caption: str) -> List[str]:
    """Extract hashtags from caption text."""
    if not caption:
        return []
    return HASHTAG_RE.findall(caption)


def _safe_int(v, default=0) -> int:
    """Safely convert value to int."""
    try:
        return int(v)
    except Exception:
        return default


def map_instagram_profile(api_profile: Dict, api_media: List[Dict]) -> CreatorProfileAIInput:
    """
    Map Instagram API profile + media list into CreatorProfileAIInput.
    Expects fields similar to Graph API:
      profile: username, biography, followers_count
      media: list with like_count, comments_count, video_view_count, timestamp
    """
    logger.info("[Ingestion] Mapping Instagram API profile")

    followers = _safe_int(api_profile.get("followers_count", 0))

    likes = []
    comments = []
    views = []
    timestamps = []

    for m in api_media:
        likes.append(_safe_int(m.get("like_count", 0)))
        comments.append(_safe_int(m.get("comments_count", 0)))

        v = m.get("video_view_count")
        if v is not None:
            views.append(_safe_int(v))

        ts = m.get("timestamp")
        if ts:
            try:
                timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except Exception:
                pass

    avg_likes = round(sum(likes) / len(likes)) if likes else 0
    avg_comments = round(sum(comments) / len(comments)) if comments else 0
    avg_views = round(sum(views) / len(views)) if views else None

    # Estimate posts per week from timestamps (simple heuristic)
    posts_per_week = 2.0
    if len(timestamps) >= 2:
        timestamps.sort()
        days = (timestamps[-1] - timestamps[0]).days
        if days > 0:
            posts_per_week = round((len(timestamps) / days) * 7, 2)

    # Calculate engagement rate by views (ratio)
    if avg_views and avg_views > 0:
        avg_engagement_rate = (avg_likes + avg_comments) / avg_views
    else:
        avg_engagement_rate = 0

    return CreatorProfileAIInput(
        creator_id=api_profile.get("username", ""),
        username=api_profile.get("username", ""),
        platform="instagram",
        bio_text=api_profile.get("biography", "") or "",
        followers_count=max(followers, 0),
        following_count=_safe_int(api_profile.get("follows_count", 0)),
        total_posts=_safe_int(api_profile.get("media_count", len(api_media))),
        account_type="creator",
        avg_likes=max(avg_likes, 0),
        avg_comments=max(avg_comments, 0),
        avg_views=max(avg_views, 0) if avg_views is not None else None,
        posts_per_week=posts_per_week,
        historical_engagement={
            "avg_likes": avg_likes,
            "avg_comments": avg_comments,
            "avg_views": avg_views,
            "avg_engagement_rate_by_views": avg_engagement_rate
        },
        posting_frequency_per_week=posts_per_week,
        profile_last_updated=datetime.now(timezone.utc)
    )


def map_instagram_posts(api_media: List[Dict]) -> List[CreatorPostAIInput]:
    """
    Map Instagram API media list into CreatorPostAIInput list.
    """
    logger.info(f"[Ingestion] Mapping {len(api_media)} Instagram posts")

    posts = []

    for m in api_media:
        caption = m.get("caption", "") or ""

        # Detect post type from media_type
        media_type = m.get("media_type", "")
        post_type = "reel" if media_type in ("VIDEO", "REEL") else "post"

        # Parse timestamp
        ts = m.get("timestamp")
        posted_at = None
        if ts:
            try:
                posted_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                posted_at = datetime.now(timezone.utc)

        # Get views (only for videos)
        views = None
        if m.get("video_view_count") is not None:
            views = _safe_int(m.get("video_view_count"))

        posts.append(
            CreatorPostAIInput(
                post_id=m.get("id", ""),
                creator_id=m.get("username", ""),
                platform="instagram",
                post_type=post_type,
                caption_text=caption,
                hashtags=_extract_hashtags(caption),
                likes=_safe_int(m.get("like_count", 0)),
                comments=_safe_int(m.get("comments_count", 0)),
                views=views,
                audio_name=None,
                posted_at=posted_at
            )
        )

    return posts


def map_instagram_to_ai_inputs(
    api_profile: Dict,
    api_media: List[Dict]
) -> Tuple[CreatorProfileAIInput, List[CreatorPostAIInput]]:
    """
    Convenience wrapper returning (CreatorProfileAIInput, List[CreatorPostAIInput])
    """
    profile = map_instagram_profile(api_profile, api_media)
    posts = map_instagram_posts(api_media)
    logger.info(f"[Ingestion] Completed API mapping: {len(posts)} posts, {profile.followers_count} followers")
    return profile, posts


