"""RQ job orchestration for account-level analysis."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from rq import Retry, get_current_job

from backend.app.account_sources.creonnect_bd_client import CreonnectBDClient
from backend.app.account_sources import materialize_account_source_payload
from backend.app.domain.post_models import SinglePostInsights
import backend.app.infra.redis_client as redis_client
from backend.app.infra.job_queue import (
    ACCOUNT_ANALYSIS_JOB_NAME,
    ACCOUNT_ANALYSIS_QUEUE_NAME,
    enqueue_callable,
)
from backend.app.infra.rq_queue import (
    DEFAULT_FAILURE_TTL_SECONDS,
    DEFAULT_JOB_TIMEOUT_SECONDS,
    DEFAULT_RESULT_TTL_SECONDS,
    get_queue as get_rq_queue,
)
from backend.app.analytics.account_health_engine import (
    compute_account_engagement_signals,
    compute_account_vision_summary,
    compute_content_type_performance,
)
from backend.app.analytics.creator_scoring_engine import calculate_creator_score
from backend.app.analytics.reel_analysis_service import compute_reel_analysis
from backend.app.analytics.reel_audio_engine import compute_reel_audio_score
from backend.app.analytics.reel_gemini_engine import run_reel_gemini_analysis
from backend.app.services.account_ai_intelligence import generate_creator_intelligence
from backend.app.services.account_analysis_result_store import persist_account_analysis_result
from backend.app.services.account_analysis_service import analyze_account_health
from backend.app.services.post_insights_service import build_single_post_insights
from backend.app.utils.logger import logger
from backend.app.utils.number_utils import now_iso as _now_iso, safe_float as _safe_float
from backend.app.infra.redis_job_store import RedisJobStore
from backend.app.workers.embedding_worker import upsert_creator


ACCOUNT_ANALYSIS_JOB_KEY_PREFIX = "account_analysis:job:"
ACCOUNT_ANALYSIS_DEDUPE_KEY_PREFIX = "account_analysis:dedupe:"
ACCOUNT_ANALYSIS_RATE_KEY_PREFIX = "account_analysis:rate:"
ACCOUNT_ANALYSIS_INPUTHASH_KEY_PREFIX = "account_analysis:inputhash:"
ACCOUNT_ANALYSIS_STATUS_TTL_SECONDS = 86400
ACCOUNT_ANALYSIS_DEDUPE_TTL_SECONDS = 7200
ACCOUNT_ANALYSIS_INPUTHASH_TTL_SECONDS = 86400
ACCOUNT_ANALYSIS_RATE_TTL_SECONDS = 3600
ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR = 3

_store = RedisJobStore(ACCOUNT_ANALYSIS_JOB_KEY_PREFIX, ACCOUNT_ANALYSIS_STATUS_TTL_SECONDS)
_ACCOUNT_EXTRA_STATUS_FIELDS: dict = {"progress": None, "warnings": [], "quality": None}
ACCOUNT_ANALYSIS_QUEUED_STALE_SECONDS = max(900, DEFAULT_JOB_TIMEOUT_SECONDS + 300)
ACCOUNT_ANALYSIS_STARTED_STALE_SECONDS = max(1800, DEFAULT_JOB_TIMEOUT_SECONDS * 2)

_ACTIVE_REUSABLE_STATUSES = {"queued", "started", "succeeded"}
_RUNNING_STATUSES = {"queued", "started"}
_GEMINI_CONCURRENCY_LIMIT = 8
_ACCOUNT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,120}$")

_ASYNC_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_ASYNC_BRIDGE_THREAD: Thread | None = None
_ASYNC_BRIDGE_LOCK = Lock()


def get_redis():
    return redis_client.get_redis()


def get_json(key: str):
    return redis_client.get_json(key)


def get_text(key: str):
    return redis_client.get_text(key)


def set_json(key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
    redis_client.set_json(key, value, ttl_seconds=ttl_seconds)


def set_text(key: str, value: str, ttl_seconds: int | None = None) -> None:
    redis_client.set_text(key, value, ttl_seconds=ttl_seconds)


class AccountAnalysisRateLimitError(Exception):
    """Raised when account analysis enqueue rate limit is exceeded."""

    def __init__(self, message: str, job_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.job_id = job_id


def get_queue():
    """Compatibility wrapper for tests that monkeypatch queue transport."""
    return get_rq_queue(ACCOUNT_ANALYSIS_QUEUE_NAME)


def _dedupe_key(account_id: str, post_limit: int) -> str:
    return f"{ACCOUNT_ANALYSIS_DEDUPE_KEY_PREFIX}{account_id}:{post_limit}"


def _rate_key(account_id: str) -> str:
    return f"{ACCOUNT_ANALYSIS_RATE_KEY_PREFIX}{account_id}"


def _inputhash_key(account_id: str, payload_hash: str) -> str:
    return f"{ACCOUNT_ANALYSIS_INPUTHASH_KEY_PREFIX}{account_id}:{payload_hash}"


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


def _connection_id_from_payload(payload: dict[str, Any]) -> str | None:
    value = payload.get("connection_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    source_meta = payload.get("source_meta")
    if isinstance(source_meta, dict):
        meta_value = source_meta.get("connection_id")
        if isinstance(meta_value, str) and meta_value.strip():
            return meta_value.strip()
    return None


def _publish_result_to_creonnect_bd(
    *,
    payload: dict[str, Any],
    result_payload: dict[str, Any],
    job_id: str,
) -> None:
    source = payload.get("source")
    if not (isinstance(source, str) and source.strip().lower() == "creonnect_bd"):
        return
    connection_id = _connection_id_from_payload(payload)
    if not connection_id:
        logger.warning("[AccountAnalysisJob] Skipping creonnect-bd sync: missing connection_id job_id=%s", job_id)
        return

    account_level = dict(result_payload)
    posts_summary = account_level.pop("posts_summary", None)
    post_items: list[dict[str, Any]] = []
    if isinstance(posts_summary, list):
        for item in posts_summary:
            if not isinstance(item, dict):
                continue
            post_id = item.get("post_id")
            if not isinstance(post_id, str) or not post_id.strip():
                continue
            post_items.append(
                {
                    "post_id": post_id.strip(),
                    "ai_analysis": item,
                }
            )

    client = CreonnectBDClient(
        base_url=payload.get("bd_base_url") if isinstance(payload.get("bd_base_url"), str) else None,
        timeout_seconds=payload.get("bd_timeout_seconds") if isinstance(payload.get("bd_timeout_seconds"), (int, float)) else None,
    )
    logger.info(
        "[AccountAnalysisJob] Syncing analysis to creonnect-bd job_id=%s connection_id=%s posts=%s",
        job_id,
        connection_id,
        len(post_items),
    )
    _run_coroutine_sync(
        client.update_connection_ai_analysis(
            platform="instagram",
            connection_id=connection_id,
            ai_analysis=account_level,
        )
    )
    if post_items:
        _run_coroutine_sync(
            client.update_posts_ai_analysis(
                platform="instagram",
                connection_id=connection_id,
                items=post_items,
            )
        )
    logger.info("[AccountAnalysisJob] Synced analysis to creonnect-bd job_id=%s connection_id=%s", job_id, connection_id)


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
    payload = _store.get(job_id)
    if not isinstance(payload, dict):
        return None
    sanitized = _sanitize_status_payload(payload)
    return _project_stale_failed_status(sanitized)


def _update_status(job_id: str, **updates: Any) -> dict[str, Any]:
    payload = _store.get(job_id) or _store.base_status(job_id, _ACCOUNT_EXTRA_STATUS_FIELDS)
    payload.update(updates)
    _store.write(job_id, payload)
    return payload


def initialize_job_status(job_id: str) -> dict[str, Any]:
    existing = get_account_analysis_job_status(job_id)
    if existing:
        return existing
    payload = _store.base_status(job_id, _ACCOUNT_EXTRA_STATUS_FIELDS)
    _store.write(job_id, payload)
    return payload



def get_account_analysis_job_status(job_id: str) -> dict[str, Any] | None:
    return _read_status_with_guard(job_id)


def _normalize_account_id(value: Any) -> str:
    account_id = value.strip() if isinstance(value, str) else ""
    if not account_id:
        raise ValueError("account_id is required for account analysis jobs.")
    if not _ACCOUNT_ID_PATTERN.fullmatch(account_id):
        raise ValueError(
            "account_id must be 1-120 characters and contain only letters, numbers, or underscores."
        )
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


def _delete_dedupe_job_id(account_id: str, post_limit: int, job_id: str) -> None:
    key = _dedupe_key(account_id, post_limit)
    redis_client = get_redis()
    payload = get_json(key)
    if isinstance(payload, dict) and payload.get("job_id") == job_id:
        redis_client.delete(key)


def _compute_posts_payload_hash(payload: dict[str, Any]) -> str | None:
    posts = payload.get("posts")
    if not isinstance(posts, list):
        return None
    serialized = json.dumps(posts, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _coalesce_account_id(*values: Any) -> str:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    raise ValueError("account_id is required for account analysis jobs.")


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


def _delete_inputhash_job_id(account_id: str, payload_hash: str | None, job_id: str) -> None:
    if not payload_hash:
        return
    key = _inputhash_key(account_id, payload_hash)
    existing_job_id = get_text(key)
    if existing_job_id == job_id:
        get_redis().delete(key)


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
    redis_client = get_redis()
    rate_key = _rate_key(account_id)
    pipe = redis_client.pipeline()
    pipe.incr(rate_key)
    pipe.expire(rate_key, ACCOUNT_ANALYSIS_RATE_TTL_SECONDS)
    rate_value, _ = pipe.execute()
    rate_value = int(rate_value)
    if rate_value <= ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR:
        return
    raise AccountAnalysisRateLimitError(
        message=(
            f"Rate limit exceeded for account_id='{account_id}'. "
            f"Maximum {ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR} account-analysis requests per hour."
        ),
        job_id=running_job_id,
    )

def _restore_rate_limit_counter(account_id: str) -> None:
    rate_key = _rate_key(account_id)
    redis_client = get_redis()
    value = redis_client.decr(rate_key)
    if int(value) <= 0:
        redis_client.delete(rate_key)


T = Any  # simple TypeVar alias for _try_nonfatal


def _try_nonfatal(label: str, fn: Callable[[], Any], account_id: str, fallback: Any = None) -> Any:
    """Call fn(); on any Exception log a non-fatal warning and return fallback."""
    try:
        return fn()
    except Exception as exc:
        logger.warning("[AccountAnalysisJob] Non-fatal: %s failed for %s: %s", label, account_id, exc)
        return fallback


def _run_coroutine_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    loop = _get_async_bridge_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def _get_async_bridge_loop() -> asyncio.AbstractEventLoop:
    global _ASYNC_BRIDGE_LOOP, _ASYNC_BRIDGE_THREAD
    with _ASYNC_BRIDGE_LOCK:
        if _ASYNC_BRIDGE_LOOP is not None and _ASYNC_BRIDGE_LOOP.is_running():
            return _ASYNC_BRIDGE_LOOP

        ready = Lock()
        ready.acquire()

        def _runner() -> None:
            global _ASYNC_BRIDGE_LOOP
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _ASYNC_BRIDGE_LOOP = loop
            ready.release()
            loop.run_forever()

        _ASYNC_BRIDGE_THREAD = Thread(
            target=_runner,
            name="account-analysis-async-bridge",
            daemon=True,
        )
        _ASYNC_BRIDGE_THREAD.start()
        ready.acquire()
        ready.release()
        if _ASYNC_BRIDGE_LOOP is None:
            raise RuntimeError("Failed to initialize async bridge loop.")
        return _ASYNC_BRIDGE_LOOP

async def _materialize_posts_for_enqueue_async(
    payload: dict[str, Any],
    post_limit: int,
) -> dict[str, Any]:
    if isinstance(payload.get("posts"), list):
        sanitized_payload = dict(payload)
        sanitized_payload.pop("access_token", None)
        return sanitized_payload
    try:
        return await materialize_account_source_payload(payload, post_limit=post_limit)
    except Exception as exc:
        raise ValueError(f"Failed to materialize account source payload: {exc}") from exc


def _materialize_posts_for_enqueue(payload: dict[str, Any], post_limit: int) -> dict[str, Any]:
    """Sync-only helper. Callers in async contexts must use `_materialize_posts_for_enqueue_async`."""
    if isinstance(payload.get("posts"), list):
        sanitized_payload = dict(payload)
        sanitized_payload.pop("access_token", None)
        return sanitized_payload
    try:
        return _run_coroutine_sync(materialize_account_source_payload(payload, post_limit=post_limit))
    except Exception as exc:
        raise ValueError(f"Failed to materialize account source payload: {exc}") from exc


def _enqueue_account_analysis_job_impl(
    payload: dict[str, Any],
    *,
    sanitized_payload: dict[str, Any],
) -> dict[str, str]:
    account_id = _normalize_account_id(
        _coalesce_account_id(sanitized_payload.get("account_id"), payload.get("account_id"))
    )
    post_limit = _normalize_post_limit(payload.get("post_limit", 30))
    include_posts_summary = _normalize_include_posts_summary(payload.get("include_posts_summary", False))
    include_posts_summary_max = _normalize_include_posts_summary_max(payload.get("include_posts_summary_max", 30))
    payload_hash = _compute_posts_payload_hash(sanitized_payload)
    logger.info(
        "[AccountAnalysisJob] Enqueue prepared account_id=%s post_limit=%s source=%s posts_in_payload=%s include_posts_summary=%s",
        account_id,
        post_limit,
        sanitized_payload.get("source"),
        len(sanitized_payload.get("posts")) if isinstance(sanitized_payload.get("posts"), list) else None,
        include_posts_summary,
    )

    reusable_job_id, reusable_status = _resolve_reusable_job(
        account_id=account_id,
        post_limit=post_limit,
        payload_hash=payload_hash,
    )
    # Return the existing active job immediately - no rate-limit charge for a reuse.
    if reusable_job_id and reusable_status:
        logger.info(
            "[AccountAnalysisJob] Reusing existing job job_id=%s account_id=%s status=%s",
            reusable_job_id,
            account_id,
            reusable_status,
        )
        return {"job_id": reusable_job_id, "status": reusable_status}

    _enforce_rate_limit(account_id, running_job_id=None)

    raw_job_id = _normalize_job_id(sanitized_payload.get("job_id"))
    job_id = raw_job_id or str(uuid4())
    full_payload = dict(sanitized_payload)
    full_payload["job_id"] = job_id
    full_payload["account_id"] = account_id
    full_payload["post_limit"] = post_limit
    full_payload["include_posts_summary"] = include_posts_summary
    full_payload["include_posts_summary_max"] = include_posts_summary_max

    logger.info(
        "[AccountAnalysisJob] Queueing job job_id=%s account_id=%s post_limit=%s source=%s",
        job_id,
        account_id,
        post_limit,
        sanitized_payload.get("source"),
    )
    try:
        queue = get_queue()
        if hasattr(queue, "enqueue"):
            retry = Retry(max=2, interval=[10, 30])
            enqueued_job = queue.enqueue(
                run_account_analysis_job,
                full_payload,
                job_id=job_id,
                job_timeout=DEFAULT_JOB_TIMEOUT_SECONDS,
                result_ttl=DEFAULT_RESULT_TTL_SECONDS,
                failure_ttl=DEFAULT_FAILURE_TTL_SECONDS,
                retry=retry,
            )
            logger.info(
                "[AccountAnalysisJob] Enqueued job job_id=%s queue=%s transport_status=%s retry=%s",
                job_id,
                ACCOUNT_ANALYSIS_QUEUE_NAME,
                getattr(enqueued_job, "get_status", lambda: "queued")(),
                2,
            )
        else:
            enqueued_job = enqueue_callable(
                queue_name=ACCOUNT_ANALYSIS_QUEUE_NAME,
                job_name=ACCOUNT_ANALYSIS_JOB_NAME,
                func=run_account_analysis_job,
                payload=full_payload,
                job_id=job_id,
                timeout_seconds=DEFAULT_JOB_TIMEOUT_SECONDS,
                result_ttl_seconds=DEFAULT_RESULT_TTL_SECONDS,
                failure_ttl_seconds=DEFAULT_FAILURE_TTL_SECONDS,
                retry_max=2,
                retry_intervals=[10, 30],
            )
            logger.info(
                "[AccountAnalysisJob] Enqueued job job_id=%s queue=%s backend=%s transport_status=%s retry=%s",
                job_id,
                ACCOUNT_ANALYSIS_QUEUE_NAME,
                enqueued_job.backend,
                enqueued_job.raw_status,
                2,
            )
        # Write Redis state only after the transport has accepted the job.
        initialize_job_status(job_id)
        _write_dedupe_job_id(account_id, post_limit, job_id)
        _write_inputhash_job_id(account_id, payload_hash, job_id)
        logger.debug(
            "[AccountAnalysisJob] Dedupe/inputhash recorded job_id=%s payload_hash_prefix=%s",
            job_id,
            payload_hash[:12] if isinstance(payload_hash, str) else None,
        )
    except Exception:
        _delete_dedupe_job_id(account_id, post_limit, job_id)
        _delete_inputhash_job_id(account_id, payload_hash, job_id)
        _restore_rate_limit_counter(account_id)
        raise
    return {"job_id": job_id, "status": "queued"}



def enqueue_account_analysis_job(payload: dict[str, Any]) -> dict[str, str]:
    """Enqueue account analysis background job and persist queued status."""
    payload = payload if isinstance(payload, dict) else {}
    post_limit = _normalize_post_limit(payload.get("post_limit", 30))
    logger.info(
        "[AccountAnalysisJob] Enqueue request received sync account_id=%s post_limit=%s source=%s has_posts=%s",
        payload.get("account_id"),
        post_limit,
        payload.get("source"),
        isinstance(payload.get("posts"), list),
    )
    sanitized_payload = _materialize_posts_for_enqueue(payload, post_limit=post_limit)
    logger.debug(
        "[AccountAnalysisJob] Enqueue materialized sync account_id=%s posts=%s source=%s",
        sanitized_payload.get("account_id"),
        len(sanitized_payload.get("posts")) if isinstance(sanitized_payload.get("posts"), list) else None,
        sanitized_payload.get("source"),
    )
    return _enqueue_account_analysis_job_impl(payload, sanitized_payload=sanitized_payload)


async def enqueue_account_analysis_job_async(payload: dict[str, Any]) -> dict[str, str]:
    """Async enqueue path that materializes Instagram media without blocking the event loop."""
    payload = payload if isinstance(payload, dict) else {}
    post_limit = _normalize_post_limit(payload.get("post_limit", 30))
    logger.info(
        "[AccountAnalysisJob] Enqueue request received async account_id=%s post_limit=%s source=%s has_posts=%s",
        payload.get("account_id"),
        post_limit,
        payload.get("source"),
        isinstance(payload.get("posts"), list),
    )
    sanitized_payload = await _materialize_posts_for_enqueue_async(payload, post_limit=post_limit)
    logger.debug(
        "[AccountAnalysisJob] Enqueue materialized async account_id=%s posts=%s source=%s",
        sanitized_payload.get("account_id"),
        len(sanitized_payload.get("posts")) if isinstance(sanitized_payload.get("posts"), list) else None,
        sanitized_payload.get("source"),
    )
    return _enqueue_account_analysis_job_impl(payload, sanitized_payload=sanitized_payload)


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
    raise ValueError(
        "No post source configured. Provide precomputed posts in payload['posts'] via enqueue_account_analysis_job."
    )


def _posts_payload_has_precomputed_scores(payload: dict[str, Any]) -> bool:
    raw_posts = payload.get("posts")
    if not isinstance(raw_posts, list) or not raw_posts:
        return False

    required_keys = {
        "visual_quality_score",
        "content_clarity_score",
        "caption_effectiveness_score",
        "engagement_potential_score",
        "brand_safety_score",
        "weighted_post_score",
    }

    for item in raw_posts:
        if isinstance(item, SinglePostInsights):
            return True
        if isinstance(item, dict):
            has_all_keys = all(key in item for key in required_keys)
            has_no_none = all(item.get(key) is not None for key in required_keys)
            if has_all_keys and has_no_none:
                return True
    return False


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


def _bounded_media_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > 2048:
        return None
    return text


def _is_reel_post(post: SinglePostInsights) -> bool:
    media_type = post.media_type if isinstance(post.media_type, str) else ""
    return media_type.strip().upper() == "REEL"


def _maybe_attach_inline_reel_analysis(post: SinglePostInsights) -> SinglePostInsights:
    if not _is_reel_post(post):
        return post

    media_url = post.media_url if isinstance(post.media_url, str) else ""
    logger.info(
        "[AccountAnalysisJob] Detected REEL post for inline reel analysis media_id=%s",
        post.media_id,
    )
    if not media_url.strip():
        logger.info(
            "[AccountAnalysisJob] Skipping inline reel analysis for media_id=%s: missing media_url",
            post.media_id,
        )
        return post

    try:
        logger.info(
            "[AccountAnalysisJob] Starting inline reel analysis media_id=%s",
            post.media_id,
        )
        vision_result = run_reel_gemini_analysis(media_url.strip())
        vision_status = str(vision_result.get("status", "error"))
        signals = vision_result.get("signals", {})
        if not isinstance(signals, dict):
            signals = {}
        logger.info(
            "[AccountAnalysisJob] Inline reel vision result media_id=%s status=%s signal_keys=%s",
            post.media_id,
            vision_status,
            sorted(signals.keys()),
        )

        audio_score = compute_reel_audio_score(
            audio_name=None,
            caption_text=post.caption_text,
        )
        reel_model = compute_reel_analysis(
            reel_vision_signals=signals,
            audio_score=audio_score,
            watch_time_pct=None,
            reel_vision_status=vision_status,
        )
        logger.info(
            "[AccountAnalysisJob] Inline reel analysis complete media_id=%s status=%s total=%s",
            post.media_id,
            vision_status,
            reel_model.total,
        )
        logger.info(
            "[AccountAnalysisJob] Attached reel_analysis to post media_id=%s",
            post.media_id,
        )
        return post.model_copy(update={"reel_analysis": reel_model})
    except Exception as exc:
        logger.warning(
            "[AccountAnalysisJob] Non-fatal: inline reel analysis failed for media_id=%s: %s",
            post.media_id,
            exc,
        )
        return post


def _build_post_summary(
    post: SinglePostInsights,
    *,
    vision_enabled: bool,
    note_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    note_overrides = note_overrides or {}
    first_signal = None
    try:
        vision_signals = post.vision_analysis.signals if post.vision_analysis is not None else []
        first_signal = vision_signals[0] if vision_signals else None
    except Exception:
        first_signal = None
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
    ai_summary = note_overrides.get("ai_summary")
    if not isinstance(ai_summary, str) or not ai_summary.strip():
        ai_summary = getattr(first_signal, "scene_description", None) if first_signal is not None else None
    if isinstance(ai_summary, str):
        ai_summary = ai_summary.strip() or None
    summary = {
        "post_id": post.media_id,
        "shortcode": None,
        "post_type": _normalize_summary_post_type(post.media_type),
        "media_url": _bounded_media_url(post.media_url),
        "caption_preview": _caption_preview(post.caption_text, max_len=120),
        "ai_summary": ai_summary,
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
            "cringe_score": _safe_float(getattr(first_signal, "cringe_score", None)) if first_signal is not None else None,
            "cringe_label": getattr(first_signal, "cringe_label", None) if first_signal is not None else None,
            "production_level": getattr(first_signal, "production_level", None) if first_signal is not None else None,
            "hook_strength_score": _safe_float(getattr(first_signal, "hook_strength_score", None)) if first_signal is not None else None,
            "technical_flaws": list(getattr(first_signal, "technical_flaws", []) or [])[:],
        },
    }
    if post.reel_analysis is not None:
        logger.info(
            "[AccountAnalysisJob] Including reel_analysis in posts_summary media_id=%s total=%s",
            post.media_id,
            post.reel_analysis.total,
        )
        summary["reel_analysis"] = post.reel_analysis.model_dump(mode="python")
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


def _draft_optimizer_history(posts: list[SinglePostInsights], limit: int = 12) -> list[dict[str, Any]]:
    ordered_posts = sorted(
        posts,
        key=lambda post: (
            post.published_at.isoformat() if post.published_at is not None else "",
            str(post.media_id or ""),
        ),
        reverse=True,
    )
    return [post.model_dump(mode="json") for post in ordered_posts[:limit]]


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
        "ai_summary": None,
        "analysis_failure_reason": None,
    }
    if not isinstance(ai_analysis, dict):
        return notes
    vision_status = ai_analysis.get("vision_status")
    if vision_status in {"ok", "error", "disabled"}:
        notes["vision_status"] = vision_status
    notes["fallback_used"] = bool(ai_analysis.get("fallback_used", False))
    summary = ai_analysis.get("summary")
    if isinstance(summary, str) and summary.strip():
        notes["ai_summary"] = summary.strip()
    explicit_reason = ai_analysis.get("vision_error_reason")
    if isinstance(explicit_reason, str) and explicit_reason.strip():
        notes["analysis_failure_reason"] = explicit_reason.strip()
        return notes

    raw_warnings = ai_analysis.get("warnings")
    if isinstance(raw_warnings, list):
        for item in raw_warnings:
            if not isinstance(item, dict):
                continue
            if item.get("code") != "VISION_ERROR":
                continue
            warning_message = item.get("message")
            if isinstance(warning_message, str) and warning_message.strip():
                notes["analysis_failure_reason"] = warning_message.strip()
                break
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
            processed.append(_maybe_attach_inline_reel_analysis(post))
        return _pipeline_result_payload(
            processed_posts=processed,
            warnings=warnings,
            per_post_warnings_count=per_post_warnings_count,
            vision_error_count=vision_error_count,
            ai_fallback_count=ai_fallback_count,
            notes_by_post_id=notes_by_post_id,
        )



    semaphore = asyncio.Semaphore(_GEMINI_CONCURRENCY_LIMIT)
    total = len(posts)

    async def _analyse_one(post: SinglePostInsights) -> tuple[SinglePostInsights, dict[str, Any], list[dict[str, Any]], bool]:
        try:
            async with semaphore:
                historical = [candidate for candidate in posts if candidate.media_id != post.media_id]
                pipeline_result = await build_single_post_insights(
                    target_post=post,
                    historical_posts=historical,
                    run_ai=True,
                )
            processed_post = _maybe_attach_inline_reel_analysis(pipeline_result["post"])
            ai_analysis = pipeline_result.get("ai_analysis")
            ai_warnings = _extract_ai_warnings(ai_analysis if isinstance(ai_analysis, dict) else None)
            notes = _extract_ai_notes(ai_analysis if isinstance(ai_analysis, dict) else None, vision_enabled=vision_enabled)
            fallback_used = notes.get("fallback_used") is True
            return processed_post, notes, ai_warnings, fallback_used
        except Exception as exc:
            logger.warning(
                "[AccountAnalysisJob] Failed per-post analysis for media_id=%s: %s",
                getattr(post, "media_id", None),
                exc,
            )
            post_id = post.media_id if isinstance(post.media_id, str) else ""
            return (
                post,
                {"vision_status": "error", "fallback_used": True},
                [
                    _build_warning(
                        code="POST_PIPELINE_ERROR",
                        message="Per-post analysis failed; using raw post output.",
                        post_id=post_id,
                    )
                ],
                False,
            )

    results = await asyncio.gather(*[_analyse_one(post) for post in posts], return_exceptions=False)

    processed_posts: list[SinglePostInsights] = []
    for post, result in zip(posts, results, strict=False):
        processed_post, notes, ai_warnings, fallback_used = result
        processed_posts.append(processed_post)
        post_id = post.media_id if isinstance(post.media_id, str) else ""
        notes_by_post_id[post_id] = notes

        for warning in ai_warnings:
            _append_unique_warning(warnings, warning)
            code = _warning_code(warning)
            if _is_vision_warning(code):
                vision_error_count += 1
            _increment_post_warning_count(per_post_warnings_count, _warning_post_id(warning), 1)

        if fallback_used:
            ai_fallback_count += 1

    update_progress(stage="posts", done=total, total=total)
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
    logger.info(
        "[AccountAnalysisJob] Picked from queue job_id=%s rq_ pjob_id=%s queue=%s payload_keys=%s",
        job_id,
        current_job_id or None,
        getattr(getattr(current_job, "origin", None), "strip", lambda: getattr(current_job, "origin", None))()
        if current_job is not None
        else None,
        sorted(payload.keys()),
    )

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
        logger.info(
            "[AccountAnalysisJob] Started job_id=%s account_id=%s post_limit=%s vision_enabled=%s",
            job_id,
            account_id,
            post_limit,
            vision_enabled,
        )
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
        logger.info(
            "[AccountAnalysisJob] Fetched posts job_id=%s account_id=%s count=%s",
            job_id,
            account_id,
            len(posts),
        )
        _write_dedupe_job_id(account_id, post_limit, job_id)
        run_single_post_pipeline = not _posts_payload_has_precomputed_scores(payload)
        logger.info(
            "[AccountAnalysisJob] Running post pipeline job_id=%s account_id=%s enabled=%s",
            job_id,
            account_id,
            run_single_post_pipeline,
        )
        pipeline_run = _run_coroutine_sync(
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

        logger.info(
            "[AccountAnalysisJob] Aggregating account result job_id=%s account_id=%s processed_posts=%s warnings=%s",
            job_id,
            account_id,
            len(processed_posts),
            len(warnings_global),
        )
        _progress(stage="aggregate", done=len(processed_posts), total=max(1, len(posts)))
        result = analyze_account_health(
            posts=processed_posts,
            account_avg_engagement_rate=payload.get("account_avg_engagement_rate"),
            niche_avg_engagement_rate=payload.get("niche_avg_engagement_rate"),
            follower_band=payload.get("follower_band"),
            use_cache=True,
        )
        creator_score = _try_nonfatal(
            "creator scoring",
            lambda: calculate_creator_score(processed_posts, payload if isinstance(payload, dict) else {}),
            account_id,
        )

        engagement_signals = _try_nonfatal(
            "engagement signals",
            lambda: compute_account_engagement_signals(processed_posts),
            account_id,
        )

        vision_summary = _try_nonfatal(
            "vision summary",
            lambda: compute_account_vision_summary(processed_posts),
            account_id,
        )

        try:
            creator_intelligence = _run_coroutine_sync(
                generate_creator_intelligence(
                    posts=processed_posts,
                    account_id=account_id,
                    username=payload.get("username"),
                    bio=payload.get("bio"),
                    niche_tags=payload.get("niche_tags"),
                    creator_dominant_category=payload.get("creator_dominant_category"),
                    follower_count=payload.get("follower_count"),
                )
            )
        except Exception as intel_exc:
            logger.warning(
                "[AccountAnalysisJob] Non-fatal: creator intelligence failed for %s: %s",
                account_id,
                intel_exc,
            )
            from backend.app.domain.account_models import CreatorIntelligence

            creator_intelligence = CreatorIntelligence()

        content_type_performance = _try_nonfatal(
            "content type performance",
            lambda: compute_content_type_performance(processed_posts),
            account_id,
        )

        def _attach_signals() -> None:
            result.creator_intelligence = creator_intelligence
            result.vision_summary = vision_summary
            result.engagement_signals = engagement_signals
            result.content_type_performance = content_type_performance
        _try_nonfatal("attaching account signals", _attach_signals, account_id)

        result_payload = result.model_dump(mode="python")
        if creator_score is not None:
            result_payload["creator_score"] = creator_score.model_dump(mode="python")
        persisted_result_payload = dict(result_payload)
        persisted_result_payload["draft_optimizer_history"] = _draft_optimizer_history(processed_posts)

        def _enqueue_embedding() -> None:
            upsert_creator({
                "account_id": account_id,
                "username": payload.get("username"),
                "bio": payload.get("bio"),
                "follower_count": payload.get("follower_count"),
                "creator_dominant_category": payload.get("creator_dominant_category"),
                "niche_tags": payload.get("niche_tags") or [],
                "ahs_score": result.ahs_score,
                "predicted_engagement_rate": result.pillars["engagement_quality"].score if "engagement_quality" in result.pillars else None,
                "avg_visual_quality_score": result.pillars["content_quality"].score if "content_quality" in result.pillars else None,
                "avg_brand_safety_score": result.pillars["brand_safety"].score if "brand_safety" in result.pillars else None,
                "avg_views": sum((post.core_metrics.reach or 0) if post.core_metrics else 0 for post in processed_posts) / len(processed_posts) if processed_posts else 0,
                "avg_likes": sum((post.core_metrics.likes or 0) if post.core_metrics else 0 for post in processed_posts) / len(processed_posts) if processed_posts else 0,
                "avg_comments": sum((post.core_metrics.comments or 0) if post.core_metrics else 0 for post in processed_posts) / len(processed_posts) if processed_posts else 0,
                "posts_per_week": result.metadata.post_count_used / (result.metadata.time_window_days / 7) if getattr(result.metadata, "time_window_days", None) else 0,
            })
        _try_nonfatal("embedding ingestion", _enqueue_embedding, account_id)

        try:
            if include_posts_summary:
                result_payload["posts_summary"] = _bounded_posts_summary(
                    processed_posts,
                    include_posts_summary_max=include_posts_summary_max,
                    vision_enabled=vision_enabled,
                    notes_by_post_id=notes_by_post_id,
                )
        except Exception as summary_exc:
            logger.warning(
                "[AccountAnalysisJob] Non-fatal: failed to build posts_summary for %s: %s",
                account_id,
                summary_exc,
            )

        logger.info(
            "[AccountAnalysisJob] Succeeded job_id=%s account_id=%s ahs_score=%s warnings=%s vision_errors=%s ai_fallbacks=%s",
            job_id,
            account_id,
            getattr(result, "ahs_score", None),
            len(warnings_global),
            quality.get("vision_error_count"),
            quality.get("ai_fallback_count"),
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
        persist_account_analysis_result(
            job_id=job_id,
            account_id=account_id,
            username=payload.get("username") if isinstance(payload.get("username"), str) else None,
            payload=payload,
            status="succeeded",
            result=persisted_result_payload,
            warnings=warnings_global,
            quality=quality,
            error=None,
        )
    except Exception as exc:
        logger.exception("[AccountAnalysisJob] Job failed for job_id=%s", job_id)
        error_payload = {"type": exc.__class__.__name__, "message": str(exc)}
        _update_status(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            error=error_payload,
            warnings=warnings_global,
            quality=quality,
            result=None,
        )
        persist_account_analysis_result(
            job_id=job_id,
            account_id=account_id,
            username=payload.get("username") if isinstance(payload.get("username"), str) else None,
            payload=payload,
            status="failed",
            result=None,
            warnings=warnings_global,
            quality=quality,
            error=error_payload,
        )
        if current_job is not None:
            raise
