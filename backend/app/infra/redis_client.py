"""Redis client and JSON helpers for backend services."""

from __future__ import annotations

import json
import os
from typing import Any

from redis import Redis


DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_INCR_WITH_EXPIRE_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""
_incr_script = None


def get_redis() -> Redis:
    """Return a Redis client configured from environment."""
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    # Keep binary responses enabled for RQ, which stores pickled job payloads.
    return Redis.from_url(redis_url, decode_responses=False)


def set_json(key: str, obj: dict[str, Any], ttl_seconds: int | None = None) -> None:
    """Store JSON payload under key with optional TTL."""
    redis_client = get_redis()
    payload = json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
    if ttl_seconds is None:
        redis_client.set(key, payload)
    else:
        redis_client.set(key, payload, ex=max(1, int(ttl_seconds)))


def set_text(key: str, value: str, ttl_seconds: int | None = None) -> None:
    """Store plain text value with optional TTL."""
    redis_client = get_redis()
    if ttl_seconds is None:
        redis_client.set(key, value)
    else:
        redis_client.set(key, value, ex=max(1, int(ttl_seconds)))


def get_text(key: str) -> str | None:
    """Load plain text value from key."""
    redis_client = get_redis()
    raw = redis_client.get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return None
    return raw if isinstance(raw, str) else None


def incr_with_expire(key: str, ttl_seconds: int) -> int:
    """Increment counter and set expiry on first creation."""
    global _incr_script
    redis_client = get_redis()
    if _incr_script is None:
        _incr_script = redis_client.register_script(_INCR_WITH_EXPIRE_SCRIPT)
    value = _incr_script(keys=[key], args=[max(1, int(ttl_seconds))])
    return int(value)


def get_json(key: str) -> dict[str, Any] | None:
    """Load JSON payload from key; return None if missing/invalid."""
    redis_client = get_redis()
    raw = redis_client.get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return None
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
