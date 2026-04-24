"""Redis client and JSON helpers for backend services."""

from __future__ import annotations

import json
import os
from typing import Any

from redis import Redis
from redis.asyncio import Redis as AsyncRedis


DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_redis_client: Redis | None = None
_rq_redis_client: Redis | None = None
_async_redis_client: AsyncRedis | None = None
_INCR_WITH_EXPIRE_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
elseif redis.call('TTL', KEYS[1]) == -1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""
_incr_script = None


def get_redis() -> Redis:
    """Return the synchronous application Redis client."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    _redis_client = Redis.from_url(redis_url, decode_responses=True)
    return _redis_client


def get_rq_redis() -> Redis:
    """Return the synchronous Redis client reserved for RQ/pickled payloads."""
    global _rq_redis_client
    if _rq_redis_client is not None:
        return _rq_redis_client
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    _rq_redis_client = Redis.from_url(redis_url, decode_responses=False)
    return _rq_redis_client


def get_async_redis() -> AsyncRedis:
    """Return the async application Redis client."""
    global _async_redis_client
    if _async_redis_client is not None:
        return _async_redis_client
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    _async_redis_client = AsyncRedis.from_url(redis_url, decode_responses=True)
    return _async_redis_client


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
    return raw if isinstance(raw, str) else None


def incr_with_expire(key: str, ttl_seconds: int) -> int:
    """Increment counter and ensure the key keeps a TTL."""
    global _incr_script
    redis_client = get_redis()
    if _incr_script is None:
        _incr_script = redis_client.register_script(_INCR_WITH_EXPIRE_SCRIPT)
    value = _incr_script(keys=[key], args=[max(1, int(ttl_seconds))], client=redis_client)
    return int(value)


def get_json(key: str) -> dict[str, Any] | None:
    """Load JSON payload from key; return None if missing/invalid."""
    redis_client = get_redis()
    raw = redis_client.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


async def aset_json(key: str, obj: dict[str, Any], ttl_seconds: int | None = None) -> None:
    """Store JSON payload under key with optional TTL using async Redis."""
    redis_client = get_async_redis()
    payload = json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
    if ttl_seconds is None:
        await redis_client.set(key, payload)
    else:
        await redis_client.set(key, payload, ex=max(1, int(ttl_seconds)))


async def aset_text(key: str, value: str, ttl_seconds: int | None = None) -> None:
    """Store plain text value with optional TTL using async Redis."""
    redis_client = get_async_redis()
    if ttl_seconds is None:
        await redis_client.set(key, value)
    else:
        await redis_client.set(key, value, ex=max(1, int(ttl_seconds)))


async def aget_text(key: str) -> str | None:
    """Load plain text value from key using async Redis."""
    redis_client = get_async_redis()
    raw = await redis_client.get(key)
    return raw if isinstance(raw, str) else None


async def aincr_with_expire(key: str, ttl_seconds: int) -> int:
    """Increment counter and ensure the key keeps a TTL using async Redis."""
    redis_client = get_async_redis()
    value = await redis_client.eval(_INCR_WITH_EXPIRE_SCRIPT, 1, key, max(1, int(ttl_seconds)))
    return int(value)


async def aget_json(key: str) -> dict[str, Any] | None:
    """Load JSON payload from key using async Redis."""
    redis_client = get_async_redis()
    raw = await redis_client.get(key)
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
