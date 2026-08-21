"""Durable post-score observations and account baseline projection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import PostAnalysisScoreSnapshot
from backend.app.utils.logger import logger


BASELINE_SAMPLE_SIZE = 12
MINIMUM_BASELINE_POSTS = 3


def _latest_distinct_scores(records: Iterable[PostAnalysisScoreSnapshot], *, exclude_post_id: str | None = None) -> list[float]:
    """Return recent score observations, keeping only the newest analysis per post."""
    seen_post_ids: set[str] = set()
    scores: list[float] = []
    for record in records:
        if exclude_post_id and record.post_id == exclude_post_id:
            continue
        if record.post_id in seen_post_ids:
            continue
        seen_post_ids.add(record.post_id)
        if isinstance(record.score, (int, float)):
            scores.append(float(record.score))
        if len(scores) >= BASELINE_SAMPLE_SIZE:
            break
    return scores


def baseline_projection(
    records: Iterable[PostAnalysisScoreSnapshot],
    *,
    current_score: float | None,
    exclude_post_id: str | None = None,
) -> dict[str, Any]:
    """Build a transparent rolling-average projection from durable observations."""
    scores = _latest_distinct_scores(records, exclude_post_id=exclude_post_id)
    if len(scores) < MINIMUM_BASELINE_POSTS:
        return {
            "status": "insufficient_history",
            "sample_size": len(scores),
            "minimum_sample_size": MINIMUM_BASELINE_POSTS,
            "average_score": None,
            "delta_from_average": None,
            "reason": "Analyze at least three distinct posts to unlock an account score baseline.",
        }
    average = round(sum(scores) / len(scores), 2)
    return {
        "status": "available",
        "sample_size": len(scores),
        "minimum_sample_size": MINIMUM_BASELINE_POSTS,
        "average_score": average,
        "delta_from_average": round(current_score - average, 2) if current_score is not None else None,
        "reason": "Rolling average of each post's latest analysis, up to the 12 most recent distinct posts.",
    }


def record_post_score_snapshot(
    *,
    account_id: str,
    post_id: str,
    contract_version: str,
    score: float | None,
    score_components: list[dict[str, Any]],
    confidence_level: str,
    source_posted_at: datetime | None,
    analyzed_at: datetime | None = None,
) -> None:
    """Append a score observation; reruns are intentionally retained for auditability."""
    normalized_account_id = account_id.strip()
    normalized_post_id = post_id.strip()
    if not normalized_account_id or not normalized_post_id:
        return
    observed_at = analyzed_at or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        session.add(
            PostAnalysisScoreSnapshot(
                account_id=normalized_account_id,
                post_id=normalized_post_id,
                contract_version=contract_version,
                score=score,
                score_components_json=score_components,
                confidence_level=confidence_level,
                source_posted_at=source_posted_at,
                analyzed_at=observed_at,
            )
        )
        session.commit()


def get_account_score_baseline(*, account_id: str, current_score: float | None, exclude_post_id: str | None = None) -> dict[str, Any]:
    """Read durable snapshots and return an honest baseline availability state."""
    normalized_account_id = account_id.strip() if isinstance(account_id, str) else ""
    if not normalized_account_id:
        return {
            "status": "unavailable",
            "sample_size": 0,
            "minimum_sample_size": MINIMUM_BASELINE_POSTS,
            "average_score": None,
            "delta_from_average": None,
            "reason": "An authenticated account is required to calculate a score baseline.",
        }
    try:
        session_factory = get_sync_sessionmaker()
        with session_factory() as session:
            records = list(
                session.scalars(
                    select(PostAnalysisScoreSnapshot)
                    .where(PostAnalysisScoreSnapshot.account_id == normalized_account_id)
                    .order_by(PostAnalysisScoreSnapshot.analyzed_at.desc(), PostAnalysisScoreSnapshot.id.desc())
                )
            )
        return baseline_projection(records, current_score=current_score, exclude_post_id=exclude_post_id)
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        logger.warning("[PostScoreHistory] Baseline unavailable account_id=%s: %s", normalized_account_id, exc)
        return {
            "status": "unavailable",
            "sample_size": 0,
            "minimum_sample_size": MINIMUM_BASELINE_POSTS,
            "average_score": None,
            "delta_from_average": None,
            "reason": "Score history is temporarily unavailable.",
        }
