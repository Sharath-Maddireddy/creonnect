from __future__ import annotations

from typing import Any

from backend.app.infra.redis_client import get_json, get_redis, set_json
from backend.app.utils.logger import logger


TOKEN_KEY_PREFIX = "instagram:token:"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 55  # 55 days (tokens expire in 60 days)


def _token_key(user_id: str) -> str:
    return f"{TOKEN_KEY_PREFIX}{user_id}"


def save_token(user_id: str, token_data: dict[str, Any]) -> None:
    """Persist Instagram OAuth token data for a user."""
    key = _token_key(user_id)
    set_json(key, token_data, ttl_seconds=TOKEN_TTL_SECONDS)
    logger.info("Saved Instagram token for user_id=%s", user_id)


def get_token(user_id: str) -> dict[str, Any] | None:
    """Load Instagram OAuth token data for a user."""
    key = _token_key(user_id)
    return get_json(key)


def delete_token(user_id: str) -> None:
    """Remove Instagram OAuth token data for a user."""
    key = _token_key(user_id)
    redis_client = get_redis()
    redis_client.delete(key)
    logger.info("Deleted Instagram token for user_id=%s", user_id)
