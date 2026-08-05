"""Background job definitions for trend analysis."""

from __future__ import annotations

import asyncio
from backend.app.services.account_ai_intelligence import generate_creator_intelligence
from backend.app.services.creator_trend_service import CreatorTrendService, TrendDataUnavailableError, attach_weekly_opportunity
from backend.app.services.draft_history_service import load_draft_history_context
from backend.app.services.trend_cache import TrendAnalysisCache
from backend.app.services.trend_result_store import upsert_trend_result_sync
from backend.app.utils.logger import logger


def _run_async(coro):
    return asyncio.run(coro)


def run_trend_analysis(account_id: str) -> dict:
    """Background job: Perform trend analysis for a creator.
    
    This job:
    1. Loads draft history
    2. Discovers creator niche
    3. Fetches global trends
    4. Generates recommendations
    5. Caches and stores result
    
    Args:
        account_id: Creator's account ID
        
    Returns:
        dict with status and result or error details
        
    Raises:
        Exception: On unexpected errors (RQ will handle retry)
    """
    logger.info(f"[TrendAnalysisJob] Starting for account={account_id}")

    try:
        # Load draft history
        logger.debug(f"[TrendAnalysisJob] Loading draft history for account={account_id}")
        history_context = load_draft_history_context(account_id)
        posts = history_context.historical_posts
        bio = history_context.account_data.get("bio")
        username = history_context.account_data.get("username")

        cached_result = TrendAnalysisCache.get(account_id, posts)
        if cached_result is not None:
            cached_result = attach_weekly_opportunity(cached_result)
            upsert_trend_result_sync(account_id, cached_result)
            logger.info(f"[TrendAnalysisJob] Reused cache for account={account_id}")
            return {
                "status": "success",
                "account_id": account_id,
                "result": cached_result.model_dump(mode="python"),
            }

        # Build real creator intelligence from account data
        logger.debug(f"[TrendAnalysisJob] Building creator intelligence for account={account_id}")
        creator_intelligence = _run_async(generate_creator_intelligence(
            posts=posts,
            account_id=account_id,
            username=username,
            bio=bio,
            niche_tags=history_context.account_data.get("niche_tags") or [],
            creator_dominant_category=history_context.account_data.get("creator_dominant_category"),
            follower_count=history_context.account_data.get("follower_count"),
        ))

        # Use the same orchestrator as the synchronous endpoint so queued jobs include
        # recommendations, opportunities, and insights with the current schema.
        logger.debug(f"[TrendAnalysisJob] Building trend result for account={account_id}")
        result = _run_async(CreatorTrendService().get_trends_and_recommendations(
            account_id=account_id,
            posts=posts,
            bio=bio,
            username=username,
            creator_intelligence=creator_intelligence,
            recommendation_count=5,
        ))
        result = attach_weekly_opportunity(result)
        TrendAnalysisCache.set(account_id, posts, result)

        # Upsert to database
        logger.debug(f"[TrendAnalysisJob] Upserting to database for account={account_id}")
        upsert_trend_result_sync(account_id, result)

        logger.info(f"[TrendAnalysisJob] Completed successfully for account={account_id}")
        return {
            "status": "success",
            "account_id": account_id,
            "result": result.model_dump(mode="python")
        }
    except TrendDataUnavailableError as exc:
        logger.warning(f"[TrendAnalysisJob] Trend data unavailable for account={account_id}: {exc}")
        raise
    except Exception as exc:
        logger.exception(f"[TrendAnalysisJob] Failed for account={account_id}: {exc}")
        raise


