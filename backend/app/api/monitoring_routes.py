"""Lightweight monitoring dashboard routes.

Provides operational visibility into trend generation health,
latency, and fallback rates. No external deps required.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.infra.database import get_db
from backend.app.infra.models import IdeaGenerationJob
from backend.app.api.auth import verify_api_key

router = APIRouter(
    prefix="/api/v1/monitoring",
    tags=["monitoring"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/trends/health")
async def trends_generation_health(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return trend generation pipeline health metrics.

    Returns:
        - Total, completed, failed, queued job counts (last 24h)
        - Average completion time
        - Failure rate percentage
    """
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Total jobs in last 24h
    total_stmt = select(func.count(IdeaGenerationJob.id)).where(
        IdeaGenerationJob.created_at >= since
    )
    total = (await db.execute(total_stmt)).scalar() or 0

    # Completed
    completed_stmt = select(func.count(IdeaGenerationJob.id)).where(
        IdeaGenerationJob.created_at >= since,
        IdeaGenerationJob.status == "completed",
    )
    completed = (await db.execute(completed_stmt)).scalar() or 0

    # Failed
    failed_stmt = select(func.count(IdeaGenerationJob.id)).where(
        IdeaGenerationJob.created_at >= since,
        IdeaGenerationJob.status == "failed",
    )
    failed = (await db.execute(failed_stmt)).scalar() or 0

    # Queued/processing
    queued_stmt = select(func.count(IdeaGenerationJob.id)).where(
        IdeaGenerationJob.created_at >= since,
        IdeaGenerationJob.status.in_(["queued", "processing"]),
    )
    queued = (await db.execute(queued_stmt)).scalar() or 0

    # Failure rate
    failure_rate = (failed / total * 100) if total > 0 else 0.0

    # Average completion time for completed jobs
    avg_time_stmt = select(
        func.avg(
            func.extract("epoch", IdeaGenerationJob.completed_at - IdeaGenerationJob.created_at)
        )
    ).where(
        IdeaGenerationJob.created_at >= since,
        IdeaGenerationJob.status == "completed",
        IdeaGenerationJob.completed_at.isnot(None),
    )
    avg_seconds = (await db.execute(avg_time_stmt)).scalar()

    return {
        "total_jobs_24h": total,
        "completed": completed,
        "failed": failed,
        "queued_or_processing": queued,
        "failure_rate_pct": round(failure_rate, 2),
        "avg_completion_seconds": round(float(avg_seconds), 1) if avg_seconds else None,
        "health_status": "healthy" if failure_rate < 5 else "degraded" if failure_rate < 15 else "unhealthy",
    }
