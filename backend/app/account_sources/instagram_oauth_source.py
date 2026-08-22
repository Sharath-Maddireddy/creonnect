"""Materialize an authenticated Instagram account into canonical analysis posts."""

from __future__ import annotations

import asyncio

from backend.app.account_sources.base import AccountSource
from backend.app.account_sources.mappers import build_seed_post_from_creator_post, safe_float_or_none, safe_int_or_none
from backend.app.account_sources.models import AccountSourceRequest, AccountSourceType, NormalizedAccountPayload
from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.ingestion.instagram_oauth import (
    fetch_instagram_account_insights,
    fetch_instagram_media,
    fetch_instagram_profile,
)


class InstagramOAuthAccountSource(AccountSource):
    """Load account analysis input from a server-side Instagram OAuth token."""

    source_type = AccountSourceType.INSTAGRAM_OAUTH

    async def load(self, request: AccountSourceRequest) -> NormalizedAccountPayload:
        if not request.access_token:
            raise ValueError("A connected Instagram account is required for this source.")
        profile, media, account_insights = await asyncio.gather(
            fetch_instagram_profile(request.access_token),
            fetch_instagram_media(request.access_token, limit=request.post_limit),
            fetch_instagram_account_insights(request.access_token),
        )
        account_id = str(profile.get("id") or request.account_id or "")
        if not account_id:
            raise ValueError("Instagram profile response did not include an account ID.")
        follower_count = safe_int_or_none(profile.get("followers_count"))
        posts = []
        for item in media:
            media_type = str(item.get("media_type") or "IMAGE").upper()
            is_reel = media_type in {"REEL", "VIDEO"}
            creator_post = CreatorPostAIInput(
                post_id=str(item.get("id") or ""), creator_id=account_id, platform="instagram",
                post_type="REEL" if is_reel else "IMAGE", media_url=str(item.get("media_url") or ""),
                thumbnail_url=str(item.get("thumbnail_url") or ""), caption_text=str(item.get("caption") or ""),
                likes=safe_int_or_none(item.get("like_count")) or 0,
                comments=safe_int_or_none(item.get("comments_count")) or 0,
                views=safe_int_or_none(item.get("views")), posted_at=item.get("timestamp"),
            )
            reach = safe_int_or_none(item.get("reach"))
            likes, comments = creator_post.likes, creator_post.comments
            saves = safe_int_or_none(item.get("saves"))
            shares = safe_int_or_none(item.get("shares"))
            engagements = likes + comments + (saves or 0) + (shares or 0)
            posts.append(build_seed_post_from_creator_post(
                creator_post, account_id=account_id, follower_count=follower_count,
                core_metrics_overrides={"reach": reach, "impressions": safe_int_or_none(item.get("impressions")),
                    "likes": likes, "comments": comments, "saves": saves, "shares": shares,
                    "profile_visits": safe_int_or_none(item.get("profile_visits"))},
                derived_metrics_overrides={"engagement_rate": (engagements / reach) if reach else None,
                    "watch_through_rate": safe_float_or_none(item.get("watch_through_rate"))},
            ))
        return NormalizedAccountPayload(source_type=self.source_type, source_ref=account_id,
            source_meta={"insights_enriched": True, "account_insights_enriched": True}, account_id=account_id,
            username=profile.get("username"), bio=profile.get("biography"), follower_count=follower_count,
            account_insights=account_insights, posts=posts)
