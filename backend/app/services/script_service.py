"""Script generation service."""

from __future__ import annotations

from backend.app.ai.niche import detect_creator_niche
from backend.app.demo.synthetic_loader import load_synthetic
from backend.app.services.creator_pool_service import get_all_creators
from backend.core.script_generator import generate_reel_script


def _build_top_post(posts: list) -> dict | None:
    if not posts:
        return None
    sorted_posts = sorted(
        posts,
        key=lambda p: (p.likes + p.comments) / max(p.views or 1, 1),
        reverse=True,
    )
    if not sorted_posts:
        return None
    best = sorted_posts[0]
    return {
        "caption": best.caption_text,
        "likes": best.likes,
        "comments": best.comments,
        "views": best.views or 0,
    }


def generate_creator_script_service(creator_id: str) -> dict:
    """Generate a reel script for a creator ID or demo profile."""
    profile, posts = load_synthetic()

    if profile.username == creator_id or creator_id == "demo":
        try:
            niche = detect_creator_niche(profile, posts)
        except Exception:
            niche = {"primary_niche": "general"}
        creator_data = {
            "username": profile.username,
            "followers": profile.followers_count,
            "bio": profile.bio_text,
        }
        return generate_reel_script(
            creator_profile=creator_data,
            niche_scores=niche,
            top_post=_build_top_post(posts),
        )

    creators = get_all_creators()
    creator = next(
        (
            item
            for item in creators
            if item.get("account_id") == creator_id or item.get("username") == creator_id
        ),
        None,
    )
    if creator is None:
        raise ValueError("Creator not found")

    creator_data = {
        "username": creator.get("username") or creator.get("account_id") or "creator",
        "followers": int(creator.get("follower_count") or 0),
        "bio": creator.get("bio") or "",
    }
    niche_scores = {
        "primary_niche": creator.get("creator_dominant_category") or "general",
    }

    return generate_reel_script(
        creator_profile=creator_data,
        niche_scores=niche_scores,
        top_post=None,
    )
