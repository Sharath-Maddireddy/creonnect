"""Routes for trend analysis endpoints."""

from __future__ import annotations

import asyncio
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.instagram_auth_routes import get_current_instagram_user
from backend.app.domain.post_models import SinglePostInsights
from backend.app.domain.account_models import CreatorIntelligence
from backend.app.domain.trend_models import TrendAnalysisResult
from backend.app.infra.database import get_db
from backend.app.infra.models import CreatorTrendResult
from backend.app.infra.redis_client import aincr_with_expire
from backend.app.services.creator_trend_service import CreatorTrendService
from backend.app.services.draft_history_service import load_draft_history_context
from backend.app.services.trend_cache import TrendAnalysisCache
from backend.app.services.trend_queue_helper import enqueue_trend_analysis_job, get_trend_analysis_job_status
from backend.app.utils.logger import logger


router = APIRouter(prefix="/api/v1/accounts", tags=["trends"])


@router.get("/{account_id}/trends", response_model=TrendAnalysisResult | dict)
async def get_trends(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_instagram_user),
) -> TrendAnalysisResult | dict:
    """Return trend analysis and recommendations from DB, or trigger refresh if missing."""
    try:
        row = await db.get(CreatorTrendResult, account_id)
    except Exception:
        logger.exception("[TrendRoutes] DB lookup failed for account=%s", account_id)
        raise HTTPException(status_code=500, detail="Failed to load trend result from DB")

    if row is not None:
        try:
            payload: dict[str, Any] = {
                "niche": row.niche_json if isinstance(row.niche_json, dict) else {},
                "global_trends": row.global_trends_json or [],
                "recommendations": row.recommendations_json or [],
            }
            return TrendAnalysisResult.model_validate(payload)
        except Exception:
            logger.exception("[TrendRoutes] Failed to deserialize stored trend result for account=%s", account_id)
            raise HTTPException(status_code=500, detail="Failed to parse stored trend result")

    # Missing: trigger a refresh and return its result
    return await refresh_trends(account_id=account_id, db=db, current_user=current_user)


@router.post("/{account_id}/trends/refresh", response_model=TrendAnalysisResult | dict)
async def refresh_trends(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_instagram_user),
) -> TrendAnalysisResult | dict:
    """Force a recalculation of trends. Limited to 1 per 30 minutes.
    
    Returns TrendAnalysisResult if computed synchronously (cache hit or fast path),
    or dict with job_id if queued asynchronously.
    """
    # 1. Rate limit
    try:
        count = await aincr_with_expire(f"rate_limit:trends_refresh:{account_id}", 1800)
    except Exception:
        logger.exception("[TrendRoutes] Redis rate check failed for account=%s", account_id)
        raise HTTPException(status_code=500, detail="Rate check failed")

    if count > 1:
        logger.warning(
            "[TrendRoutes] Rate limit exceeded for account=%s "
            "(this is now queued instead of rejected)",
            account_id
        )
        # Instead of returning 429, queue the job for later processing
        # This allows the user to check status rather than being rejected

    # 2. Load draft/history context
    try:
        history_context = await asyncio.to_thread(load_draft_history_context, account_id)
    except Exception:
        logger.exception("[TrendRoutes] Failed to load history for account=%s", account_id)
        raise HTTPException(status_code=500, detail="Failed to load historical context")

    posts = history_context.historical_posts

    # 3. Check cache first
    try:
        cached_result = TrendAnalysisCache.get(account_id, posts)
        if cached_result:
            logger.info("[TrendRoutes] Returned cached result for account=%s", account_id)
            return cached_result
    except Exception as exc:
        logger.warning("[TrendRoutes] Cache check failed: %s", exc)
        # Continue without cache

    # 4. If rate-limited (count > 1), queue instead of blocking
    if count > 1:
        logger.info("[TrendRoutes] Queueing trend analysis for account=%s (rate-limited)", account_id)
        try:
            job = enqueue_trend_analysis_job(account_id)
            return {
                "status": "queued",
                "job_id": job.id,
                "message": "Trend analysis queued. Check status with GET /trends/job/{job_id}"
            }
        except Exception:
            logger.exception("[TrendRoutes] Failed to enqueue job for account=%s", account_id)
            raise HTTPException(status_code=500, detail="Failed to queue trend analysis")

    # 5. If not rate-limited, compute synchronously (fast path for first request)
    logger.info("[TrendRoutes] Computing trends synchronously for account=%s", account_id)

    # Creator intelligence stub
    mock_creator_intelligence = CreatorIntelligence()

    # Run service
    service = CreatorTrendService()
    try:
        result = await service.get_trends_and_recommendations(
            account_id=account_id,
            posts=posts,
            bio=history_context.account_data.get("bio"),
            username=history_context.account_data.get("username"),
            creator_intelligence=mock_creator_intelligence,
        )
    except Exception:
        logger.exception("[TrendRoutes] Trend service failed for account=%s", account_id)
        raise HTTPException(status_code=500, detail="Failed to compute trends")

    # 6. Cache the result
    try:
        TrendAnalysisCache.set(account_id, posts, result)
        logger.debug("[TrendRoutes] Cached result for account=%s", account_id)
    except Exception as exc:
        logger.warning("[TrendRoutes] Failed to cache result: %s", exc)

    # 7. Upsert into CreatorTrendResult
    try:
        existing = await db.get(CreatorTrendResult, account_id)
        niche_payload = result.niche.model_dump(mode="python") if hasattr(result.niche, "model_dump") else {}
        global_trends_payload = [t.model_dump(mode="python") for t in result.global_trends]
        recommendations_payload = [r.model_dump(mode="python") for r in result.recommendations]

        if existing is None:
            new_row = CreatorTrendResult(
                account_id=account_id,
                niche_json=niche_payload,
                global_trends_json=global_trends_payload,
                recommendations_json=recommendations_payload,
            )
            db.add(new_row)
        else:
            existing.niche_json = niche_payload
            existing.global_trends_json = global_trends_payload
            existing.recommendations_json = recommendations_payload
            db.add(existing)
        await db.commit()
    except Exception:
        logger.exception("[TrendRoutes] Failed to upsert trend result for account=%s", account_id)
        raise HTTPException(status_code=500, detail="Failed to save trend result")

    return result


@router.get("/{account_id}/trends/job/{job_id}")
async def get_trend_job_status(
    account_id: str,
    job_id: str,
    current_user=Depends(get_current_instagram_user),
) -> dict:
    """Poll status of a queued trend analysis job.
    
    Returns:
    - {"status": "queued", "job_id": "..."}
    - {"status": "processing", "job_id": "..."}
    - {"status": "completed", "job_id": "...", "result": {...}}
    - {"status": "failed", "job_id": "...", "error": "..."}
    """
    status_info = get_trend_analysis_job_status(job_id)
    return status_info



