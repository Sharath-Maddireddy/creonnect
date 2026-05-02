"""RQ job orchestration for reel analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from rq import get_current_job

from backend.app.analytics.reel_analysis_service import compute_reel_analysis
from backend.app.analytics.reel_audio_engine import compute_reel_audio_score
from backend.app.analytics.reel_gemini_engine import run_reel_gemini_analysis
from backend.app.infra.job_queue import (
    REEL_ANALYSIS_JOB_NAME,
    REEL_ANALYSIS_QUEUE_NAME,
    enqueue_callable,
)
from backend.app.infra.redis_client import get_json, set_json
from backend.app.infra.rq_queue import (
    DEFAULT_FAILURE_TTL_SECONDS,
    DEFAULT_RESULT_TTL_SECONDS,
)
from backend.app.utils.logger import logger


REEL_JOB_KEY_PREFIX = "reel_analysis:job:"
REEL_JOB_STATUS_TTL_SECONDS = 86400
REEL_JOB_TIMEOUT_SECONDS = 120


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_key(job_id: str) -> str:
    return f"{REEL_JOB_KEY_PREFIX}{job_id}"


def _base_status(job_id: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "queued",
        "created_at": _now_iso(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }


def _write_status(job_id: str, payload: dict[str, Any]) -> None:
    set_json(_job_key(job_id), payload, ttl_seconds=REEL_JOB_STATUS_TTL_SECONDS)


def _read_status(job_id: str) -> dict[str, Any] | None:
    return get_json(_job_key(job_id))


def _update_status(job_id: str, **updates: Any) -> dict[str, Any]:
    payload = _read_status(job_id) or _base_status(job_id)
    payload.update(updates)
    _write_status(job_id, payload)
    return payload


def initialize_reel_job_status(job_id: str) -> None:
    logger.debug("[ReelAnalysisJob] Initializing status job_id=%s", job_id)
    _write_status(job_id, _base_status(job_id))


def get_reel_job_status(job_id: str) -> dict[str, Any] | None:
    return _read_status(job_id)


def enqueue_reel_analysis_job(payload: dict[str, Any]) -> dict[str, str]:
    """Enqueue reel analysis background job and return queued status payload."""
    media_url = str(payload.get("media_url", "")).strip()
    if not media_url:
        raise ValueError("media_url is required.")

    job_id = str(uuid4())
    full_payload = {
        "job_id": job_id,
        "media_url": media_url,
        "audio_name": payload.get("audio_name"),
        "caption_text": str(payload.get("caption_text", "")),
        "watch_time_pct": payload.get("watch_time_pct"),
    }
    logger.info(
        "[ReelAnalysisJob] Enqueue requested job_id=%s media_url_present=%s audio_name=%s watch_time_pct=%s",
        job_id,
        bool(media_url),
        bool(payload.get("audio_name")),
        payload.get("watch_time_pct"),
    )
    initialize_reel_job_status(job_id)
    enqueue_callable(
        queue_name=REEL_ANALYSIS_QUEUE_NAME,
        job_name=REEL_ANALYSIS_JOB_NAME,
        func=run_reel_analysis_job,
        payload=full_payload,
        job_id=job_id,
        timeout_seconds=REEL_JOB_TIMEOUT_SECONDS,
        result_ttl_seconds=DEFAULT_RESULT_TTL_SECONDS,
        failure_ttl_seconds=DEFAULT_FAILURE_TTL_SECONDS,
    )
    return {"job_id": job_id, "status": "queued"}


def run_reel_analysis_job(payload: dict[str, Any]) -> None:
    """RQ worker entrypoint for reel analysis."""
    current_job = get_current_job()
    job_id = (current_job.id if current_job is not None else None) or str(payload.get("job_id") or uuid4())
    media_url = str(payload.get("media_url", "")).strip()
    audio_name = payload.get("audio_name")
    caption_text = str(payload.get("caption_text", ""))
    watch_time_pct_raw = payload.get("watch_time_pct")
    watch_time_pct = float(watch_time_pct_raw) if isinstance(watch_time_pct_raw, (int, float)) else None

    logger.info(
        "[ReelAnalysisJob] Started job_id=%s audio_name=%s watch_time_pct=%s",
        job_id,
        bool(audio_name),
        watch_time_pct,
    )
    _update_status(job_id, status="started", started_at=_now_iso())

    try:
        vision_result = run_reel_gemini_analysis(media_url)
        vision_status = str(vision_result.get("status", "error"))
        signals = vision_result.get("signals", {})
        if not isinstance(signals, dict):
            signals = {}
        logger.debug(
            "[ReelAnalysisJob] Vision result job_id=%s status=%s signal_keys=%s",
            job_id,
            vision_status,
            sorted(signals.keys()),
        )

        audio_score = compute_reel_audio_score(
            audio_name=audio_name if isinstance(audio_name, str) else None,
            caption_text=caption_text,
        )
        logger.debug(
            "[ReelAnalysisJob] Audio score job_id=%s total=%s",
            job_id,
            getattr(audio_score, "total", None),
        )

        reel_model = compute_reel_analysis(
            reel_vision_signals=signals,
            audio_score=audio_score,
            watch_time_pct=watch_time_pct,
            reel_vision_status=vision_status,
        )

        result = reel_model.model_dump()
        result["raw_vision_signals"] = signals
        _update_status(
            job_id,
            status="succeeded",
            finished_at=_now_iso(),
            result=result,
            error=None,
        )
        logger.info(
            "[ReelAnalysisJob] Completed job_id=%s vision_status=%s total=%.1f",
            job_id,
            vision_status,
            float(reel_model.total or 0.0),
        )
    except Exception as exc:
        logger.error("[ReelAnalysisJob] Failed job_id=%s: %s", job_id, exc)
        _update_status(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            error={"type": type(exc).__name__, "message": str(exc)},
            result=None,
        )
