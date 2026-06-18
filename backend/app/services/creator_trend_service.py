from __future__ import annotations

"""Orchestration service that runs niche discovery, global trend fetching,
and recommendation generation for a creator.
"""

from typing import List

from backend.app.analytics.niche_discovery_engine import discover_creator_niche
from backend.app.analytics.global_trend_engine import fetch_global_trends
from backend.app.analytics.trend_recommendation_engine import generate_trend_recommendations
from backend.app.domain.post_models import SinglePostInsights
from backend.app.domain.account_models import CreatorIntelligence
from backend.app.domain.trend_models import TrendAnalysisResult
from backend.app.utils.logger import logger


class CreatorTrendService:
    """Service to produce trend analysis results for a creator.

    Usage:
        service = CreatorTrendService()
        result = await service.get_trends_and_recommendations(...)
    """

    async def get_trends_and_recommendations(
        self,
        account_id: str,
        posts: List[SinglePostInsights],
        bio: str | None,
        username: str | None,
        creator_intelligence: CreatorIntelligence,
    ) -> TrendAnalysisResult:
        """Run the full trend analysis pipeline and return consolidated results.

        The workflow:
        1. discover_creator_niche
        2. fetch_global_trends
        3. generate_trend_recommendations

        Logs progress and raises a RuntimeError on unexpected orchestration errors.
        """

        logger.info("[CreatorTrendService] Starting trend analysis for account=%s", account_id)

        try:
            niche = await discover_creator_niche(posts, bio, username)
            trends = await fetch_global_trends(niche)
            recs = await generate_trend_recommendations(creator_intelligence, trends)

            result = TrendAnalysisResult(niche=niche, global_trends=trends, recommendations=recs)
            logger.info("[CreatorTrendService] Completed trend analysis for account=%s", account_id)
            return result

        except Exception as exc:
            logger.error("[CreatorTrendService] Orchestration failed for account=%s: %s", account_id, exc)
            raise RuntimeError("Creator trend orchestration failed") from exc


__all__ = ["CreatorTrendService"]
