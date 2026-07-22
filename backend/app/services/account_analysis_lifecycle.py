"""Job lifecycle/status helpers for account analysis jobs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any


def project_stale_failed_status(
    payload: dict[str, Any],
    *,
    running_statuses: set[str],
    queued_stale_seconds: int,
    started_stale_seconds: int,
    parse_iso_datetime: Callable[[Any], datetime | None],
    now_iso: Callable[[], str],
) -> dict[str, Any]:
    status = payload.get("status")
    if status not in running_statuses:
        return payload

    now = datetime.now(timezone.utc)
    created_at = parse_iso_datetime(payload.get("created_at"))
    started_at = parse_iso_datetime(payload.get("started_at"))
    stale_reason: str | None = None
    stale_finished_at: datetime | None = None

    if status == "queued":
        if created_at is None:
            return payload
        age_seconds = (now - created_at).total_seconds()
        if age_seconds > queued_stale_seconds:
            stale_reason = (
                f"Job remained queued for {int(age_seconds)}s, exceeding "
                f"{queued_stale_seconds}s."
            )
            stale_finished_at = created_at + timedelta(seconds=queued_stale_seconds)

    if status == "started":
        active_since = started_at or created_at
        if active_since is None:
            return payload
        age_seconds = (now - active_since).total_seconds()
        if age_seconds > started_stale_seconds:
            stale_reason = (
                f"Job remained started for {int(age_seconds)}s, exceeding "
                f"{started_stale_seconds}s."
            )
            stale_finished_at = active_since + timedelta(seconds=started_stale_seconds)

    if stale_reason is None:
        return payload

    finished_at = payload.get("finished_at")
    if not isinstance(finished_at, str) or not finished_at.strip():
        finished_at = stale_finished_at.isoformat() if isinstance(stale_finished_at, datetime) else now_iso()

    projected = dict(payload)
    projected.update(
        status="failed",
        finished_at=finished_at,
        error={"type": "TimeoutError", "message": stale_reason},
        result=None,
    )
    return projected


def read_status_with_guard(
    job_id: str,
    *,
    store: Any,
    sanitize_status_payload: Callable[[dict[str, Any]], dict[str, Any]],
    project_stale_status: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any] | None:
    payload = store.get(job_id)
    if not isinstance(payload, dict):
        return None
    sanitized = sanitize_status_payload(payload)
    return project_stale_status(sanitized)


def update_status(
    job_id: str,
    *,
    store: Any,
    extra_status_fields: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    payload = store.get(job_id) or store.base_status(job_id, extra_status_fields)
    payload.update(updates)
    store.write(job_id, payload)
    return payload


def initialize_job_status(
    job_id: str,
    *,
    get_status: Callable[[str], dict[str, Any] | None],
    store: Any,
    extra_status_fields: dict[str, Any],
) -> dict[str, Any]:
    existing = get_status(job_id)
    if existing:
        return existing
    payload = store.base_status(job_id, extra_status_fields)
    store.write(job_id, payload)
    return payload