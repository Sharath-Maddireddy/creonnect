"""Database-backed job state store for background queue polling and dedupe."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.job_defaults import ACTIVE_REUSABLE_STATUSES
from backend.app.infra.models import BackgroundJob
from backend.app.utils.datetime_utils import parse_iso_datetime
from backend.app.utils.logger import logger


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


def initialize_idempotent_job_state(
    *,
    job_id: str,
    queue_name: str,
    job_name: str,
    payload: dict[str, Any] | None,
    account_id: str,
    idempotency_key_hash: str,
    source_ref: str | None = None,
    post_limit: int | None = None,
    payload_hash: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Atomically create a job or return the job that owns the dedupe key."""
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
        session.add(
            BackgroundJob(
                job_id=job_id,
                queue_name=queue_name,
                job_name=job_name,
                status="queued",
                account_id=account_id,
                source_ref=source_ref,
                post_limit=post_limit,
                payload_hash=payload_hash,
                idempotency_key_hash=idempotency_key_hash,
                payload_json=payload,
                warnings_json=[],
            )
        )
        try:
            session.commit()
            return state, True
        except IntegrityError:
            session.rollback()
            row = session.execute(
                select(BackgroundJob)
                .where(BackgroundJob.queue_name == queue_name)
                .where(BackgroundJob.account_id == account_id)
                .where(BackgroundJob.idempotency_key_hash == idempotency_key_hash)
            ).scalars().first()
            if row is None:
                # The integrity failure was unrelated (for example, a job-id
                # collision), so do not disguise it as a dedupe hit.
                raise
            return serialize_job_state(row), False


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
            row.started_at = parse_iso_datetime(updates["started_at"])
        if "finished_at" in updates:
            row.finished_at = parse_iso_datetime(updates["finished_at"])
        if updates.pop("release_idempotency_key", False):
            row.idempotency_key_hash = None
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
        "queue_name": row.queue_name,
        "job_name": row.job_name,
        "account_id": row.account_id,
        "source_ref": row.source_ref,
        "created_at": row.created_at.astimezone(timezone.utc).isoformat() if row.created_at else None,
        "updated_at": row.updated_at.astimezone(timezone.utc).isoformat() if row.updated_at else None,
        "started_at": row.started_at.astimezone(timezone.utc).isoformat() if row.started_at else None,
        "finished_at": row.finished_at.astimezone(timezone.utc).isoformat() if row.finished_at else None,
        "progress": row.progress_json,
        "error": row.error_json,
        "result": row.result_json,
        "warnings": row.warnings_json or [],
        "quality": row.quality_json,
    }


def find_background_job_by_payload_hash(*, queue_name: str, account_id: str, payload_hash: str) -> dict[str, Any] | None:
    """Return the original job for an idempotency key, including terminal jobs."""
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        row = session.execute(
            select(BackgroundJob)
            .where(BackgroundJob.queue_name == queue_name)
            .where(BackgroundJob.account_id == account_id)
            .where(BackgroundJob.payload_hash == payload_hash)
            .order_by(BackgroundJob.created_at.desc())
        ).scalars().first()
        return serialize_job_state(row) if row is not None else None


def find_background_job_by_idempotency_key(
    *, queue_name: str, account_id: str, idempotency_key_hash: str
) -> dict[str, Any] | None:
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        row = session.execute(
            select(BackgroundJob)
            .where(BackgroundJob.queue_name == queue_name)
            .where(BackgroundJob.account_id == account_id)
            .where(BackgroundJob.idempotency_key_hash == idempotency_key_hash)
        ).scalars().first()
        return serialize_job_state(row) if row is not None else None


def list_background_jobs(*, queue_name: str, account_id: str, limit: int, skip: int) -> list[dict[str, Any]]:
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        rows = session.execute(
            select(BackgroundJob)
            .where(BackgroundJob.queue_name == queue_name)
            .where(BackgroundJob.account_id == account_id)
            .order_by(BackgroundJob.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
        return [serialize_job_state(row) for row in rows]


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
