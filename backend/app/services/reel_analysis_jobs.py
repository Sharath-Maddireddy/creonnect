"""RQ job orchestration for reel analysis."""

from __future__ import annotations

from datetime import datetime, timezone
import platform
from typing import Any
from uuid import uuid4

from rq import get_current_job

from backend.app.analytics.reel_analysis_service import compute_reel_analysis
from backend.app.analytics.reel_audio_engine import compute_reel_audio_score
from backend.app.analytics.reel_gemini_engine import run_reel_gemini_analysis
from backend.app.analytics.reel_sarvam_engine import transcribe_reel_audio
import concurrent.futures
import os
from backend.app.infra.redis_client import get_json, set_json
from backend.app.infra.rq_queue import (
    DEFAULT_FAILURE_TTL_SECONDS,
    DEFAULT_RESULT_TTL_SECONDS,
    get_queue,
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
    initialize_reel_job_status(job_id)
    queue = get_queue("reel-analysis")
    job_timeout = None if platform.system() == "Windows" else REEL_JOB_TIMEOUT_SECONDS
    queue.enqueue(
        run_reel_analysis_job,
        full_payload,
        job_id=job_id,
        job_timeout=job_timeout,
        result_ttl=DEFAULT_RESULT_TTL_SECONDS,
        failure_ttl=DEFAULT_FAILURE_TTL_SECONDS,
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

    _update_status(job_id, status="started", started_at=_now_iso())

    try:
        # Run vision (Gemini) and STT (Sarvam) in parallel to save time
        transcript = None
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_vision = executor.submit(run_reel_gemini_analysis, media_url)
                future_transcript = executor.submit(transcribe_reel_audio, media_url)
                try:
                    vision_result = future_vision.result()
                except Exception as _e:
                    logger.error("[ReelAnalysisJob] run_reel_gemini_analysis failed: %s", _e)
                    vision_result = {"status": "error", "signals": {}, "error": str(_e)}
                try:
                    transcript = future_transcript.result()
                except Exception as _e:
                    logger.error("[ReelAnalysisJob] transcribe_reel_audio failed: %s", _e)
                    transcript = None
        except Exception as e:
            # Fall back to sequential calls if executor fails
            logger.error("[ReelAnalysisJob] concurrency executor failed, falling back: %s", e)
            try:
                vision_result = run_reel_gemini_analysis(media_url)
            except Exception as _e:
                logger.error("[ReelAnalysisJob] run_reel_gemini_analysis failed: %s", _e)
                vision_result = {"status": "error", "signals": {}, "error": str(_e)}
            try:
                transcript = transcribe_reel_audio(media_url)
            except Exception as _e:
                logger.error("[ReelAnalysisJob] transcribe_reel_audio failed: %s", _e)
                transcript = None

        vision_status = str(vision_result.get("status", "error"))
        signals = vision_result.get("signals", {})
        if not isinstance(signals, dict):
            signals = {}

        # Determine sarvam transcription status per returned transcript and env
        if isinstance(transcript, str) and transcript.strip():
            sarvam_status = "ok"
        elif transcript is None:
            sarvam_status = "disabled" if not os.getenv("SARVAM_API_KEY") else "error"
        else:
            sarvam_status = "error"

        audio_score = compute_reel_audio_score(
            audio_name=audio_name if isinstance(audio_name, str) else None,
            caption_text=caption_text,
        )

        reel_model = compute_reel_analysis(
            reel_vision_signals=signals,
            audio_score=audio_score,
            watch_time_pct=watch_time_pct,
            reel_vision_status=vision_status,
            spoken_transcript=transcript,
            sarvam_transcription_status=sarvam_status,
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
