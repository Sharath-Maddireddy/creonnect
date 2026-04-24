"""Tests for encrypted Instagram token storage."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.app.infra import token_store


def test_save_token_encrypts_payload_before_storage(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("CREONNECT_TOKEN_ENCRYPTION_KEY", raising=False)
    token_store._TOKEN_FERNET = None
    token_store._TOKEN_KEY_WARNING_EMITTED = False

    def _fake_set_json(key: str, payload: dict[str, Any], ttl_seconds: int | None = None) -> None:
        captured["key"] = key
        captured["payload"] = payload
        captured["ttl"] = ttl_seconds

    monkeypatch.setattr(token_store, "set_json", _fake_set_json)

    token_store.save_token("user-123", {"access_token": "secret", "username": "creator"})

    assert captured["key"] == "instagram:token:user-123"
    assert captured["ttl"] == token_store.TOKEN_TTL_SECONDS
    assert "ciphertext" in captured["payload"]
    assert captured["payload"]["ciphertext"] != "secret"


def test_get_token_decrypts_ciphertext_payload(monkeypatch) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("CREONNECT_TOKEN_ENCRYPTION_KEY", raising=False)
    token_store._TOKEN_FERNET = None
    token_store._TOKEN_KEY_WARNING_EMITTED = False

    encrypted_payload = token_store._encrypt_token_payload({"access_token": "secret", "username": "creator"})
    monkeypatch.setattr(token_store, "get_json", lambda key: encrypted_payload)

    assert token_store.get_token("user-123") == {"access_token": "secret", "username": "creator"}


def test_get_token_keeps_legacy_plaintext_payloads_readable(monkeypatch) -> None:
    monkeypatch.setattr(token_store, "get_json", lambda key: {"access_token": "legacy", "username": "creator"})
    assert token_store.get_token("user-123") == {"access_token": "legacy", "username": "creator"}


def test_save_token_async_encrypts_payload_before_storage(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("CREONNECT_TOKEN_ENCRYPTION_KEY", raising=False)
    token_store._TOKEN_FERNET = None
    token_store._TOKEN_KEY_WARNING_EMITTED = False

    async def _fake_aset_json(key: str, payload: dict[str, Any], ttl_seconds: int | None = None) -> None:
        captured["key"] = key
        captured["payload"] = payload
        captured["ttl"] = ttl_seconds

    monkeypatch.setattr(token_store, "aset_json", _fake_aset_json)

    asyncio.run(token_store.save_token_async("user-123", {"access_token": "secret"}))

    assert captured["key"] == "instagram:token:user-123"
    assert captured["ttl"] == token_store.TOKEN_TTL_SECONDS
    assert "ciphertext" in captured["payload"]


def test_get_token_async_decrypts_ciphertext_payload(monkeypatch) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("CREONNECT_TOKEN_ENCRYPTION_KEY", raising=False)
    token_store._TOKEN_FERNET = None
    token_store._TOKEN_KEY_WARNING_EMITTED = False

    encrypted_payload = token_store._encrypt_token_payload({"access_token": "secret"})

    async def _fake_aget_json(key: str) -> dict[str, Any]:
        return encrypted_payload

    monkeypatch.setattr(token_store, "aget_json", _fake_aget_json)

    assert asyncio.run(token_store.get_token_async("user-123")) == {"access_token": "secret"}
