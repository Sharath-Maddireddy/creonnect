"""Nightly background jobs."""

from __future__ import annotations

from backend.app.analytics.audience_quality import calculate_authenticity_score
from backend.app.services.creator_pool_service import query_creator_pool
from backend.app.utils.logger import logger


def run_authenticity_refresh_job() -> None:
    """Simulate nightly authenticity score pre-computation for all creators."""
    creators = query_creator_pool()

    for creator in creators:
        username = creator.get("username", "unknown")
        follower_count = int(creator.get("follower_count", 0) or 0)
        avg_views = int(creator.get("avg_views", 0) or 0)
        avg_likes = int(creator.get("avg_likes", 0) or 0)
        avg_comments = int(creator.get("avg_comments", 0) or 0)

        score = calculate_authenticity_score(
            follower_count=follower_count,
            avg_views=avg_views,
            avg_likes=avg_likes,
            avg_comments=avg_comments,
        )
        logger.info(f"Pre-computing authenticity for {username}: Score {score}")


if __name__ == "__main__":
    run_authenticity_refresh_job()
