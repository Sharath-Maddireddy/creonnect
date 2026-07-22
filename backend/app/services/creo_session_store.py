"""Redis-backed conversation session store for Creo Intelligence.

Each session stores the full message history as a JSON list in Redis under
the key ``creo:session:{session_id}``.  The key is given a sliding TTL so
active conversations stay alive while idle ones are automatically evicted.

Usage (async context required)::

    store = CreoSessionStore()
    messages = await store.get_messages(session_id)
    messages.append({"role": "user", "content": "..."})
    await store.save_messages(session_id, messages)
"""

from __future__ import annotations

import json
import os
from typing import Any

from backend.app.infra.redis_client import get_async_redis
from backend.app.utils.logger import logger

# ── Configuration ─────────────────────────────────────────────────────────────

_DEFAULT_SESSION_TTL_SECONDS: int = 4 * 60 * 60  # 4 hours
_MAX_MESSAGES_PER_SESSION: int = 50  # keep the last N messages to stay within context

_KEY_PREFIX = "creo:session:"


def _session_key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}"


def _session_ttl() -> int:
    raw = (os.getenv("CREO_SESSION_TTL_SECONDS") or "").strip()
    try:
        value = int(raw)
        return max(60, value)  # floor at 1 minute
    except (ValueError, TypeError):
        return _DEFAULT_SESSION_TTL_SECONDS


def _max_messages() -> int:
    raw = (os.getenv("CREO_SESSION_MAX_MESSAGES") or "").strip()
    try:
        value = int(raw)
        return max(10, value)  # floor at 10 messages
    except (ValueError, TypeError):
        return _MAX_MESSAGES_PER_SESSION


# ── Store ──────────────────────────────────────────────────────────────────────


class CreoSessionStore:
    """Async Redis-backed session store for Creo Intelligence conversations.

    All public methods are coroutines.  A single instance can be shared across
    the application (connection is managed by the underlying async Redis client).
    """

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Return the message history for *session_id*, or an empty list."""
        if not _is_valid_session_id(session_id):
            logger.warning("[CreoSession] Invalid session_id=%r; returning empty history.", session_id)
            return []

        key = _session_key(session_id)
        try:
            redis = get_async_redis()
            raw = await redis.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.error("[CreoSession] Redis read failed for key=%s: %s", key, exc)
            return []

        if raw is None:
            return []

        try:
            messages = json.loads(raw)
            if not isinstance(messages, list):
                return []
            return [m for m in messages if isinstance(m, dict)]
        except json.JSONDecodeError as exc:
            logger.error("[CreoSession] JSON decode failed for key=%s: %s", key, exc)
            return []

    # ── Write ─────────────────────────────────────────────────────────────────

    async def save_messages(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Persist *messages* for *session_id*, trimming to the allowed max.

        The TTL is refreshed on every write (sliding window) so active sessions
        stay alive.
        """
        if not _is_valid_session_id(session_id):
            logger.warning("[CreoSession] Invalid session_id=%r; skipping save.", session_id)
            return

        max_msgs = _max_messages()
        trimmed = messages[-max_msgs:] if len(messages) > max_msgs else messages

        key = _session_key(session_id)
        ttl = ttl_seconds if isinstance(ttl_seconds, int) and ttl_seconds > 0 else _session_ttl()
        payload = json.dumps(trimmed, ensure_ascii=True, separators=(",", ":"))

        try:
            redis = get_async_redis()
            await redis.set(key, payload, ex=ttl)
            logger.debug("[CreoSession] Saved %d messages for session=%s (TTL=%ds).", len(trimmed), session_id, ttl)
        except Exception as exc:  # noqa: BLE001
            logger.error("[CreoSession] Redis write failed for key=%s: %s", key, exc)

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_session(self, session_id: str) -> bool:
        """Delete the session from Redis.  Returns True if the key existed."""
        if not _is_valid_session_id(session_id):
            return False

        key = _session_key(session_id)
        try:
            redis = get_async_redis()
            deleted_count = await redis.delete(key)
            existed = deleted_count > 0
            logger.info("[CreoSession] Deleted session=%s (existed=%s).", session_id, existed)
            return existed
        except Exception as exc:  # noqa: BLE001
            logger.error("[CreoSession] Redis delete failed for key=%s: %s", key, exc)
            return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def session_exists(self, session_id: str) -> bool:
        """Return True if a session exists in Redis."""
        if not _is_valid_session_id(session_id):
            return False
        key = _session_key(session_id)
        try:
            redis = get_async_redis()
            return bool(await redis.exists(key))
        except Exception as exc:  # noqa: BLE001
            logger.error("[CreoSession] Redis exists check failed for key=%s: %s", key, exc)
            return False


# ── Validation ────────────────────────────────────────────────────────────────


def _is_valid_session_id(session_id: str) -> bool:
    """Return True for non-empty strings with no dangerous Redis key characters."""
    if not isinstance(session_id, str):
        return False
    stripped = session_id.strip()
    if not stripped or len(stripped) > 128:
        return False
    # Disallow characters that could manipulate Redis key namespaces
    forbidden = {"\n", "\r", "\x00", " "}
    return not any(ch in stripped for ch in forbidden)


# ── Module-level singleton ────────────────────────────────────────────────────

_session_store: CreoSessionStore | None = None


def get_session_store() -> CreoSessionStore:
    """Return the module-level singleton session store."""
    global _session_store
    if _session_store is None:
        _session_store = CreoSessionStore()
    return _session_store
