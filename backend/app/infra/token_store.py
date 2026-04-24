from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from backend.app.infra.redis_client import aget_json, aset_json, get_async_redis, get_json, get_redis, set_json
from backend.app.utils.logger import logger


TOKEN_KEY_PREFIX = "instagram:token:"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 55  # 55 days (tokens expire in 60 days)
_TOKEN_FERNET: Fernet | None = None
_TOKEN_KEY_WARNING_EMITTED = False


def _token_key(user_id: str) -> str:
    return f"{TOKEN_KEY_PREFIX}{user_id}"


def _build_dev_fernet_key() -> str:
    global _TOKEN_KEY_WARNING_EMITTED
    seed = (os.getenv("CREONNECT_SESSION_SECRET") or "creonnect-dev-token-key").encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    if not _TOKEN_KEY_WARNING_EMITTED:
        logger.warning("CREONNECT_TOKEN_ENCRYPTION_KEY is not set; using a derived dev-only token key.")
        _TOKEN_KEY_WARNING_EMITTED = True
    return base64.urlsafe_b64encode(digest).decode("ascii")


def _resolve_fernet() -> Fernet:
    global _TOKEN_FERNET
    if _TOKEN_FERNET is not None:
        return _TOKEN_FERNET
    configured_key = (os.getenv("CREONNECT_TOKEN_ENCRYPTION_KEY") or "").strip()
    if not configured_key:
        if os.getenv("ENV", "dev").lower() not in {"dev", "development", "test"}:
            raise RuntimeError("CREONNECT_TOKEN_ENCRYPTION_KEY must be set in production environments")
        configured_key = _build_dev_fernet_key()
    _TOKEN_FERNET = Fernet(configured_key.encode("utf-8"))
    return _TOKEN_FERNET


def _encrypt_token_payload(token_data: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(token_data, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    encrypted = _resolve_fernet().encrypt(payload).decode("ascii")
    return {"ciphertext": encrypted}


def _decrypt_token_payload(stored_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(stored_payload, dict):
        return None
    ciphertext = stored_payload.get("ciphertext")
    if not isinstance(ciphertext, str) or not ciphertext.strip():
        return stored_payload
    try:
        decrypted = _resolve_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        logger.warning("Failed to decrypt Instagram token payload: %s", exc)
        return None
    try:
        payload = json.loads(decrypted)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def save_token(user_id: str, token_data: dict[str, Any]) -> None:
    """Persist Instagram OAuth token data for a user."""
    key = _token_key(user_id)
    set_json(key, _encrypt_token_payload(token_data), ttl_seconds=TOKEN_TTL_SECONDS)
    logger.info("Saved Instagram token for user_id=%s", user_id)


def get_token(user_id: str) -> dict[str, Any] | None:
    """Load Instagram OAuth token data for a user."""
    key = _token_key(user_id)
    return _decrypt_token_payload(get_json(key))


async def save_token_async(user_id: str, token_data: dict[str, Any]) -> None:
    """Persist Instagram OAuth token data for a user via async Redis."""
    key = _token_key(user_id)
    await aset_json(key, _encrypt_token_payload(token_data), ttl_seconds=TOKEN_TTL_SECONDS)
    logger.info("Saved Instagram token for user_id=%s", user_id)


async def get_token_async(user_id: str) -> dict[str, Any] | None:
    """Load Instagram OAuth token data for a user via async Redis."""
    key = _token_key(user_id)
    return _decrypt_token_payload(await aget_json(key))


def delete_token(user_id: str) -> None:
    """Remove Instagram OAuth token data for a user."""
    key = _token_key(user_id)
    redis_client = get_redis()
    redis_client.delete(key)
    logger.info("Deleted Instagram token for user_id=%s", user_id)


async def delete_token_async(user_id: str) -> None:
    """Remove Instagram OAuth token data for a user via async Redis."""
    key = _token_key(user_id)
    redis_client = get_async_redis()
    await redis_client.delete(key)
    logger.info("Deleted Instagram token for user_id=%s", user_id)
