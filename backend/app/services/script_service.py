"""
Script Service

Generates reel scripts for creators.
"""

from backend.app.demo.synthetic_loader import load_synthetic
from backend.app.ai.niche import detect_creator_niche
from backend.core.script_generator import generate_reel_script


def generate_creator_script_service(creator_id: str) -> dict:
    """
    Generate a reel script for a creator.

    Raises:
        ValueError: if creator not found
    """
    profile, posts = load_synthetic()

    if profile.username != creator_id and creator_id != "demo":
        raise ValueError("Creator not found")

    niche = detect_creator_niche(profile, posts)

    top_post = None
    if posts:
        sorted_posts = sorted(
            posts,
            key=lambda p: (p.likes + p.comments) / max(p.views or 1, 1),
            reverse=True
        )
        if sorted_posts:
            best = sorted_posts[0]
            top_post = {
                "caption": best.caption_text,
                "likes": best.likes,
                "comments": best.comments,
                "views": best.views or 0
            }

    creator_data = {
        "username": profile.username,
        "followers": profile.followers_count,
        "bio": profile.bio_text
    }

    return generate_reel_script(
        creator_profile=creator_data,
        niche_scores=niche,
        top_post=top_post
    )


