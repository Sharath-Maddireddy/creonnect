"""Background job definitions for trend analysis.

This module defines RQ jobs for async trend processing.
Allows trend analysis to be queued instead of synchronous,
preventing rate limit rejections and improving scalability.
"""

from __future__ import annotations

from typing import List
from datetime import datetime

import asyncio
from backend.app.analytics.niche_discovery_engine import discover_creator_niche
from backend.app.analytics.global_trend_engine import fetch_global_trends
from backend.app.analytics.trend_recommendation_engine import generate_trend_recommendations
from backend.app.domain.post_models import SinglePostInsights
from backend.app.domain.trend_models import TrendAnalysisResult
from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import CreatorTrendResult
from backend.app.services.account_ai_intelligence import generate_creator_intelligence
from backend.app.services.draft_history_service import load_draft_history_context
from backend.app.services.trend_cache import TrendAnalysisCache
from backend.app.utils.logger import logger


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

        # Build real creator intelligence from account data
        logger.debug(f"[TrendAnalysisJob] Building creator intelligence for account={account_id}")
        creator_intelligence = asyncio.run(generate_creator_intelligence(
            posts=posts,
            account_id=account_id,
            username=username,
            bio=bio,
            niche_tags=history_context.account_data.get("niche_tags") or [],
            creator_dominant_category=history_context.account_data.get("creator_dominant_category"),
            follower_count=history_context.account_data.get("follower_count"),
        ))

        # Discover niche
        logger.debug(f"[TrendAnalysisJob] Discovering niche for account={account_id}")
        niche = asyncio.run(discover_creator_niche(posts, bio, username))

        # Fetch global trends
        logger.debug(f"[TrendAnalysisJob] Fetching trends for account={account_id}")
        trends = asyncio.run(fetch_global_trends(niche))

        # Generate recommendations
        logger.debug(f"[TrendAnalysisJob] Generating recommendations for account={account_id}")
        recs = asyncio.run(generate_trend_recommendations(creator_intelligence, trends))

        # Build result
        result = TrendAnalysisResult(niche=niche, global_trends=trends, recommendations=recs)

        # Cache result
        logger.debug(f"[TrendAnalysisJob] Caching result for account={account_id}")
        TrendAnalysisCache.set(account_id, posts, result)

        # Upsert to database
        logger.debug(f"[TrendAnalysisJob] Upserting to database for account={account_id}")
        _upsert_trend_result(account_id, result)

        logger.info(f"[TrendAnalysisJob] Completed successfully for account={account_id}")
        return {
            "status": "success",
            "account_id": account_id,
            "result": result.model_dump(mode="python")
        }
    except Exception as exc:
        logger.exception(f"[TrendAnalysisJob] Failed for account={account_id}: {exc}")
        raise

def _upsert_trend_result(account_id: str, result: TrendAnalysisResult) -> None:
    """Upsert trend result to database (synchronous, using session factory).
    
    Args:
        account_id: Creator's account ID
        result: TrendAnalysisResult to store
    """
    session_factory = get_sync_sessionmaker()

    with session_factory() as session:
        existing = session.get(CreatorTrendResult, account_id)

        niche_payload = result.niche.model_dump(mode="python") if hasattr(result.niche, "model_dump") else {}
        global_trends_payload = [t.model_dump(mode="python") for t in result.global_trends]
        recommendations_payload = [r.model_dump(mode="python") for r in result.recommendations]
        content_gaps_payload = [g.model_dump(mode="python") for g in result.content_gaps] if result.content_gaps else []
        daily_insights_payload = result.daily_insights.model_dump(mode="python") if result.daily_insights and hasattr(result.daily_insights, "model_dump") else None
        opportunity_bullets_payload = result.opportunity_bullets if result.opportunity_bullets else []

        if existing is None:
            new_row = CreatorTrendResult(
                account_id=account_id,
                niche_json=niche_payload,
                global_trends_json=global_trends_payload,
                recommendations_json=recommendations_payload,
                content_gaps_json=content_gaps_payload,
                daily_insights_json=daily_insights_payload,
                opportunity_bullets_json=opportunity_bullets_payload,
            )
            session.add(new_row)
        else:
            existing.niche_json = niche_payload
            existing.global_trends_json = global_trends_payload
            existing.recommendations_json = recommendations_payload
            existing.content_gaps_json = content_gaps_payload
            existing.daily_insights_json = daily_insights_payload
            existing.opportunity_bullets_json = opportunity_bullets_payload
            session.add(existing)

        session.commit()
        logger.debug(f"[TrendAnalysisJob] Upserted to database for account={account_id}")


