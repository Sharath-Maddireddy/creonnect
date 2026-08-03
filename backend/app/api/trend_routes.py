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
from backend.app.domain.trend_models import ResolvedAccount, TrendAnalysisResult, TrendingTopicDetail
from backend.app.infra.database import get_db
from backend.app.api.instagram_auth_routes import require_current_account
from backend.app.infra.models import AccountAnalysisResult, CreatorDiscoveryMeta, CreatorTrendResult
from backend.app.infra.redis_client import aincr_with_expire
from backend.app.services.account_ai_intelligence import generate_creator_intelligence
from backend.app.services.creator_trend_service import CreatorTrendService, attach_weekly_opportunity
from backend.app.services.draft_history_service import DraftHistoryContext, load_draft_history_context
from backend.app.services.trend_queue_helper import get_trend_analysis_job_status
from backend.app.utils.env import is_production_environment
from backend.app.utils.logger import logger
from backend.app.utils.telemetry import emit_counter, emit_histogram, timed


router = APIRouter(
    prefix="/api/v1/accounts",
    tags=["trends"],
    dependencies=[Depends(require_current_account)],
)

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


def _normalize_trend_result(payload: TrendAnalysisResult | dict[str, Any]) -> TrendAnalysisResult:
    if isinstance(payload, TrendAnalysisResult):
        return payload
    if isinstance(payload, dict):
        cleaned = {key: value for key, value in payload.items() if key != "_meta"}
        cleaned["global_trends"] = [
            trend for trend in cleaned.get("global_trends", [])
            if not isinstance(trend, dict) or str(trend.get("trend_type") or "").lower() != "audio"
        ]
        return TrendAnalysisResult.model_validate(cleaned)
    raise HTTPException(status_code=500, detail="Unexpected trend payload")


def _without_dismissed_opportunities(result: TrendAnalysisResult, dismissed_ids: list[str] | None) -> TrendAnalysisResult:
    dismissed = {value for value in dismissed_ids or [] if isinstance(value, str)}
    if not dismissed:
        return result
    payload = result.model_dump(mode="python")
    payload["content_gaps"] = [
        gap for gap in payload.get("content_gaps", [])
        if not isinstance(gap, dict) or gap.get("id") not in dismissed
    ]
    return TrendAnalysisResult.model_validate(payload)


def _score_from_momentum(momentum: str) -> int:
    return {"rising": 148, "peaking": 121, "falling": 42}.get(str(momentum or "").lower(), 64)


def _competition_from_match_and_momentum(match_pct: int, momentum: str) -> str:
    momentum_value = str(momentum or "").lower()
    if momentum_value == "peaking" or match_pct >= 90:
        return "High"
    if momentum_value == "rising" or match_pct >= 75:
        return "Medium"
    return "Low"


def _build_topic_details(result: TrendAnalysisResult) -> list[TrendingTopicDetail]:
    topic_rows: list[TrendingTopicDetail] = []
    niche_name = result.niche.primary_category if result.niche else "your niche"
    recommendation_map = {
        str(rec.trend_reference or "").strip().lower(): rec
        for rec in result.recommendations
        if str(rec.trend_reference or "").strip()
    }
    fallback_recommendation = result.recommendations[0] if result.recommendations else None

    for index, trend in enumerate(result.global_trends, start=1):
        if trend.trend_type == "audio":
            continue
        recommendation = recommendation_map.get(trend.topic_name.strip().lower()) or fallback_recommendation
        match_pct = int(round(
            trend.audience_match_pct
            if isinstance(trend.audience_match_pct, (int, float))
            else min(95, max(58, round((recommendation.opportunity_score if recommendation and recommendation.opportunity_score is not None else 72))))
        ))
        growth_pct = _score_from_momentum(trend.momentum)
        if trend.trend_type == "format":
            growth_pct += 12
        elif trend.trend_type == "hashtag":
            growth_pct -= 8
        why_it_fits = (
            recommendation.rationale
            if recommendation and recommendation.rationale
            else f"This trend aligns with {niche_name} content patterns and current audience interest."
        )
        topic_rows.append(
            TrendingTopicDetail(
                id=f"topic_{index}",
                topic_name=trend.topic_name,
                trend_type=trend.trend_type,
                momentum=trend.momentum,
                audience_match_pct=max(0, min(100, match_pct)),
                growth_pct=max(0, growth_pct),
                competition_level=_competition_from_match_and_momentum(match_pct, trend.momentum),
                description=trend.description,
                why_it_fits=why_it_fits,
                example_reference=trend.example_reference,
            )
        )
    return topic_rows


def _normalize_query_value(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_int_query_value(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    normalized = default
    if isinstance(value, bool):
        normalized = int(value)
    elif isinstance(value, int):
        normalized = value
    elif isinstance(value, float):
        normalized = int(value)
    elif isinstance(value, str):
        try:
            normalized = int(value.strip())
        except ValueError:
            normalized = default

    if minimum is not None:
        normalized = max(minimum, normalized)
    if maximum is not None:
        normalized = min(maximum, normalized)
    return normalized


def _sort_items(
    items: list[TrendingTopicDetail],
    *,
    sort_by: str,
    sort_dir: str,
    field_map: dict[str, str],
) -> list:
    sort_by_value = sort_by if isinstance(sort_by, str) else "default"
    sort_dir_value = sort_dir if isinstance(sort_dir, str) else "desc"
    target_attr = field_map.get(sort_by_value, field_map.get("default", "growth_pct"))
    reverse = sort_dir_value.lower() != "asc"
    if target_attr == "competition_level":
        competition_order = {"low": 1, "medium": 2, "high": 3}
        return sorted(
            items,
            key=lambda item: competition_order.get(str(getattr(item, target_attr, "")).lower(), 0),
            reverse=reverse,
        )
    if target_attr == "topic_name":
        return sorted(
            items,
            key=lambda item: str(getattr(item, target_attr, "")).lower(),
            reverse=reverse,
        )
    return sorted(
        items,
        key=lambda item: getattr(item, target_attr, 0) if getattr(item, target_attr, None) is not None else 0,
        reverse=reverse,
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


@router.get("/{account_id}/trends/topics")
async def get_trend_topics(
    account_id: str,
    search: str | None = Query(default=None),
    trend_type: str | None = Query(default=None),
    momentum: str | None = Query(default=None),
    competition_level: str | None = Query(default=None),
    sort_by: str = Query(default="growth"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return detailed trending-topic rows derived from the creator trend result."""
    result = _normalize_trend_result(await _get_trends_inner(account_id, db))
    topics = _build_topic_details(result)
    search_value = _normalize_query_value(search)
    trend_type_value = _normalize_query_value(trend_type)
    momentum_value = _normalize_query_value(momentum)
    competition_value = _normalize_query_value(competition_level)

    if search_value:
        topics = [
            topic for topic in topics
            if search_value in topic.topic_name.lower()
            or search_value in topic.description.lower()
            or search_value in topic.why_it_fits.lower()
            or (topic.example_reference and search_value in topic.example_reference.lower())
        ]
    if trend_type_value:
        topics = [topic for topic in topics if topic.trend_type.lower() == trend_type_value]
    if momentum_value:
        topics = [topic for topic in topics if topic.momentum.lower() == momentum_value]
    if competition_value:
        topics = [topic for topic in topics if topic.competition_level.lower() == competition_value]

    topics = _sort_items(
        topics,
        sort_by=sort_by,
        sort_dir=sort_dir,
        field_map={
            "name": "topic_name",
            "growth": "growth_pct",
            "audience_match": "audience_match_pct",
            "competition": "competition_level",
            "default": "growth_pct",
        },
    )
    limit_value = _normalize_int_query_value(limit, 50, minimum=1, maximum=200)
    offset_value = _normalize_int_query_value(offset, 0, minimum=0)
    total = len(topics)
    topics = topics[offset_value: offset_value + limit_value]
    return {
        "topics": [topic.model_dump(mode="python") for topic in topics],
        "total": total,
    }


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
            result = attach_weekly_opportunity(TrendAnalysisResult.model_validate(payload))
            return _without_dismissed_opportunities(result, row.dismissed_content_opportunities_json)
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

    # 3. A manual refresh always recalculates; cache is only a background-job optimization.
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

    # 5. Upsert into CreatorTrendResult
    existing: CreatorTrendResult | None = None
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
                dismissed_content_opportunities_json=[],
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

    return _without_dismissed_opportunities(
        result,
        existing.dismissed_content_opportunities_json if existing is not None else [],
    )


@router.post("/{account_id}/trends/opportunities/{opportunity_id}/dismiss")
async def dismiss_content_opportunity(account_id: str, opportunity_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await db.get(CreatorTrendResult, account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Trend analysis not found")
    opportunity_ids = {
        str(opportunity.get("id")) for opportunity in (row.content_gaps_json or [])
        if isinstance(opportunity, dict) and isinstance(opportunity.get("id"), str)
    }
    if opportunity_id not in opportunity_ids:
        raise HTTPException(status_code=404, detail="Content opportunity not found")
    ids = [value for value in (row.dismissed_content_opportunities_json or []) if isinstance(value, str)]
    if opportunity_id not in ids:
        ids.append(opportunity_id)
        row.dismissed_content_opportunities_json = ids
        await db.commit()
    return {"dismissed": True, "opportunity_id": opportunity_id}


@router.delete("/{account_id}/trends/opportunities/{opportunity_id}/dismiss")
async def restore_content_opportunity(account_id: str, opportunity_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await db.get(CreatorTrendResult, account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Trend analysis not found")
    row.dismissed_content_opportunities_json = [
        value for value in (row.dismissed_content_opportunities_json or []) if value != opportunity_id
    ]
    await db.commit()
    return {"restored": True, "opportunity_id": opportunity_id}

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
