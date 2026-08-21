"""Regression tests for the explicitly enabled local authentication bypass."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.app.api.instagram_auth_routes import get_current_instagram_user


def _request_without_session_user() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "session": {}})


def test_dev_auth_bypass_returns_configured_local_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
    monkeypatch.setenv("DEV_AUTH_BYPASS_ACCOUNT_ID", "local-tester")

    user = get_current_instagram_user(_request_without_session_user())

    assert user.id == "local-tester"
    assert user.username == "local-dev"


def test_dev_auth_bypass_is_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")

    with pytest.raises(HTTPException) as exc_info:
        get_current_instagram_user(_request_without_session_user())

    assert exc_info.value.status_code == 401
