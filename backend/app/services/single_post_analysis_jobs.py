"""Background job orchestration for single-post analysis."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.domain.post_models import SinglePostInsights
from backend.app.infra.job_queue import (
    DEFAULT_FAILURE_TTL_SECONDS,
    DEFAULT_JOB_TIMEOUT_SECONDS,
    DEFAULT_RESULT_TTL_SECONDS,
    SINGLE_POST_ANALYSIS_JOB_NAME,
    SINGLE_POST_ANALYSIS_QUEUE_NAME,
    enqueue_callable,
)
from backend.app.infra.job_state_store import get_job_state, initialize_job_state, update_job_state
from backend.app.services.post_insights_service import build_single_post_insights
from backend.app.utils.logger import logger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalize_post_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"REEL", "VIDEO", "REELS", "CLIPS"}:
        return "REEL"
    return "IMAGE"


def _stable_post_id(*, media_url: str, post_type: str, caption_text: str) -> str:
    payload = json.dumps(
        [media_url, post_type, caption_text],
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()[:16]
    return f"auto_{digest}"


def _normalize_enqueue_payload(payload: dict[str, Any]) -> dict[str, Any]:
    media_url = _normalize_text(payload.get("media_url"))
    if not media_url:
        raise ValueError("media_url is required for single-post analysis.")
    post_type = _normalize_post_type(payload.get("post_type"))
    caption_text = str(payload.get("caption_text") or "")
    post_id = _normalize_text(payload.get("post_id")) or _stable_post_id(
        media_url=media_url,
        post_type=post_type,
        caption_text=caption_text,
    )
    normalized = {
        "post_id": post_id,
        "account_id": _normalize_text(payload.get("account_id")),
        "creator_id": _normalize_text(payload.get("creator_id")),
        "platform": _normalize_text(payload.get("platform")) or "instagram",
        "post_type": post_type,
        "media_url": media_url,
        "thumbnail_url": str(payload.get("thumbnail_url") or ""),
        "caption_text": caption_text,
        "hashtags": payload.get("hashtags") if isinstance(payload.get("hashtags"), list) else [],
        "likes": int(payload.get("likes") or 0),
        "comments": int(payload.get("comments") or 0),
        "views": payload.get("views"),
        "audio_name": _normalize_text(payload.get("audio_name")),
        "posted_at": payload.get("posted_at"),
        "connection_id": _normalize_text(payload.get("connection_id")),
        "run_advanced_caption_ai": bool(payload.get("run_advanced_caption_ai", True)),
        "run_advanced_audience_ai": bool(payload.get("run_advanced_audience_ai", True)),
    }
    return normalized


def enqueue_single_post_analysis_job(payload: dict[str, Any]) -> dict[str, str]:
    normalized = _normalize_enqueue_payload(payload if isinstance(payload, dict) else {})
    raw_job_id = _normalize_text(payload.get("job_id")) if isinstance(payload, dict) else None
    job_id = raw_job_id or str(uuid4())
    normalized["job_id"] = job_id

    initialize_job_state(
        job_id=job_id,
        queue_name=SINGLE_POST_ANALYSIS_QUEUE_NAME,
        job_name=SINGLE_POST_ANALYSIS_JOB_NAME,
        payload=normalized,
        account_id=normalized.get("account_id") or normalized.get("creator_id"),
        source_ref=normalized.get("connection_id"),
        post_limit=1,
        payload_hash=None,
    )
    logger.info(
        "[SinglePostJob] Queueing job_id=%s post_id=%s media_url=%s",
        job_id,
        normalized.get("post_id"),
        normalized.get("media_url"),
    )
    enqueue_callable(
        queue_name=SINGLE_POST_ANALYSIS_QUEUE_NAME,
        job_name=SINGLE_POST_ANALYSIS_JOB_NAME,
        func=run_single_post_analysis_job,
        payload=normalized,
        job_id=job_id,
        timeout_seconds=DEFAULT_JOB_TIMEOUT_SECONDS,
        result_ttl_seconds=DEFAULT_RESULT_TTL_SECONDS,
        failure_ttl_seconds=DEFAULT_FAILURE_TTL_SECONDS,
        retry_max=2,
        retry_intervals=[10, 30],
    )
    return {"job_id": job_id, "status": "queued"}


async def enqueue_single_post_analysis_job_async(payload: dict[str, Any]) -> dict[str, str]:
    return enqueue_single_post_analysis_job(payload)


def get_single_post_analysis_job_status(job_id: str) -> dict[str, Any] | None:
    return get_job_state(job_id)


def _post_payload(post: SinglePostInsights, fallback_post_id: str, fallback_media_url: str) -> dict[str, Any]:
    return {
        "post_id": post.media_id or fallback_post_id,
        "post_type": post.media_type or "IMAGE",
        "media_url": post.media_url or fallback_media_url,
        "caption_text": post.caption_text or "",
    }


def run_single_post_analysis_job(payload: dict[str, Any]) -> None:
    payload = payload if isinstance(payload, dict) else {}
    job_id = _normalize_text(payload.get("job_id")) or str(uuid4())
    update_job_state(
        job_id,
        status="started",
        started_at=_now_iso(),
        progress={"stage": "analyze", "done": 0, "total": 1},
        error=None,
        result=None,
        warnings=[],
        quality={"vision_enabled": True, "ai_fallback_used": False},
    )
    try:
        creator_id = _normalize_text(payload.get("account_id")) or _normalize_text(payload.get("creator_id")) or ""
        creator_post = CreatorPostAIInput(
            post_id=str(payload.get("post_id") or ""),
            creator_id=creator_id,
            platform=str(payload.get("platform") or "instagram"),
            post_type=_normalize_post_type(payload.get("post_type")),
            media_url=str(payload.get("media_url") or ""),
            thumbnail_url=str(payload.get("thumbnail_url") or ""),
            caption_text=str(payload.get("caption_text") or ""),
            hashtags=payload.get("hashtags") if isinstance(payload.get("hashtags"), list) else [],
            likes=int(payload.get("likes") or 0),
            comments=int(payload.get("comments") or 0),
            views=payload.get("views"),
            audio_name=_normalize_text(payload.get("audio_name")),
            posted_at=payload.get("posted_at"),
        )
        pipeline_result = asyncio.run(
            build_single_post_insights(
                target_post=creator_post,
                historical_posts=[],
                run_ai=True,
                run_advanced_caption_ai=bool(payload.get("run_advanced_caption_ai", True)),
                run_advanced_audience_ai=bool(payload.get("run_advanced_audience_ai", True)),
            )
        )
        raw_post = pipeline_result.get("post")
        if raw_post is None:
            raise RuntimeError("Single-post pipeline returned no post data.")
        post = raw_post if isinstance(raw_post, SinglePostInsights) else SinglePostInsights.model_validate(raw_post)
        ai_analysis = pipeline_result.get("ai_analysis") if isinstance(pipeline_result.get("ai_analysis"), dict) else {}
        warnings = ai_analysis.get("warnings") if isinstance(ai_analysis.get("warnings"), list) else []
        fallback_used = bool(ai_analysis.get("fallback_used", False))
        result_payload = {
            "status": "succeeded",
            "post": _post_payload(post, fallback_post_id=creator_post.post_id, fallback_media_url=creator_post.media_url),
            "scores": {
                "P": post.weighted_post_score.score if post.weighted_post_score else None,
                "predicted_engagement_rate": post.predicted_engagement_rate,
            },
            "ai_analysis": ai_analysis,
        }
        update_job_state(
            job_id,
            status="succeeded",
            finished_at=_now_iso(),
            progress={"stage": "analyze", "done": 1, "total": 1},
            error=None,
            warnings=warnings,
            quality={"vision_enabled": True, "ai_fallback_used": fallback_used},
            result=result_payload,
        )
        logger.info("[SinglePostJob] Succeeded job_id=%s post_id=%s", job_id, creator_post.post_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[SinglePostJob] Failed job_id=%s", job_id)
        update_job_state(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            error={"type": exc.__class__.__name__, "message": str(exc)},
            warnings=[],
            result=None,
        )
        raise
