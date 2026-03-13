"""RQ job orchestration for account-level analysis."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from rq import Retry, get_current_job

from backend.app.domain.post_models import SinglePostInsights
from backend.app.infra.redis_client import get_json, get_text, incr_with_expire, set_json, set_text
from backend.app.infra.rq_queue import (
    DEFAULT_FAILURE_TTL_SECONDS,
    DEFAULT_JOB_TIMEOUT_SECONDS,
    DEFAULT_RESULT_TTL_SECONDS,
    get_queue,
)
from backend.app.services.account_analysis_service import analyze_account_health
from backend.app.services.post_insights_service import build_single_post_insights
from backend.app.utils.logger import logger


ACCOUNT_ANALYSIS_JOB_KEY_PREFIX = "account_analysis:job:"
ACCOUNT_ANALYSIS_DEDUPE_KEY_PREFIX = "account_analysis:dedupe:"
ACCOUNT_ANALYSIS_RATE_KEY_PREFIX = "account_analysis:rate:"
ACCOUNT_ANALYSIS_INPUTHASH_KEY_PREFIX = "account_analysis:inputhash:"
ACCOUNT_ANALYSIS_STATUS_TTL_SECONDS = 86400
ACCOUNT_ANALYSIS_DEDUPE_TTL_SECONDS = 7200
ACCOUNT_ANALYSIS_INPUTHASH_TTL_SECONDS = 86400
ACCOUNT_ANALYSIS_RATE_TTL_SECONDS = 3600
ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR = 3
ACCOUNT_ANALYSIS_QUEUED_STALE_SECONDS = max(900, DEFAULT_JOB_TIMEOUT_SECONDS + 300)
ACCOUNT_ANALYSIS_STARTED_STALE_SECONDS = max(1800, DEFAULT_JOB_TIMEOUT_SECONDS * 2)

_ACTIVE_REUSABLE_STATUSES = {"queued", "started", "succeeded"}
_RUNNING_STATUSES = {"queued", "started"}


class AccountAnalysisRateLimitError(Exception):
    """Raised when account analysis enqueue rate limit is exceeded."""

    def __init__(self, message: str, job_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.job_id = job_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_key(job_id: str) -> str:
    return f"{ACCOUNT_ANALYSIS_JOB_KEY_PREFIX}{job_id}"


def _dedupe_key(account_id: str, post_limit: int) -> str:
    return f"{ACCOUNT_ANALYSIS_DEDUPE_KEY_PREFIX}{account_id}:{post_limit}"


def _rate_key(account_id: str) -> str:
    return f"{ACCOUNT_ANALYSIS_RATE_KEY_PREFIX}{account_id}"


def _inputhash_key(account_id: str, payload_hash: str) -> str:
    return f"{ACCOUNT_ANALYSIS_INPUTHASH_KEY_PREFIX}{account_id}:{payload_hash}"


def _base_status(job_id: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "queued",
        "created_at": _now_iso(),
        "started_at": None,
        "finished_at": None,
        "progress": None,
        "error": None,
        "result": None,
        "warnings": [],
        "quality": None,
    }


def _write_status(job_id: str, status_payload: dict[str, Any]) -> None:
    set_json(_job_key(job_id), status_payload, ttl_seconds=ACCOUNT_ANALYSIS_STATUS_TTL_SECONDS)


def _read_status(job_id: str) -> dict[str, Any] | None:
    return get_json(_job_key(job_id))


def _strip_signals(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_signals(item) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "signals":
                continue
            sanitized[key] = _strip_signals(item)
        return sanitized
    return value


def _sanitize_posts_summary(result: dict[str, Any]) -> dict[str, Any]:
    posts_summary = result.get("posts_summary")
    if not isinstance(posts_summary, list):
        return result

    bounded: list[dict[str, Any]] = []
    for item in posts_summary[:30]:
        if not isinstance(item, dict):
            continue
        sanitized = _strip_signals(item)
        if isinstance(sanitized, dict):
            caption_preview = sanitized.get("caption_preview")
            if isinstance(caption_preview, str):
                sanitized["caption_preview"] = caption_preview[:120]
            bounded.append(sanitized)

    payload = dict(result)
    payload["posts_summary"] = bounded
    return payload


def _sanitize_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return payload
    sanitized_result = _sanitize_posts_summary(result)
    if sanitized_result == result:
        return payload
    sanitized_payload = dict(payload)
    sanitized_payload["result"] = sanitized_result
    return sanitized_payload


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


def _project_stale_failed_status(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status")
    if status not in _RUNNING_STATUSES:
        return payload

    now = datetime.now(timezone.utc)
    created_at = _parse_iso_datetime(payload.get("created_at"))
    started_at = _parse_iso_datetime(payload.get("started_at"))
    stale_reason: str | None = None
    stale_finished_at: datetime | None = None

    if status == "queued":
        if created_at is None:
            return payload
        age_seconds = (now - created_at).total_seconds()
        if age_seconds > ACCOUNT_ANALYSIS_QUEUED_STALE_SECONDS:
            stale_reason = (
                f"Job remained queued for {int(age_seconds)}s, exceeding "
                f"{ACCOUNT_ANALYSIS_QUEUED_STALE_SECONDS}s."
            )
            stale_finished_at = created_at + timedelta(seconds=ACCOUNT_ANALYSIS_QUEUED_STALE_SECONDS)

    if status == "started":
        active_since = started_at or created_at
        if active_since is None:
            return payload
        age_seconds = (now - active_since).total_seconds()
        if age_seconds > ACCOUNT_ANALYSIS_STARTED_STALE_SECONDS:
            stale_reason = (
                f"Job remained started for {int(age_seconds)}s, exceeding "
                f"{ACCOUNT_ANALYSIS_STARTED_STALE_SECONDS}s."
            )
            stale_finished_at = active_since + timedelta(seconds=ACCOUNT_ANALYSIS_STARTED_STALE_SECONDS)

    if stale_reason is None:
        return payload

    finished_at = payload.get("finished_at")
    if not isinstance(finished_at, str) or not finished_at.strip():
        finished_at = (
            stale_finished_at.isoformat()
            if isinstance(stale_finished_at, datetime)
            else _now_iso()
        )

    projected = dict(payload)
    projected.update(
        status="failed",
        finished_at=finished_at,
        error={"type": "TimeoutError", "message": stale_reason},
        result=None,
    )
    return projected


def _read_status_with_guard(job_id: str) -> dict[str, Any] | None:
    payload = _read_status(job_id)
    if not isinstance(payload, dict):
        return None
    sanitized = _sanitize_status_payload(payload)
    return _project_stale_failed_status(sanitized)


def _update_status(job_id: str, **updates: Any) -> dict[str, Any]:
    payload = _read_status(job_id) or _base_status(job_id)
    payload.update(updates)
    _write_status(job_id, payload)
    return payload


def initialize_job_status(job_id: str) -> dict[str, Any]:
    payload = _base_status(job_id)
    _write_status(job_id, payload)
    return payload


def get_account_analysis_job_status(job_id: str) -> dict[str, Any] | None:
    return _read_status_with_guard(job_id)


def _normalize_account_id(value: Any) -> str:
    account_id = value.strip() if isinstance(value, str) else ""
    if not account_id:
        raise ValueError("account_id is required for account analysis jobs.")
    return account_id


def _normalize_post_limit(value: Any) -> int:
    try:
        post_limit = int(value)
    except (TypeError, ValueError):
        post_limit = 30
    return max(1, min(30, post_limit))


def _normalize_job_id(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return str(value).strip()
    except Exception:
        return ""


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_include_posts_summary(value: Any) -> bool:
    return _normalize_bool(value, default=False)


def _normalize_include_posts_summary_max(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 30
    return max(1, min(30, parsed))


def _status_value(job_id: str) -> str | None:
    payload = _read_status_with_guard(job_id)
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return status if isinstance(status, str) else None


def _read_dedupe_job_id(account_id: str, post_limit: int) -> str | None:
    payload = get_json(_dedupe_key(account_id, post_limit))
    if not isinstance(payload, dict):
        return None
    job_id = payload.get("job_id")
    return job_id if isinstance(job_id, str) and job_id.strip() else None


def _write_dedupe_job_id(account_id: str, post_limit: int, job_id: str) -> None:
    set_json(
        _dedupe_key(account_id, post_limit),
        {"job_id": job_id, "created_at": _now_iso()},
        ttl_seconds=ACCOUNT_ANALYSIS_DEDUPE_TTL_SECONDS,
    )


def _compute_posts_payload_hash(payload: dict[str, Any]) -> str | None:
    posts = payload.get("posts")
    if not isinstance(posts, list):
        return None
    serialized = json.dumps(posts, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _read_inputhash_job_id(account_id: str, payload_hash: str | None) -> str | None:
    if not payload_hash:
        return None
    job_id = get_text(_inputhash_key(account_id, payload_hash))
    return job_id if isinstance(job_id, str) and job_id.strip() else None


def _write_inputhash_job_id(account_id: str, payload_hash: str | None, job_id: str) -> None:
    if not payload_hash:
        return
    set_text(
        _inputhash_key(account_id, payload_hash),
        job_id,
        ttl_seconds=ACCOUNT_ANALYSIS_INPUTHASH_TTL_SECONDS,
    )


def _resolve_reusable_job(
    account_id: str,
    post_limit: int,
    payload_hash: str | None,
) -> tuple[str | None, str | None]:
    candidates: list[str] = []

    dedupe_job_id = _read_dedupe_job_id(account_id, post_limit)
    if dedupe_job_id:
        candidates.append(dedupe_job_id)

    inputhash_job_id = _read_inputhash_job_id(account_id, payload_hash)
    if inputhash_job_id and inputhash_job_id not in candidates:
        candidates.append(inputhash_job_id)

    for candidate_job_id in candidates:
        status = _status_value(candidate_job_id)
        if status in _ACTIVE_REUSABLE_STATUSES:
            return candidate_job_id, status
    return None, None


def _enforce_rate_limit(account_id: str, running_job_id: str | None) -> None:
    rate_value = incr_with_expire(_rate_key(account_id), ACCOUNT_ANALYSIS_RATE_TTL_SECONDS)
    if rate_value <= ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR:
        return
    raise AccountAnalysisRateLimitError(
        message=(
            f"Rate limit exceeded for account_id='{account_id}'. "
            f"Maximum {ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR} account-analysis requests per hour."
        ),
        job_id=running_job_id,
    )


def enqueue_account_analysis_job(payload: dict[str, Any]) -> dict[str, str]:
    """Enqueue account analysis background job and persist queued status."""
    payload = payload if isinstance(payload, dict) else {}
    account_id = _normalize_account_id(payload.get("account_id"))
    post_limit = _normalize_post_limit(payload.get("post_limit", 30))
    include_posts_summary = _normalize_include_posts_summary(payload.get("include_posts_summary", False))
    include_posts_summary_max = _normalize_include_posts_summary_max(payload.get("include_posts_summary_max", 30))
    payload_hash = _compute_posts_payload_hash(payload)

    reusable_job_id, reusable_status = _resolve_reusable_job(
        account_id=account_id,
        post_limit=post_limit,
        payload_hash=payload_hash,
    )
    if reusable_job_id and reusable_status:
        return {"job_id": reusable_job_id, "status": reusable_status}
    _enforce_rate_limit(account_id, running_job_id=None)

    queue = get_queue()
    raw_job_id = _normalize_job_id(payload.get("job_id"))
    job_id = raw_job_id or str(uuid4())
    full_payload = dict(payload)
    full_payload["job_id"] = job_id
    full_payload["account_id"] = account_id
    full_payload["post_limit"] = post_limit
    full_payload["include_posts_summary"] = include_posts_summary
    full_payload["include_posts_summary_max"] = include_posts_summary_max

    initialize_job_status(job_id)
    _write_dedupe_job_id(account_id, post_limit, job_id)
    _write_inputhash_job_id(account_id, payload_hash, job_id)
    queue.enqueue(
        run_account_analysis_job,
        full_payload,
        job_id=job_id,
        job_timeout=DEFAULT_JOB_TIMEOUT_SECONDS,
        result_ttl=DEFAULT_RESULT_TTL_SECONDS,
        failure_ttl=DEFAULT_FAILURE_TTL_SECONDS,
        retry=Retry(max=2, interval=[10, 30]),
    )
    return {"job_id": job_id, "status": "queued"}


def _coerce_single_post(item: Any) -> SinglePostInsights:
    if isinstance(item, SinglePostInsights):
        return item
    if isinstance(item, dict):
        return SinglePostInsights.model_validate(item)
    raise ValueError("Unsupported post payload type; expected SinglePostInsights or dict.")


def _fetch_posts_from_source(payload: dict[str, Any], post_limit: int) -> list[SinglePostInsights]:
    raw_posts = payload.get("posts")
    if isinstance(raw_posts, list):
        posts: list[SinglePostInsights] = []
        for item in raw_posts[:post_limit]:
            posts.append(_coerce_single_post(item))
        return posts

    raise ValueError("No post source configured. Provide precomputed posts in payload['posts'].")


def _build_warning(
    *,
    code: str,
    message: str,
    post_id: str | None = None,
) -> dict[str, Any]:
    warning: dict[str, Any] = {
        "component": "vision",
        "code": code,
        "message": message,
    }
    if isinstance(post_id, str) and post_id.strip():
        warning["post_id"] = post_id.strip()
    return warning


def _append_unique_warning(warnings: list[dict[str, Any]], warning: dict[str, Any]) -> None:
    key = (
        warning.get("component"),
        warning.get("code"),
        warning.get("message"),
        warning.get("post_id"),
    )
    for existing in warnings:
        existing_key = (
            existing.get("component"),
            existing.get("code"),
            existing.get("message"),
            existing.get("post_id"),
        )
        if existing_key == key:
            return
    warnings.append(warning)


def _quality_payload(vision_enabled: bool) -> dict[str, Any]:
    return {
        "vision_enabled": bool(vision_enabled),
        "vision_error_count": 0,
        "ai_fallback_count": 0,
    }


def _caption_preview(value: str | None, max_len: int = 120) -> str:
    if not isinstance(value, str):
        return ""
    return value[:max_len]


def _normalize_summary_post_type(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if normalized in {"IMAGE", "REEL"}:
        return normalized
    return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded_media_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > 2048:
        return None
    return text


def _build_post_summary(
    post: SinglePostInsights,
    *,
    vision_enabled: bool,
    note_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    note_overrides = note_overrides or {}
    vision_status = note_overrides.get("vision_status")
    if vision_status not in {"ok", "error", "disabled"}:
        vision_analysis = post.vision_analysis
        if vision_analysis is not None and isinstance(vision_analysis.status, str):
            if vision_analysis.status == "ok":
                vision_status = "ok"
            elif vision_analysis.status == "error":
                vision_status = "error"
            else:
                vision_status = "disabled" if not vision_enabled else "ok"
        else:
            vision_status = "disabled" if not vision_enabled else "ok"

    fallback_used = bool(note_overrides.get("fallback_used", False))
    summary = {
        "post_id": post.media_id,
        "shortcode": None,
        "post_type": _normalize_summary_post_type(post.media_type),
        "media_url": _bounded_media_url(post.media_url),
        "caption_preview": _caption_preview(post.caption_text, max_len=120),
        "scores": {
            "S1": _safe_float(post.visual_quality_score.total if post.visual_quality_score is not None else None),
            "S2": _safe_float(
                post.caption_effectiveness_score.total_0_50 if post.caption_effectiveness_score is not None else None
            ),
            "S3": _safe_float(post.content_clarity_score.total if post.content_clarity_score is not None else None),
            "S4": _safe_float(
                post.audience_relevance_score.total_0_50 if post.audience_relevance_score is not None else None
            ),
            "S5": _safe_float(post.engagement_potential_score.total if post.engagement_potential_score is not None else None),
            "S6": _safe_float(post.brand_safety_score.total_0_50 if post.brand_safety_score is not None else None),
            "P": _safe_float(post.weighted_post_score.score if post.weighted_post_score is not None else None),
            "predicted_er": _safe_float(post.predicted_engagement_rate),
        },
        "notes": {
            "vision_status": vision_status,
            "fallback_used": fallback_used,
        },
    }
    return summary


def _bounded_posts_summary(
    posts: list[SinglePostInsights],
    *,
    include_posts_summary_max: int,
    vision_enabled: bool,
    notes_by_post_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for post in posts:
        post_id = post.media_id if isinstance(post.media_id, str) else ""
        summaries.append(
            _build_post_summary(
                post,
                vision_enabled=vision_enabled,
                note_overrides=notes_by_post_id.get(post_id),
            )
        )
    summaries.sort(key=lambda item: (str(item.get("post_id") or ""), str(item.get("media_url") or "")))
    return summaries[:include_posts_summary_max]


def _warning_code(warning: dict[str, Any]) -> str | None:
    code = warning.get("code")
    return code if isinstance(code, str) else None


def _warning_post_id(warning: dict[str, Any]) -> str:
    post_id = warning.get("post_id")
    if isinstance(post_id, str):
        return post_id
    return ""


def _is_vision_warning(code: str | None) -> bool:
    return code in {"GEMINI_API_KEY_MISSING", "VISION_ERROR"}


def _increment_post_warning_count(counter: dict[str, int], post_id: str, increment_by: int = 1) -> None:
    key = post_id or ""
    counter[key] = counter.get(key, 0) + max(0, int(increment_by))


def _extract_ai_warnings(ai_analysis: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(ai_analysis, dict):
        return []
    raw = ai_analysis.get("warnings")
    if not isinstance(raw, list):
        return []
    warnings: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            warnings.append(item)
    return warnings


def _extract_ai_notes(ai_analysis: dict[str, Any] | None, *, vision_enabled: bool) -> dict[str, Any]:
    notes: dict[str, Any] = {
        "vision_status": "disabled" if not vision_enabled else "ok",
        "fallback_used": False,
    }
    if not isinstance(ai_analysis, dict):
        return notes
    vision_status = ai_analysis.get("vision_status")
    if vision_status in {"ok", "error", "disabled"}:
        notes["vision_status"] = vision_status
    notes["fallback_used"] = bool(ai_analysis.get("fallback_used", False))
    return notes


def _pipeline_result_payload(
    *,
    processed_posts: list[SinglePostInsights],
    warnings: list[dict[str, Any]],
    per_post_warnings_count: dict[str, int],
    vision_error_count: int,
    ai_fallback_count: int,
    notes_by_post_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "posts": processed_posts,
        "warnings": warnings,
        "per_post_warnings_count": per_post_warnings_count,
        "vision_error_count": int(vision_error_count),
        "ai_fallback_count": int(ai_fallback_count),
        "notes_by_post_id": notes_by_post_id,
    }


async def _run_single_post_pipeline_if_needed(
    posts: list[SinglePostInsights],
    run_single_post_pipeline: bool,
    vision_enabled: bool,
    update_progress: Callable[[str, int, int], None],
) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    per_post_warnings_count: dict[str, int] = {}
    notes_by_post_id: dict[str, dict[str, Any]] = {}
    vision_error_count = 0
    ai_fallback_count = 0

    if not run_single_post_pipeline:
        processed: list[SinglePostInsights] = []
        total = len(posts)
        for index, post in enumerate(posts, start=1):
            update_progress(stage="posts", done=index, total=total)
            processed.append(post)
        return _pipeline_result_payload(
            processed_posts=processed,
            warnings=warnings,
            per_post_warnings_count=per_post_warnings_count,
            vision_error_count=vision_error_count,
            ai_fallback_count=ai_fallback_count,
            notes_by_post_id=notes_by_post_id,
        )

    processed_posts: list[SinglePostInsights] = []
    total = len(posts)
    for index, post in enumerate(posts, start=1):
        update_progress(stage="posts", done=index - 1, total=total)
        appended = False
        try:
            historical = [candidate for candidate in posts if candidate.media_id != post.media_id]
            pipeline_result = await build_single_post_insights(
                target_post=post,
                historical_posts=historical,
                run_ai=True,
            )
            processed_posts.append(pipeline_result["post"])
            appended = True

            ai_analysis = pipeline_result.get("ai_analysis")
            ai_warnings = _extract_ai_warnings(ai_analysis if isinstance(ai_analysis, dict) else None)
            notes = _extract_ai_notes(ai_analysis if isinstance(ai_analysis, dict) else None, vision_enabled=vision_enabled)
            post_id = post.media_id if isinstance(post.media_id, str) else ""
            notes_by_post_id[post_id] = notes

            for warning in ai_warnings:
                _append_unique_warning(warnings, warning)
                code = _warning_code(warning)
                if _is_vision_warning(code):
                    vision_error_count += 1
                _increment_post_warning_count(per_post_warnings_count, _warning_post_id(warning), 1)

            if notes.get("fallback_used") is True:
                ai_fallback_count += 1
        except Exception as exc:
            logger.warning(
                "[AccountAnalysisJob] Failed per-post analysis for media_id=%s: %s",
                getattr(post, "media_id", None),
                exc,
            )
            if not appended:
                processed_posts.append(post)
            post_id = post.media_id if isinstance(post.media_id, str) else ""
            notes_by_post_id[post_id] = {"vision_status": "error", "fallback_used": True}
            _append_unique_warning(
                warnings,
                _build_warning(
                    code="POST_PIPELINE_ERROR",
                    message="Per-post analysis failed; using raw post output.",
                    post_id=post_id,
                ),
            )
            _increment_post_warning_count(per_post_warnings_count, post_id, 1)
        finally:
            update_progress(stage="posts", done=index, total=total)
    return _pipeline_result_payload(
        processed_posts=processed_posts,
        warnings=warnings,
        per_post_warnings_count=per_post_warnings_count,
        vision_error_count=vision_error_count,
        ai_fallback_count=ai_fallback_count,
        notes_by_post_id=notes_by_post_id,
    )


def run_account_analysis_job(payload: dict[str, Any]) -> None:
    """RQ worker job entrypoint for account-level analysis."""
    payload = payload if isinstance(payload, dict) else {}
    current_job = get_current_job()
    current_job_id = _normalize_job_id(current_job.id if current_job is not None else None)
    raw_job_id = _normalize_job_id(payload.get("job_id"))
    job_id = current_job_id or raw_job_id or str(uuid4())
    account_id = _normalize_account_id(payload.get("account_id"))
    post_limit = _normalize_post_limit(payload.get("post_limit", 30))
    include_posts_summary = _normalize_include_posts_summary(payload.get("include_posts_summary", False))
    include_posts_summary_max = _normalize_include_posts_summary_max(payload.get("include_posts_summary_max", 30))
    vision_enabled = bool((os.getenv("GEMINI_API_KEY") or "").strip())
    warnings_global: list[dict[str, Any]] = []
    per_post_warnings_count: dict[str, int] = {}
    quality = _quality_payload(vision_enabled=vision_enabled)

    if not vision_enabled:
        _append_unique_warning(
            warnings_global,
            _build_warning(
                code="GEMINI_API_KEY_MISSING",
                message="Gemini vision is disabled because GEMINI_API_KEY is not set.",
            ),
        )

    def _progress(stage: str, done: int, total: int) -> None:
        _update_status(
            job_id,
            status="started",
            progress={"stage": stage, "done": int(done), "total": int(total)},
            warnings=warnings_global,
            quality=quality,
        )

    try:
        _update_status(
            job_id,
            status="started",
            started_at=_now_iso(),
            progress={"stage": "fetch", "done": 0, "total": post_limit},
            error=None,
            result=None,
            warnings=warnings_global,
            quality=quality,
        )

        posts = _fetch_posts_from_source(payload, post_limit=post_limit)
        _write_dedupe_job_id(account_id, post_limit, job_id)
        run_single_post_pipeline = _normalize_bool(payload.get("run_single_post_pipeline", False), default=False)
        pipeline_run = asyncio.run(
            _run_single_post_pipeline_if_needed(
                posts=posts,
                run_single_post_pipeline=run_single_post_pipeline,
                vision_enabled=vision_enabled,
                update_progress=_progress,
            )
        )
        processed_posts = pipeline_run["posts"]
        notes_by_post_id = pipeline_run["notes_by_post_id"]

        for warning in pipeline_run["warnings"]:
            _append_unique_warning(warnings_global, warning)
        per_post_warnings_count.update(pipeline_run["per_post_warnings_count"])
        quality["vision_error_count"] = int(pipeline_run["vision_error_count"])
        quality["ai_fallback_count"] = int(pipeline_run["ai_fallback_count"])

        if not run_single_post_pipeline and not vision_enabled:
            for post in processed_posts:
                post_id = post.media_id if isinstance(post.media_id, str) else ""
                notes_by_post_id[post_id] = {"vision_status": "disabled", "fallback_used": True}
                if post_id:
                    _increment_post_warning_count(per_post_warnings_count, post_id, 1)

        _progress(stage="aggregate", done=len(processed_posts), total=max(1, len(posts)))
        result = analyze_account_health(
            posts=processed_posts,
            account_avg_engagement_rate=payload.get("account_avg_engagement_rate"),
            niche_avg_engagement_rate=payload.get("niche_avg_engagement_rate"),
            follower_band=payload.get("follower_band"),
            use_cache=True,
        )
        result_payload = result.model_dump(mode="python")
        if include_posts_summary:
            result_payload["posts_summary"] = _bounded_posts_summary(
                processed_posts,
                include_posts_summary_max=include_posts_summary_max,
                vision_enabled=vision_enabled,
                notes_by_post_id=notes_by_post_id,
            )

        _update_status(
            job_id,
            status="succeeded",
            finished_at=_now_iso(),
            progress={"stage": "aggregate", "done": len(processed_posts), "total": max(1, len(posts))},
            error=None,
            warnings=warnings_global,
            quality=quality,
            result=result_payload,
        )
    except Exception as exc:
        logger.exception("[AccountAnalysisJob] Job failed for job_id=%s", job_id)
        _update_status(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            error={"type": exc.__class__.__name__, "message": str(exc)},
            warnings=warnings_global,
            quality=quality,
            result=None,
        )
