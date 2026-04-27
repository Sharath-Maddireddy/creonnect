"""Nightly background jobs."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.app.analytics.audience_quality import calculate_authenticity_score
from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import CreatorDiscoveryMeta, FollowerSnapshot
from backend.app.utils.logger import logger


def _safe_int(value, default: int = 0) -> int:
    """Safely convert a value to int, returning default on invalid input."""
    try:
        return int(value) if value else default
    except (TypeError, ValueError):
        return default


def record_follower_snapshot(account_id: str, follower_count: int) -> None:
    """Upsert today's follower snapshot for the given creator account."""
    session_factory = get_sync_sessionmaker()
    today = date.today()

    with session_factory() as session:
        existing_snapshot = session.scalar(
            select(FollowerSnapshot).where(
                FollowerSnapshot.account_id == account_id,
                FollowerSnapshot.snapshot_date == today,
            )
        )
        if existing_snapshot is None:
            session.add(
                FollowerSnapshot(
                    account_id=account_id,
                    snapshot_date=today,
                    follower_count=int(follower_count),
                )
            )
        else:
            existing_snapshot.follower_count = int(follower_count)
        session.commit()


def run_authenticity_refresh_job() -> None:
    """Refresh persisted authenticity scores for all creators."""
    session_factory = get_sync_sessionmaker()

    try:
        with session_factory() as session:
            creators = session.execute(select(CreatorDiscoveryMeta)).scalars().all()
            for creator in creators:
                creator.authenticity_score = calculate_authenticity_score(
                    follower_count=_safe_int(creator.follower_count),
                    avg_views=_safe_int(creator.avg_views),
                    avg_likes=_safe_int(creator.avg_likes),
                    avg_comments=_safe_int(creator.avg_comments),
                )
                logger.info(
                    "Pre-computing authenticity for %s: Score %s",
                    creator.username or "unknown",
                    creator.authenticity_score,
                )
            session.commit()
    except SQLAlchemyError as exc:
        logger.warning("[NightlyJobs] Authenticity refresh skipped because database query failed: %s", exc)


if __name__ == "__main__":
    run_authenticity_refresh_job()
