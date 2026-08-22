"""Cache helpers for loading single-post insights by media_id."""

from __future__ import annotations

import threading
from typing import Any

from backend.app.domain.post_models import SinglePostInsights
from backend.app.infra.redis_client import get_json, set_json
from backend.app.utils.logger import logger


POST_INSIGHTS_CACHE_KEY_PREFIX = "post:insights:v2r2:"
POST_INSIGHTS_CACHE_TTL_SECONDS = 86400
_POST_INSIGHTS_CACHE: dict[str, dict[str, Any]] = {}
_POST_INSIGHTS_CACHE_LOCK = threading.Lock()


def _normalize_cache_identity(account_id: str, media_id: str) -> tuple[str, str] | None:
    normalized_account_id = account_id.strip() if isinstance(account_id, str) else ""
    normalized_media_id = media_id.strip() if isinstance(media_id, str) else ""
    if not normalized_account_id or not normalized_media_id:
        return None
    return normalized_account_id, normalized_media_id


def _post_insights_key(account_id: str, media_id: str) -> str:
    return f"{POST_INSIGHTS_CACHE_KEY_PREFIX}{account_id}:{media_id}"


def write_post_insights_snapshot(
    account_id: str,
    media_id: str,
    *,
    post: SinglePostInsights,
    ai_analysis: dict[str, Any] | None,
) -> None:
    identity = _normalize_cache_identity(account_id, media_id)
    if identity is None:
        return
    normalized_account_id, normalized_media_id = identity
    cache_key = _post_insights_key(normalized_account_id, normalized_media_id)

    payload = {
        "post": post.model_dump(mode="json"),
        "ai_analysis": ai_analysis if isinstance(ai_analysis, dict) else None,
    }

    try:
        set_json(
            cache_key,
            payload,
            ttl_seconds=POST_INSIGHTS_CACHE_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "[PostSnapshotStore] Failed to write post insights snapshot for media_id=%s: %s",
            normalized_media_id,
            exc,
        )

    with _POST_INSIGHTS_CACHE_LOCK:
        _POST_INSIGHTS_CACHE[cache_key] = payload


def read_post_insights_snapshot(account_id: str, media_id: str) -> dict[str, Any] | None:
    identity = _normalize_cache_identity(account_id, media_id)
    if identity is None:
        return None
    normalized_account_id, normalized_media_id = identity
    cache_key = _post_insights_key(normalized_account_id, normalized_media_id)

    try:
        payload = get_json(cache_key)
    except Exception as exc:
        logger.warning(
            "[PostSnapshotStore] Failed to read post insights snapshot for media_id=%s: %s",
            normalized_media_id,
            exc,
        )
        payload = None

    if isinstance(payload, dict):
        with _POST_INSIGHTS_CACHE_LOCK:
            _POST_INSIGHTS_CACHE[cache_key] = payload
        return payload

    with _POST_INSIGHTS_CACHE_LOCK:
        cached_payload = _POST_INSIGHTS_CACHE.get(cache_key)
    return cached_payload if isinstance(cached_payload, dict) else None
