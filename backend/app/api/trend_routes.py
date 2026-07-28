"""Routes for trend analysis endpoints."""

from __future__ import annotations

import asyncio
import os
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


from backend.app.domain.post_models import SinglePostInsights
from backend.app.domain.account_models import CreatorIntelligence
from backend.app.domain.trend_models import ResolvedAccount, TrendAnalysisResult
from backend.app.infra.database import get_db
from backend.app.infra.models import AccountAnalysisResult, CreatorDiscoveryMeta, CreatorTrendResult
from backend.app.infra.redis_client import aincr_with_expire
from backend.app.services.account_ai_intelligence import generate_creator_intelligence
from backend.app.services.creator_trend_service import CreatorTrendService, attach_weekly_opportunity
from backend.app.services.draft_history_service import DraftHistoryContext, load_draft_history_context
from backend.app.services.trend_cache import TrendAnalysisCache
from backend.app.services.trend_queue_helper import get_trend_analysis_job_status
from backend.app.utils.env import is_production_environment
from backend.app.utils.logger import logger
from backend.app.utils.telemetry import emit_counter, emit_histogram, timed


router = APIRouter(prefix="/api/v1/accounts", tags=["trends"])

_DEFAULT_TRENDS_REFRESH_LIMIT = 3
_HIGH_TEST_REFRESH_LIMIT = 100


def _get_trends_refresh_limit() -> int:
    configured = (os.getenv("TREND_REFRESH_RATE_LIMIT") or "").strip()
    if configured:
        try:
            parsed = int(configured)
            if parsed > 0:
                return parsed
        except ValueError:
            logger.warning("[TrendRoutes] Invalid TREND_REFRESH_RATE_LIMIT=%r; using default.", configured)

    allow_high_limit = (os.getenv("TREND_REFRESH_ALLOW_HIGH_LIMIT_FOR_TESTS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if allow_high_limit and not is_production_environment():
        return _HIGH_TEST_REFRESH_LIMIT
    return _DEFAULT_TRENDS_REFRESH_LIMIT


def _fallback_history_context(account_id: str) -> DraftHistoryContext:
    return DraftHistoryContext(
        historical_posts=[],
        account_data={
            "account_id": account_id,
            "username": account_id,
            "bio": f"Creator account {account_id}",
        },
    )


@router.get("/resolve", response_model=ResolvedAccount)
async def resolve_account_query(
    query: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> ResolvedAccount:
    """Resolve a user-entered account search query to a canonical account record."""
    raw_query = (query or "").strip()
    normalized_query = raw_query.lstrip("@").strip()
    lowered_query = normalized_query.lower()

    if not normalized_query:
        return ResolvedAccount(query=raw_query, resolved=False, reason="empty_query")

    creator_stmt = (
        select(CreatorDiscoveryMeta)
        .where(
            or_(
                CreatorDiscoveryMeta.account_id == normalized_query,
                func.lower(func.coalesce(CreatorDiscoveryMeta.username, "")) == lowered_query,
            )
        )
        .limit(1)
    )
    creator_match = (await db.execute(creator_stmt)).scalar_one_or_none()
    if creator_match is not None:
        return ResolvedAccount(
            query=raw_query,
            resolved=True,
            account_id=creator_match.account_id,
            username=creator_match.username or normalized_query,
            display_name=creator_match.username or creator_match.account_id,
        )

    analysis_stmt = (
        select(AccountAnalysisResult)
        .where(
            or_(
                AccountAnalysisResult.account_id == normalized_query,
                func.lower(func.coalesce(AccountAnalysisResult.username, "")) == lowered_query,
            )
        )
        .order_by(AccountAnalysisResult.updated_at.desc())
        .limit(1)
    )
    analysis_match = (await db.execute(analysis_stmt)).scalar_one_or_none()
    if analysis_match is not None:
        return ResolvedAccount(
            query=raw_query,
            resolved=True,
            account_id=analysis_match.account_id,
            username=analysis_match.username or normalized_query,
            display_name=analysis_match.username or analysis_match.account_id,
        )

    return ResolvedAccount(
        query=raw_query,
        resolved=False,
        reason="not_found",
    )


@router.get("/{account_id}/trends", response_model=TrendAnalysisResult | dict)
async def get_trends(
    account_id: str,
    db: AsyncSession = Depends(get_db),
) -> TrendAnalysisResult | dict:
    """Return trend analysis and recommendations from DB, or trigger refresh if missing."""
    with timed("trends_endpoint_latency_seconds", account_id=account_id, operation="get"):
        result = await _get_trends_inner(account_id, db)
    return result


async def _get_trends_inner(account_id: str, db: AsyncSession) -> TrendAnalysisResult | dict:
    try:
        row = await db.get(CreatorTrendResult, account_id)
    except Exception:
        logger.warning(
            "[TrendRoutes] DB lookup failed for account=%s; computing transient trend result",
            account_id,
            exc_info=True,
        )
        return await refresh_trends(account_id=account_id, db=db)

    if row is not None:
        try:
            payload: dict[str, Any] = {
                "niche": row.niche_json if isinstance(row.niche_json, dict) else {},
                "global_trends": row.global_trends_json or [],
                "recommendations": row.recommendations_json or [],
                "content_gaps": row.content_gaps_json or [],
                "daily_insights": row.daily_insights_json if isinstance(row.daily_insights_json, dict) else None,
                "opportunity_bullets": row.opportunity_bullets_json or [],
            }
            return attach_weekly_opportunity(TrendAnalysisResult.model_validate(payload))
        except Exception:
            logger.exception("[TrendRoutes] Failed to deserialize stored trend result for account=%s", account_id)
            raise HTTPException(status_code=500, detail="Failed to parse stored trend result")

    # Missing: trigger a refresh and return its result
    return await refresh_trends(account_id=account_id, db=db, count=5)


@router.post("/{account_id}/trends/refresh", response_model=TrendAnalysisResult | dict)
async def refresh_trends(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    count: int = Query(default=5, ge=1, le=10, description="Number of trend recommendations to return"),
) -> TrendAnalysisResult | dict:
    """Force a recalculation of trends. Limited to 1 per 30 minutes."""

    degraded_reasons: list[str] = []

    # 1. Rate limit
    refresh_limit = _get_trends_refresh_limit()
    try:
        rate_count = await aincr_with_expire(f"rate_limit:trends_refresh:{account_id}", 1800)
    except Exception:
        logger.warning(
            "[TrendRoutes] Redis rate check failed for account=%s; continuing without rate limit",
            account_id,
            exc_info=True,
        )
        degraded_reasons.append("rate_limit_unavailable")
        rate_count = 1

    if rate_count > refresh_limit:
        logger.warning(
            "[TrendRoutes] Rate limit exceeded for account=%s — returning 429",
            account_id,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many refresh requests. Please try again in 30 minutes.",
        )

    # 2. Load draft/history context
    try:
        history_context = await asyncio.to_thread(load_draft_history_context, account_id)
    except Exception:
        logger.warning(
            "[TrendRoutes] Failed to load history for account=%s; using transient fallback context",
            account_id,
            exc_info=True,
        )
        history_context = _fallback_history_context(account_id)
        degraded_reasons.append("history_context_fallback")

    posts = history_context.historical_posts

    # 3. Check cache first
    try:
        cached_result = await TrendAnalysisCache.aget(account_id, posts)
        if cached_result:
            logger.info("[TrendRoutes] Returned cached result for account=%s", account_id)
            return attach_weekly_opportunity(cached_result)
    except Exception as exc:
        logger.warning("[TrendRoutes] Cache check failed: %s", exc)
        # Continue without cache

    # 4. Build real creator intelligence from actual post data + bio
    logger.info("[TrendRoutes] Building creator intelligence for account=%s", account_id)
    try:
        creator_intelligence = await generate_creator_intelligence(
            posts=posts,
            account_id=account_id,
            username=history_context.account_data.get("username"),
            bio=history_context.account_data.get("bio"),
            niche_tags=history_context.account_data.get("niche_tags") or [],
            creator_dominant_category=history_context.account_data.get("creator_dominant_category"),
            follower_count=history_context.account_data.get("follower_count"),
        )
        logger.info(
            "[TrendRoutes] Creator intelligence built for account=%s (style=%s)",
            account_id,
            bool(creator_intelligence.content_style_summary),
        )
    except Exception:
        logger.warning(
            "[TrendRoutes] Could not build creator intelligence for account=%s; using heuristic fallback",
            account_id,
            exc_info=True,
        )
        creator_intelligence = CreatorIntelligence()
        degraded_reasons.append("creator_intelligence_fallback")

    # Run service
    service = CreatorTrendService()
    try:
        result = await service.get_trends_and_recommendations(
            account_id=account_id,
            posts=posts,
            bio=history_context.account_data.get("bio"),
            username=history_context.account_data.get("username"),
            creator_intelligence=creator_intelligence,
            recommendation_count=int(count) if isinstance(count, (int, float, str)) else 5,
        )
        result = attach_weekly_opportunity(result)
    except Exception:
        logger.exception("[TrendRoutes] Trend service failed for account=%s", account_id)
        raise HTTPException(status_code=500, detail="Failed to compute trends")

    # 5. Cache the result
    try:
        await TrendAnalysisCache.aset(account_id, posts, result)
        logger.debug("[TrendRoutes] Cached result for account=%s", account_id)
    except Exception as exc:
        logger.warning("[TrendRoutes] Failed to cache result: %s", exc)

    # 6. Upsert into CreatorTrendResult
    try:
        existing = await db.get(CreatorTrendResult, account_id)
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
            db.add(new_row)
        else:
            existing.niche_json = niche_payload
            existing.global_trends_json = global_trends_payload
            existing.recommendations_json = recommendations_payload
            existing.content_gaps_json = content_gaps_payload
            existing.daily_insights_json = daily_insights_payload
            existing.opportunity_bullets_json = opportunity_bullets_payload
            db.add(existing)
        await db.commit()
    except Exception:
        logger.warning(
            "[TrendRoutes] Failed to upsert trend result for account=%s; returning transient result",
            account_id,
            exc_info=True,
        )

    if degraded_reasons:
        payload = result.model_dump(mode="python")
        payload["_meta"] = {
            "degraded": True,
            "degraded_reasons": degraded_reasons,
        }
        return payload

    return result

@router.get("/{account_id}/trends/job/{job_id}")
async def get_trend_job_status(
    account_id: str,
    job_id: str,
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
