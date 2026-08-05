"""Durable storage for versioned Creator Intelligence reports and snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.app.domain.creator_intelligence_report_models import CreatorIntelligenceReport
from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import CreatorDiscoveryMeta, CreatorIntelligenceReportRecord, FollowerSnapshot
from backend.app.utils.logger import logger


def persist_creator_intelligence_report(
    *,
    analysis_job_id: str,
    account_id: str,
    report: CreatorIntelligenceReport,
) -> None:
    """Store a report once; a job cannot overwrite a previously stored version."""
    session_factory = get_sync_sessionmaker()
    try:
        with session_factory() as session:
            existing = session.get(CreatorIntelligenceReportRecord, analysis_job_id)
            if existing is not None:
                logger.warning(
                    "[CreatorIntelligenceStore] Skipping immutable report overwrite job_id=%s",
                    analysis_job_id,
                )
                return
            session.add(
                CreatorIntelligenceReportRecord(
                    analysis_job_id=analysis_job_id,
                    account_id=account_id,
                    schema_version=report.schema_version,
                    report_status=report.report_status,
                    source_data_at=report.generated_at,
                    report_json=report.model_dump(mode="json"),
                )
            )
            session.commit()
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        logger.warning(
            "[CreatorIntelligenceStore] Failed to persist report job_id=%s: %s",
            analysis_job_id,
            exc,
        )
        raise


def record_follower_snapshot(
    *,
    account_id: str,
    follower_count: int,
    source: str,
    observed_at: datetime | None = None,
) -> bool:
    """Record the first valid observation for an account/source/day.

    Returns True when an observation was inserted and False when the daily
    snapshot already exists. Existing source observations are never overwritten.
    """
    if follower_count < 0:
        raise ValueError("follower_count must be non-negative")
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    normalized_source = source.strip()[:80] if isinstance(source, str) else "account_analysis"
    normalized_source = normalized_source or "account_analysis"

    session_factory = get_sync_sessionmaker()
    try:
        with session_factory() as session:
            existing = session.scalar(
                select(FollowerSnapshot.id).where(
                    FollowerSnapshot.account_id == account_id,
                    FollowerSnapshot.source == normalized_source,
                    FollowerSnapshot.snapshot_date == observed.date(),
                )
            )
            if existing is not None:
                return False
            session.add(
                FollowerSnapshot(
                    account_id=account_id,
                    follower_count=follower_count,
                    source=normalized_source,
                    snapshot_date=observed.date(),
                    observed_at=observed,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return False
            return True
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        logger.warning(
            "[CreatorIntelligenceStore] Failed to record follower snapshot account_id=%s: %s",
            account_id,
            exc,
        )
        raise


def get_follower_snapshots(account_id: str) -> list[FollowerSnapshot]:
    """Return ordered observed snapshots for future growth calculations."""
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        return list(
            session.scalars(
                select(FollowerSnapshot)
                .where(FollowerSnapshot.account_id == account_id)
                .order_by(FollowerSnapshot.observed_at.asc())
            )
        )


def get_peer_cohort(
    *,
    account_id: str,
    creator_dominant_category: str | None,
    follower_count: int | None,
) -> list[CreatorDiscoveryMeta]:
    """Load comparable real creators for report benchmarking.

    A category and follower count are required so an arbitrary platform-wide
    population cannot be presented as a creator's peer group.
    """
    category = creator_dominant_category.strip() if isinstance(creator_dominant_category, str) else ""
    if not category or not isinstance(follower_count, int) or follower_count <= 0:
        return []
    lower_bound = max(1, round(follower_count * 0.5))
    upper_bound = round(follower_count * 2.0)
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        return list(
            session.scalars(
                select(CreatorDiscoveryMeta)
                .where(
                    CreatorDiscoveryMeta.account_id != account_id,
                    CreatorDiscoveryMeta.creator_dominant_category == category,
                    CreatorDiscoveryMeta.follower_count >= lower_bound,
                    CreatorDiscoveryMeta.follower_count <= upper_bound,
                    CreatorDiscoveryMeta.ahs_score.is_not(None),
                    CreatorDiscoveryMeta.predicted_engagement_rate.is_not(None),
                )
                .order_by(CreatorDiscoveryMeta.updated_at.desc())
            )
        )


def get_latest_creator_intelligence_report(account_id: str) -> CreatorIntelligenceReport | None:
    """Return the newest persisted report for an account, if one exists."""
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        row = session.scalar(
            select(CreatorIntelligenceReportRecord)
            .where(CreatorIntelligenceReportRecord.account_id == account_id)
            .order_by(CreatorIntelligenceReportRecord.created_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        return CreatorIntelligenceReport.model_validate(row.report_json)
