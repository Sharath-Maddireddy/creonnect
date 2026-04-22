"""Cache helpers for loading single-post insights by media_id."""

from __future__ import annotations

import threading
from typing import Any

from backend.app.domain.post_models import SinglePostInsights
from backend.app.infra.redis_client import get_json, set_json
from backend.app.utils.logger import logger


POST_INSIGHTS_CACHE_KEY_PREFIX = "post:insights:"
POST_INSIGHTS_CACHE_TTL_SECONDS = 86400
_POST_INSIGHTS_CACHE: dict[str, dict[str, Any]] = {}
_POST_INSIGHTS_CACHE_LOCK = threading.Lock()


def _post_insights_key(media_id: str) -> str:
    return f"{POST_INSIGHTS_CACHE_KEY_PREFIX}{media_id}"


def write_post_insights_snapshot(
    media_id: str,
    *,
    post: SinglePostInsights,
    ai_analysis: dict[str, Any] | None,
) -> None:
    normalized_media_id = media_id.strip() if isinstance(media_id, str) else ""
    if not normalized_media_id:
        return

    payload = {
        "post": post.model_dump(mode="json"),
        "ai_analysis": ai_analysis if isinstance(ai_analysis, dict) else None,
    }

    try:
        set_json(
            _post_insights_key(normalized_media_id),
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
        _POST_INSIGHTS_CACHE[normalized_media_id] = payload


def read_post_insights_snapshot(media_id: str) -> dict[str, Any] | None:
    normalized_media_id = media_id.strip() if isinstance(media_id, str) else ""
    if not normalized_media_id:
        return None

    try:
        payload = get_json(_post_insights_key(normalized_media_id))
    except Exception as exc:
        logger.warning(
            "[PostSnapshotStore] Failed to read post insights snapshot for media_id=%s: %s",
            normalized_media_id,
            exc,
        )
        payload = None

    if isinstance(payload, dict):
        with _POST_INSIGHTS_CACHE_LOCK:
            _POST_INSIGHTS_CACHE[normalized_media_id] = payload
        return payload

    with _POST_INSIGHTS_CACHE_LOCK:
        cached_payload = _POST_INSIGHTS_CACHE.get(normalized_media_id)
    return cached_payload if isinstance(cached_payload, dict) else None
