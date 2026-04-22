"""
Dashboard Service

Orchestrates creator dashboard data assembly.
"""

import asyncio
from datetime import date, timedelta

from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.demo.synthetic_loader import load_synthetic
from backend.app.ingestion.instagram_mapper import map_instagram_to_ai_inputs
from backend.app.ingestion.instagram_oauth import (
    fetch_instagram_media,
    fetch_instagram_profile,
)
from backend.app.analytics.account_health_engine import compute_account_health_score
from backend.app.ai.niche import detect_creator_niche
from backend.app.ai.growth_score import compute_growth_score
from backend.app.ai.post_insights import analyze_posts
from backend.app.ai.rag import retrieve, generate_action_plan
from backend.core.snapshots import build_creator_snapshot
from backend.core.momentum import calculate_momentum
from backend.core.best_time import get_best_posting_hours
from backend.app.domain.post_models import DerivedMetrics
from backend.app.services.post_insights_service import _coerce_single_post_insights


def _placeholder_media_url(post_id: str | None, size: int = 800) -> str:
    token = post_id or "creonnect-post"
    return f"https://placehold.co/{size}x{size}?text={token}"


def _resolve_follower_band(follower_count: int | None) -> str | None:
    if follower_count is None or follower_count < 0:
        return None
    if follower_count < 10_000:
        return "0-10k"
    if follower_count < 100_000:
        return "10k-100k"
    if follower_count < 1_000_000:
        return "100k-1M"
    return "1M+"


def _safe_rate(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_creator_dashboard(creator_id: str, access_token: str | None = None) -> dict:
    """
    Build the full creator dashboard response.

    Raises:
        ValueError: if creator not found
    """
    if access_token:
        async def _fetch_instagram_data():
            api_profile, api_media = await asyncio.gather(
                fetch_instagram_profile(access_token),
                fetch_instagram_media(access_token, limit=30),
            )
            return map_instagram_to_ai_inputs(api_profile, api_media)

        profile, posts = asyncio.run(_fetch_instagram_data())
    else:
        profile, posts = load_synthetic()

        if profile.username != creator_id and creator_id != "demo":
            raise ValueError("Creator not found")

    niche = detect_creator_niche(profile, posts)
    growth = compute_growth_score(profile, posts)
    post_insights = analyze_posts(profile, posts)
    dashboard_posts = []

    # Time-series for charts
    engagement_series = []
    views_series = []

    for p, insight in zip(posts, post_insights):
        media_url = p.media_url or _placeholder_media_url(p.post_id, size=800)
        thumbnail_url = p.thumbnail_url or media_url
        engagement_series.append({
            "date": p.posted_at.isoformat() if p.posted_at else None,
            "value": insight.get("engagement_rate_by_views")
        })

        views_series.append({
            "date": p.posted_at.isoformat() if p.posted_at else None,
            "value": p.views
        })

        dashboard_posts.append({
            **insight,
            "post_id": p.post_id,
            "post_type": p.post_type,
            "media_url": media_url,
            "thumbnail_url": thumbnail_url,
            "caption_text": p.caption_text,
            "hashtags": list(p.hashtags) if isinstance(p.hashtags, list) else [],
            "likes": p.likes,
            "comments": p.comments,
            "views": p.views,
            "audio_name": p.audio_name,
            "published_at": p.posted_at.isoformat() if p.posted_at else None,
        })

    # Generate simulated snapshot history for momentum calculation
    # In production, this would come from a database
    today = date.today()
    simulated_snapshots = []
    base_followers = profile.followers_count - 500  # Simulate growth
    for i in range(7):
        day = today - timedelta(days=6 - i)
        simulated_snapshots.append({
            "date": day.isoformat(),
            "followers": base_followers + (i * 80)  # ~80 followers/day growth
        })

    # Calculate momentum
    momentum = calculate_momentum(simulated_snapshots)

    # Calculate best posting times
    posts_for_time_analysis = [
        {
            "created_at": p.posted_at.isoformat() if p.posted_at else None,
            "likes": p.likes,
            "comments": p.comments,
            "views": p.views or 0
        }
        for p in posts
    ]
    best_time = get_best_posting_hours(posts_for_time_analysis)

    # Retrieve knowledge for action plan
    query = f"{niche.get('primary_niche', 'creator')} growth strategies engagement tips"
    knowledge_chunks = retrieve(query, k=3)

    # Generate action plan
    creator_metrics = {
        "followers": profile.followers_count,
        "growth_score": growth["growth_score"],
        "avg_views": growth["metrics"]["avg_views"],
        "avg_engagement_rate_by_views": growth["metrics"]["avg_engagement_rate_by_views"],
        "posts_per_week": growth["metrics"]["posts_per_week"]
    }

    recent_posts = [
        {
            "likes": p.likes,
            "comments": p.comments,
            "views": p.views or 0
        }
        for p in posts[-3:]  # Last 3 posts
    ]

    action_plan = generate_action_plan(
        creator_metrics=creator_metrics,
        niche_data=niche,
        momentum=momentum,
        best_time=best_time,
        recent_posts=recent_posts,
        knowledge_chunks=knowledge_chunks
    )

    # Build snapshot (kept for parity with existing pipeline usage)
    _ = build_creator_snapshot({
        "username": profile.username,
        "followers": profile.followers_count,
        "avg_views": profile.avg_views or 0,
        "avg_likes": profile.avg_likes,
        "avg_comments": profile.avg_comments,
        "growth_score": growth.get("growth_score", 0)
    })

    return {
        "summary": {
            "username": profile.username,
            "followers": profile.followers_count,
            "growth_score": growth["growth_score"],
            "avg_engagement_rate_by_views": growth["metrics"]["avg_engagement_rate_by_views"],
            "avg_views": growth["metrics"]["avg_views"],
            "views_to_followers_ratio": growth["metrics"]["views_to_followers_ratio"],
            "posts_per_week": growth["metrics"]["posts_per_week"],
            "niche": niche,
            "momentum": momentum,
            "best_time_to_post": best_time
        },

        "posts": dashboard_posts,

        "charts": {
            "engagement_over_time": engagement_series,
            "views_over_time": views_series
        },

        "action_plan": action_plan
    }


def build_creator_analytics(creator_id: str, access_token: str | None = None) -> dict:
    """Build dashboard payload plus account-health analytics and content breakdown."""

    payload = build_creator_dashboard(creator_id, access_token=access_token)
    summary = dict(payload.get("summary") or {})
    posts_data = payload.get("posts") if isinstance(payload.get("posts"), list) else []

    followers_value = summary.get("followers")
    try:
        followers_count = int(followers_value) if followers_value is not None else None
    except (TypeError, ValueError):
        followers_count = None
    if followers_count is not None:
        summary["followers"] = followers_count

    single_post_models = []
    for post in posts_data:
        if not isinstance(post, dict):
            continue

        creator_post = CreatorPostAIInput(
            post_id=str(post.get("post_id") or ""),
            creator_id=str(summary.get("username") or creator_id or ""),
            platform="instagram",
            post_type="REEL" if str(post.get("post_type") or "").upper() == "REEL" else "IMAGE",
            media_url=str(post.get("media_url") or ""),
            thumbnail_url=str(post.get("thumbnail_url") or ""),
            caption_text=str(post.get("caption_text") or ""),
            hashtags=[str(item) for item in post.get("hashtags", []) if isinstance(item, str)],
            likes=int(post.get("likes") or 0),
            comments=int(post.get("comments") or 0),
            views=int(post["views"]) if post.get("views") is not None else None,
            audio_name=str(post.get("audio_name")) if isinstance(post.get("audio_name"), str) else None,
            posted_at=post.get("published_at"),
        )
        single_post = _coerce_single_post_insights(creator_post)
        single_post.derived_metrics = DerivedMetrics(
            engagement_rate=_safe_rate(post.get("engagement_rate_by_views")),
            like_rate=_safe_rate(post.get("like_rate")),
            comment_rate=_safe_rate(post.get("comment_rate")),
            engagements_total=int(post.get("total_interactions") or 0),
        )
        single_post_models.append(single_post)

    follower_band = _resolve_follower_band(followers_count)
    account_avg_engagement_rate = _safe_rate(summary.get("avg_engagement_rate_by_views"))
    account_health = compute_account_health_score(
        posts=single_post_models,
        account_avg_engagement_rate=account_avg_engagement_rate,
        niche_avg_engagement_rate=None,
        follower_band=follower_band,
    )

    content_type_breakdown: dict[str, dict[str, float | int | None]] = {}
    for post_type in ("REEL", "IMAGE"):
        matching_posts = [
            post for post in posts_data
            if isinstance(post, dict) and str(post.get("post_type") or "IMAGE").upper() == post_type
        ]
        engagement_values = [
            value for value in (_safe_rate(post.get("engagement_rate_by_views")) for post in matching_posts)
            if value is not None
        ]
        average_engagement = (
            round(sum(engagement_values) / len(engagement_values), 4)
            if engagement_values
            else None
        )
        content_type_breakdown[post_type] = {
            "count": len(matching_posts),
            "avg_engagement_rate": average_engagement,
        }

    enriched_payload = dict(payload)
    enriched_payload["summary"] = summary
    enriched_payload["account_health"] = {
        "ahs_score": account_health.ahs_score,
        "ahs_band": account_health.ahs_band,
        "pillars": {
            key: {
                "score": pillar.score,
                "band": pillar.band,
                "notes": list(pillar.notes),
            }
            for key, pillar in account_health.pillars.items()
        },
        "drivers": [driver.model_dump(mode="python") for driver in account_health.drivers],
        "recommendations": [recommendation.model_dump(mode="python") for recommendation in account_health.recommendations],
        "metadata": account_health.metadata.model_dump(mode="python"),
    }
    enriched_payload["content_type_breakdown"] = content_type_breakdown
    return enriched_payload


