"""Persistence helpers for account-analysis results."""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from backend.app.account_sources.models import AccountSourceType
from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import AccountAnalysisResult
from backend.app.utils.logger import logger


def _infer_source_type(payload: dict[str, Any]) -> str:
    raw_source = payload.get("source")
    if isinstance(raw_source, str) and raw_source.strip():
        return raw_source.strip()
    if isinstance(payload.get("posts"), list):
        return AccountSourceType.PRECOMPUTED.value
    return "unknown"


def _sanitize_request_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    source_meta = payload.get("source_meta")
    return {
        "source": _infer_source_type(payload),
        "source_ref": payload.get("source_ref"),
        "connection_id": payload.get("connection_id"),
        "fixture_path": payload.get("fixture_path"),
        "post_limit": payload.get("post_limit"),
        "post_count": len(payload.get("posts")) if isinstance(payload.get("posts"), list) else None,
        "creator_dominant_category": payload.get("creator_dominant_category"),
        "niche_tags": list(payload.get("niche_tags") or []),
        "source_meta": source_meta if isinstance(source_meta, dict) else {},
    }


def persist_account_analysis_result(
    *,
    job_id: str,
    account_id: str,
    username: str | None,
    payload: dict[str, Any],
    status: str,
    result: dict[str, Any] | None,
    warnings: list[dict[str, Any]] | None,
    quality: dict[str, Any] | None,
    error: dict[str, Any] | None,
) -> None:
    """Upsert one durable account-analysis result row."""
    session_factory = get_sync_sessionmaker()
    logger.info(
        "[AccountAnalysisStore] Persisting job_id=%s account_id=%s status=%s source=%s warnings=%d",
        job_id,
        account_id,
        status,
        _infer_source_type(payload),
        len(warnings or []),
    )
    try:
        with session_factory() as session:
            row = session.get(AccountAnalysisResult, job_id)
            if row is None:
                row = AccountAnalysisResult(job_id=job_id, account_id=account_id, status=status)
                session.add(row)
                logger.debug("[AccountAnalysisStore] Creating row job_id=%s", job_id)

            row.account_id = account_id
            row.username = username
            row.source_type = _infer_source_type(payload)
            row.source_ref = payload.get("source_ref") or payload.get("connection_id") or payload.get("fixture_path")
            row.status = status
            row.request_metadata_json = _sanitize_request_metadata(payload)
            row.result_json = result
            row.warnings_json = warnings
            row.quality_json = quality
            row.error_json = error
            session.commit()
            logger.info("[AccountAnalysisStore] Persisted job_id=%s status=%s", job_id, status)
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        logger.warning("[AccountAnalysisStore] Failed to persist result for job_id=%s: %s", job_id, exc)
