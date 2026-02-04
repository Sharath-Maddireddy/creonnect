from typing import Dict, List
from datetime import datetime, timezone

from backend.app.ai.schemas import (
    CreatorProfileAIInput,
    CreatorPostAIInput
)
from backend.app.ai.rag import retrieve
from backend.app.utils.logger import logger


# ------------------------------------------------
# RAG Query Builder
# ------------------------------------------------

def _build_rag_query(profile: CreatorProfileAIInput, ai_outputs: Dict) -> str:
    """Build a query for RAG retrieval based on creator metrics."""
    parts = []

    # Add niche
    niche_data = ai_outputs.get("niche", {})
    if isinstance(niche_data, dict):
        primary_niche = niche_data.get("primary_niche")
        if primary_niche:
            parts.append(f"{primary_niche} creator")

    # Add growth context
    growth_data = ai_outputs.get("growth", {})
    growth_score = growth_data.get("growth_score", 0)
    if growth_score >= 70:
        parts.append("high growth strategies scaling")
    elif growth_score >= 50:
        parts.append("growth optimization improvement")
    else:
        parts.append("growth fundamentals engagement")

    # Add engagement tier context
    avg_eng = (
        ai_outputs
        .get("growth", {})
        .get("metrics", {})
        .get("avg_engagement_rate_by_views")
    )

    if avg_eng is not None:
        if avg_eng >= 0.05:
            parts.append("high engagement scaling content")
        else:
            parts.append("engagement improvement tactics")

    # Add follower tier context
    followers = profile.followers_count
    if followers >= 100000:
        parts.append("macro influencer brand partnerships")
    elif followers >= 10000:
        parts.append("mid-tier creator monetization")
    else:
        parts.append("micro creator growth community")

    return " ".join(parts)


# ------------------------------------------------
# RAG Context Builder
# ------------------------------------------------

def build_creator_context(
    profile: CreatorProfileAIInput,
    posts: List[CreatorPostAIInput],
    ai_outputs: Dict
) -> Dict:
    """
    Build a structured RAG context for creator explanations.
    Uses PDF-based metrics and retrieves relevant knowledge.
    """

    # Build post summaries with engagement rate for posts that have views
    posts_with_engagement = []
    for post in posts:
        if not post.views or post.views <= 0:
            continue

        engagement_rate = (post.likes + post.comments) / post.views
        post_summary = {
            "post_id": post.post_id,
            "type": post.post_type,
            "likes": post.likes,
            "comments": post.comments,
            "views": post.views,
            "total_interactions": post.likes + post.comments,
            "caption_length": len(post.caption_text.split()) if post.caption_text else 0,
            "engagement_rate_by_views": round(engagement_rate, 4)
        }
        posts_with_engagement.append((engagement_rate, post_summary))

    # Sort by engagement rate and select best + worst for contrast learning
    posts_with_engagement.sort(key=lambda x: x[0])

    recent_posts_summary = []
    if len(posts_with_engagement) == 1:
        recent_posts_summary.append(posts_with_engagement[0][1])
    elif len(posts_with_engagement) >= 2:
        recent_posts_summary.append(posts_with_engagement[-1][1])  # highest
        recent_posts_summary.append(posts_with_engagement[0][1])   # lowest

    # Extract growth score metrics
    growth_data = ai_outputs.get("growth", {})
    growth_metrics = growth_data.get("metrics", {})
    growth_breakdown = growth_data.get("breakdown", {})

    # --- RAG Retrieval ---
    rag_query = _build_rag_query(profile, ai_outputs)
    logger.info(f"[Context] RAG query: {rag_query[:100]}..." if len(rag_query) > 100 else f"[Context] RAG query: {rag_query}")
    retrieved_knowledge = retrieve(rag_query, k=3)
    logger.info(f"[Context] Retrieved {len(retrieved_knowledge)} knowledge chunks")
    context = {
        "generated_at": datetime.now(timezone.utc).isoformat(),

        # Creator snapshot
        "creator_profile": {
            "username": profile.username,
            "platform": profile.platform,
            "followers": profile.followers_count,
            "avg_likes": profile.avg_likes,
            "avg_comments": profile.avg_comments,
            "avg_views": profile.avg_views,
            "posting_frequency_per_week":
                profile.posts_per_week
                if profile.posts_per_week is not None
                else profile.posting_frequency_per_week

        },

        # Deterministic AI outputs (truth)
        "ai_analysis": {
            "niche": ai_outputs.get("niche"),
            "growth_score": growth_data.get("growth_score"),
            "growth_breakdown": growth_breakdown,
            "avg_engagement_rate_by_views": growth_metrics.get("avg_engagement_rate_by_views"),
            "views_to_followers_ratio": growth_metrics.get("views_to_followers_ratio"),
            "post_insights": ai_outputs.get("posts", [])
        },

        # Recent content signals
        "recent_posts": recent_posts_summary,

        # Retrieved knowledge (RAG)
        "retrieved_knowledge": retrieved_knowledge,
    }

    return context
