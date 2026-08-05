from __future__ import annotations

"""Shared persistence helpers for trend-analysis results."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.trend_models import TrendAnalysisResult
from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import CreatorTrendResult


def _serialize_trend_result(result: TrendAnalysisResult) -> dict[str, Any]:
    return {
        "niche_json": result.niche.model_dump(mode="python") if hasattr(result.niche, "model_dump") else {},
        "global_trends_json": [trend.model_dump(mode="python") for trend in result.global_trends],
        "recommendations_json": [rec.model_dump(mode="python") for rec in result.recommendations],
        "content_gaps_json": [gap.model_dump(mode="python") for gap in result.content_gaps] if result.content_gaps else [],
        "daily_insights_json": (
            result.daily_insights.model_dump(mode="python")
            if result.daily_insights and hasattr(result.daily_insights, "model_dump")
            else None
        ),
        "opportunity_bullets_json": result.opportunity_bullets if result.opportunity_bullets else [],
        "weekly_opportunity_json": (
            result.weekly_opportunity.model_dump(mode="python")
            if result.weekly_opportunity and hasattr(result.weekly_opportunity, "model_dump")
            else None
        ),
    }


def apply_trend_result_to_row(row: CreatorTrendResult, result: TrendAnalysisResult) -> CreatorTrendResult:
    payload = _serialize_trend_result(result)
    for field_name, value in payload.items():
        setattr(row, field_name, value)
    return row


async def upsert_trend_result_async(
    db: AsyncSession,
    account_id: str,
    result: TrendAnalysisResult,
    *,
    dismissed_ids: list[str] | None = None,
) -> CreatorTrendResult:
    row = await db.get(CreatorTrendResult, account_id)
    if row is None:
        row = CreatorTrendResult(
            account_id=account_id,
            dismissed_content_opportunities_json=dismissed_ids or [],
        )
    elif dismissed_ids is not None:
        row.dismissed_content_opportunities_json = dismissed_ids

    apply_trend_result_to_row(row, result)
    db.add(row)
    await db.commit()
    return row


def upsert_trend_result_sync(
    account_id: str,
    result: TrendAnalysisResult,
    *,
    dismissed_ids: list[str] | None = None,
) -> None:
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        row = session.get(CreatorTrendResult, account_id)
        if row is None:
            row = CreatorTrendResult(
                account_id=account_id,
                dismissed_content_opportunities_json=dismissed_ids or [],
            )
        elif dismissed_ids is not None:
            row.dismissed_content_opportunities_json = dismissed_ids

        apply_trend_result_to_row(row, result)
        session.add(row)
        session.commit()
