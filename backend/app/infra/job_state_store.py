"""Database-backed job state store for background queue polling and dedupe."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import SQLAlchemyError

from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import BackgroundJob
from backend.app.utils.logger import logger


ACTIVE_REUSABLE_STATUSES = {"queued", "started", "succeeded"}


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def initialize_job_state(
    *,
    job_id: str,
    queue_name: str,
    job_name: str,
    payload: dict[str, Any] | None,
    account_id: str | None = None,
    source_ref: str | None = None,
    post_limit: int | None = None,
    payload_hash: str | None = None,
) -> dict[str, Any]:
    state = {
        "job_id": job_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "finished_at": None,
        "progress": None,
        "error": None,
        "result": None,
        "warnings": [],
        "quality": None,
    }
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        row = session.get(BackgroundJob, job_id)
        if row is None:
            row = BackgroundJob(
                job_id=job_id,
                queue_name=queue_name,
                job_name=job_name,
                status="queued",
            )
            session.add(row)
        row.queue_name = queue_name
        row.job_name = job_name
        row.status = "queued"
        row.account_id = account_id
        row.source_ref = source_ref
        row.post_limit = post_limit
        row.payload_hash = payload_hash
        row.payload_json = payload
        row.progress_json = None
        row.result_json = None
        row.warnings_json = []
        row.quality_json = None
        row.error_json = None
        row.started_at = None
        row.finished_at = None
        session.commit()
    return state


def update_job_state(job_id: str, **updates: Any) -> dict[str, Any]:
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        row = session.get(BackgroundJob, job_id)
        if row is None:
            raise RuntimeError(f"Background job state not initialized for job_id={job_id!r}")
        if "status" in updates:
            row.status = str(updates["status"])
        if "progress" in updates:
            row.progress_json = updates["progress"]
        if "error" in updates:
            row.error_json = updates["error"]
        if "result" in updates:
            row.result_json = updates["result"]
        if "warnings" in updates:
            row.warnings_json = updates["warnings"]
        if "quality" in updates:
            row.quality_json = updates["quality"]
        if "started_at" in updates:
            row.started_at = _parse_iso_datetime(updates["started_at"])
        if "finished_at" in updates:
            row.finished_at = _parse_iso_datetime(updates["finished_at"])
        session.commit()
        session.refresh(row)
        return serialize_job_state(row)


def get_job_state(job_id: str) -> dict[str, Any] | None:
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        row = session.get(BackgroundJob, job_id)
        return serialize_job_state(row) if row is not None else None


def serialize_job_state(row: BackgroundJob) -> dict[str, Any]:
    return {
        "job_id": row.job_id,
        "status": row.status,
        "created_at": row.created_at.astimezone(timezone.utc).isoformat() if row.created_at else None,
        "started_at": row.started_at.astimezone(timezone.utc).isoformat() if row.started_at else None,
        "finished_at": row.finished_at.astimezone(timezone.utc).isoformat() if row.finished_at else None,
        "progress": row.progress_json,
        "error": row.error_json,
        "result": row.result_json,
        "warnings": row.warnings_json or [],
        "quality": row.quality_json,
    }


def find_reusable_background_job(
    *,
    queue_name: str,
    account_id: str,
    post_limit: int | None,
    payload_hash: str | None,
) -> tuple[str | None, str | None]:
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        stmt: Select[tuple[BackgroundJob]] = (
            select(BackgroundJob)
            .where(BackgroundJob.queue_name == queue_name)
            .where(BackgroundJob.account_id == account_id)
            .where(BackgroundJob.status.in_(ACTIVE_REUSABLE_STATUSES))
            .order_by(BackgroundJob.created_at.desc())
        )
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            if payload_hash and row.payload_hash == payload_hash:
                return row.job_id, row.status
            if post_limit is not None and row.post_limit == post_limit:
                return row.job_id, row.status
    return None, None


def count_recent_jobs(*, queue_name: str, account_id: str, since: datetime) -> int:
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        stmt = (
            select(func.count())
            .select_from(BackgroundJob)
            .where(BackgroundJob.queue_name == queue_name)
            .where(BackgroundJob.account_id == account_id)
            .where(BackgroundJob.created_at >= since)
        )
        return int(session.execute(stmt).scalar_one())


def delete_background_job(job_id: str) -> None:
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        row = session.get(BackgroundJob, job_id)
        if row is None:
            return
        session.delete(row)
        session.commit()


def safe_get_job_state(job_id: str) -> dict[str, Any] | None:
    try:
        return get_job_state(job_id)
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        logger.warning("[JobStateStore] Failed to load job_id=%s: %s", job_id, exc)
        return None


def count_recent_jobs_last_hour(*, queue_name: str, account_id: str) -> int:
    return count_recent_jobs(
        queue_name=queue_name,
        account_id=account_id,
        since=datetime.now(timezone.utc) - timedelta(hours=1),
    )
