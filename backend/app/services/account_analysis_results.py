"""Result assembly helpers for account analysis jobs."""

from __future__ import annotations

from typing import Any

from backend.app.domain.post_models import SinglePostInsights


def pipeline_result_payload(
    *,
    processed_posts: list[SinglePostInsights],
    warnings: list[dict[str, Any]],
    per_post_warnings_count: dict[str, int],
    vision_error_count: int,
    ai_fallback_count: int,
    notes_by_post_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "posts": processed_posts,
        "warnings": warnings,
        "per_post_warnings_count": per_post_warnings_count,
        "vision_error_count": int(vision_error_count),
        "ai_fallback_count": int(ai_fallback_count),
        "notes_by_post_id": notes_by_post_id,
    }


def draft_optimizer_history(posts: list[SinglePostInsights], limit: int = 12) -> list[dict[str, Any]]:
    ordered_posts = sorted(
        posts,
        key=lambda post: (
            post.published_at.isoformat() if post.published_at is not None else "",
            str(post.media_id or ""),
        ),
        reverse=True,
    )
    return [post.model_dump(mode="json") for post in ordered_posts[:limit]]