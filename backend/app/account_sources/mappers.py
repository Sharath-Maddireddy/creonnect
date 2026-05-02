"""Shared mapping helpers from upstream payloads into domain post models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.tools.fixture_to_creator_input import build_creator_post_ai_input_from_fixture


def safe_int_or_none(value: Any) -> int | None:
    """Safely coerce a value to int."""
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float_or_none(value: Any) -> float | None:
    """Safely coerce a value to float."""
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_post_media_type(*, post_type: Any = None, media_type: Any = None) -> str:
    """Return the canonical media type used by analysis."""
    normalized_post_type = str(post_type or "").strip().upper()
    normalized_media_type = str(media_type or "").strip().upper()
    if normalized_post_type in {"REEL", "VIDEO", "CLIPS"}:
        return "REEL"
    if normalized_post_type == "CAROUSEL":
        return "IMAGE"
    if normalized_media_type in {"REEL", "REELS", "VIDEO", "CLIPS"}:
        return "REEL"
    return "IMAGE"


def build_seed_post_from_creator_post(
    creator_post: CreatorPostAIInput,
    *,
    account_id: str,
    follower_count: int | None,
    creator_dominant_category: str | None = None,
    core_metrics_overrides: dict[str, Any] | None = None,
    derived_metrics_overrides: dict[str, Any] | None = None,
) -> SinglePostInsights:
    """Build the canonical seed post used by account analysis."""
    metric_overrides = core_metrics_overrides or {}
    derived_overrides = derived_metrics_overrides or {}
    reach = safe_int_or_none(metric_overrides.get("reach"))
    impressions = safe_int_or_none(metric_overrides.get("impressions"))
    likes = safe_int_or_none(metric_overrides.get("likes"))
    comments = safe_int_or_none(metric_overrides.get("comments"))
    shares = safe_int_or_none(metric_overrides.get("shares"))
    saves = safe_int_or_none(metric_overrides.get("saves"))
    profile_visits = safe_int_or_none(metric_overrides.get("profile_visits"))
    website_taps = safe_int_or_none(metric_overrides.get("website_taps"))
    source_engagement_rate = safe_float_or_none(metric_overrides.get("source_engagement_rate"))

    if reach is None:
        reach = creator_post.views
    if impressions is None:
        impressions = creator_post.views if creator_post.views is not None else reach
    if likes is None:
        likes = creator_post.likes
    if comments is None:
        comments = creator_post.comments

    return SinglePostInsights(
        account_id=account_id,
        media_id=creator_post.post_id,
        media_url=creator_post.media_url or None,
        media_type=normalize_post_media_type(post_type=creator_post.post_type),
        caption_text=creator_post.caption_text,
        post_category=None,
        creator_dominant_category=creator_dominant_category,
        extracted_brand_mentions=[],
        safety_extra_flags={},
        follower_count=follower_count,
        published_at=creator_post.posted_at,
        core_metrics=CoreMetrics(
            reach=reach,
            impressions=impressions,
            likes=likes,
            comments=comments,
            shares=shares,
            saves=saves,
            profile_visits=profile_visits,
            website_taps=website_taps,
            source_engagement_rate=source_engagement_rate,
        ),
        derived_metrics=DerivedMetrics(
            engagement_rate=safe_float_or_none(derived_overrides.get("engagement_rate")),
            save_rate=safe_float_or_none(derived_overrides.get("save_rate")),
            share_rate=safe_float_or_none(derived_overrides.get("share_rate")),
            watch_through_rate=safe_float_or_none(derived_overrides.get("watch_through_rate")),
            swipe_through_rate=safe_float_or_none(derived_overrides.get("swipe_through_rate")),
            like_rate=safe_float_or_none(derived_overrides.get("like_rate")),
            comment_rate=safe_float_or_none(derived_overrides.get("comment_rate")),
            save_to_share_ratio=safe_float_or_none(derived_overrides.get("save_to_share_ratio")),
            profile_visit_rate=safe_float_or_none(derived_overrides.get("profile_visit_rate")),
            website_tap_rate=safe_float_or_none(derived_overrides.get("website_tap_rate")),
            reach_to_impression_ratio=safe_float_or_none(derived_overrides.get("reach_to_impression_ratio")),
            engagements_total=safe_int_or_none(derived_overrides.get("engagements_total")),
        ),
        benchmark_metrics=BenchmarkMetrics(),
    )


def build_seed_post_from_fixture_item(
    fixture_item: dict[str, Any],
    *,
    account_id: str,
    creator_dominant_category: str | None = None,
) -> SinglePostInsights:
    """Build a seed post from one fixture item."""
    creator_post = build_creator_post_ai_input_from_fixture(fixture_item)
    follower_count = safe_int_or_none(fixture_item.get("follower_count"))
    return build_seed_post_from_creator_post(
        creator_post,
        account_id=account_id,
        follower_count=follower_count,
        creator_dominant_category=creator_dominant_category,
        core_metrics_overrides={
            "reach": safe_int_or_none(fixture_item.get("view_count")),
            "impressions": safe_int_or_none(fixture_item.get("view_count")),
            "likes": safe_int_or_none(fixture_item.get("like_count")),
            "comments": safe_int_or_none(fixture_item.get("comment_count")),
        },
    )


def _pick_first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def build_seed_post_from_creonnect_bd_post(
    post_payload: dict[str, Any],
    *,
    account_id: str,
    follower_count: int | None,
    creator_dominant_category: str | None = None,
) -> SinglePostInsights:
    """Build a seed post from the creonnect-bd social posts API payload."""
    latest_metrics = post_payload.get("latestPostMetrics")
    latest_metrics = latest_metrics if isinstance(latest_metrics, dict) else {}
    metrics_core = latest_metrics.get("metrics_core")
    metrics_core = metrics_core if isinstance(metrics_core, dict) else {}
    derived_metrics = latest_metrics.get("derived_metrics")
    derived_metrics = derived_metrics if isinstance(derived_metrics, dict) else {}

    media_type = normalize_post_media_type(
        post_type=post_payload.get("postType"),
        media_type=post_payload.get("mediaType"),
    )
    creator_post = CreatorPostAIInput(
        post_id=str(_pick_first(post_payload, "platformPostId", "id") or ""),
        creator_id=account_id,
        platform="instagram",
        post_type=media_type,
        media_url=str(_pick_first(post_payload, "storagePublicUrl", "sourceMediaUrl") or ""),
        thumbnail_url=str(_pick_first(post_payload, "thumbnailUrl") or ""),
        caption_text=str(post_payload.get("caption") or ""),
        likes=safe_int_or_none(_pick_first(metrics_core, "likes")) or 0,
        comments=safe_int_or_none(_pick_first(metrics_core, "comments")) or 0,
        views=safe_int_or_none(_pick_first(metrics_core, "views", "video_views")),
        posted_at=_parse_datetime(post_payload.get("postedAt")),
    )
    reach = safe_int_or_none(_pick_first(metrics_core, "reach", "views", "video_views"))
    impressions = safe_int_or_none(_pick_first(metrics_core, "impressions", "views", "video_views"))
    if impressions is None:
        impressions = reach

    return build_seed_post_from_creator_post(
        creator_post,
        account_id=account_id,
        follower_count=follower_count,
        creator_dominant_category=creator_dominant_category,
        core_metrics_overrides={
            "reach": reach,
            "impressions": impressions,
            "likes": safe_int_or_none(_pick_first(metrics_core, "likes")),
            "comments": safe_int_or_none(_pick_first(metrics_core, "comments")),
            "shares": safe_int_or_none(_pick_first(metrics_core, "shares")),
            "saves": safe_int_or_none(_pick_first(metrics_core, "saves")),
            "profile_visits": safe_int_or_none(_pick_first(metrics_core, "profile_visits", "profile_visits_total")),
            "website_taps": safe_int_or_none(_pick_first(metrics_core, "website_taps", "profile_links_taps")),
            "source_engagement_rate": safe_float_or_none(_pick_first(metrics_core, "engagement_rate")),
        },
        derived_metrics_overrides=derived_metrics,
    )
