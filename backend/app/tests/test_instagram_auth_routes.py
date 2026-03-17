"""Regression tests for Instagram auth routes."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from backend.app.api.instagram_auth_routes import router as instagram_auth_router


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-session-secret", same_site="lax")
    app.include_router(instagram_auth_router)
    return TestClient(app)


def _start_oauth_session(client: TestClient) -> str:
    login_response = client.get("/api/auth/instagram/login")
    assert login_response.status_code == 200
    oauth_url = login_response.json()["oauth_url"]
    state_values = parse_qs(urlparse(oauth_url).query).get("state")
    assert state_values
    return state_values[0]


def _mock_oauth_url_builder(monkeypatch) -> None:
    def fake_get_oauth_url(state: str) -> str:
        return f"https://example.test/oauth?state={state}"

    monkeypatch.setattr("backend.app.api.instagram_auth_routes.get_oauth_url", fake_get_oauth_url)


def test_instagram_logout_requires_authenticated_session(monkeypatch) -> None:
    deleted_user_ids: list[str] = []

    def fake_delete_token(user_id: str) -> None:
        deleted_user_ids.append(user_id)

    monkeypatch.setattr("backend.app.api.instagram_auth_routes.delete_token", fake_delete_token)

    client = _build_test_client()
    response = client.post("/api/auth/logout?user_id=attacker-target")

    assert response.status_code == 401
    assert deleted_user_ids == []


def test_instagram_logout_uses_session_user_instead_of_request_parameter(monkeypatch) -> None:
    deleted_user_ids: list[str] = []
    _mock_oauth_url_builder(monkeypatch)

    async def fake_exchange_code_for_token(code: str) -> dict[str, str]:
        assert code == "oauth-code"
        return {"access_token": "short-token"}

    async def fake_exchange_short_for_long_lived_token(token: str) -> dict[str, str | int]:
        assert token == "short-token"
        return {"access_token": "long-token", "expires_in": 3600}

    async def fake_fetch_instagram_profile(access_token: str) -> dict[str, str]:
        assert access_token == "long-token"
        return {"id": "session-user", "username": "creator"}

    def fake_save_token(user_id: str, token_data: dict[str, object]) -> None:
        assert user_id == "session-user"
        assert token_data["access_token"] == "long-token"

    def fake_delete_token(user_id: str) -> None:
        deleted_user_ids.append(user_id)

    monkeypatch.setattr("backend.app.api.instagram_auth_routes.exchange_code_for_token", fake_exchange_code_for_token)
    monkeypatch.setattr(
        "backend.app.api.instagram_auth_routes.exchange_short_for_long_lived_token",
        fake_exchange_short_for_long_lived_token,
    )
    monkeypatch.setattr("backend.app.api.instagram_auth_routes.fetch_instagram_profile", fake_fetch_instagram_profile)
    monkeypatch.setattr("backend.app.api.instagram_auth_routes.save_token", fake_save_token)
    monkeypatch.setattr("backend.app.api.instagram_auth_routes.delete_token", fake_delete_token)

    client = _build_test_client()
    state = _start_oauth_session(client)

    callback_response = client.get(f"/api/auth/instagram/callback?code=oauth-code&state={state}")
    assert callback_response.status_code == 200

    logout_response = client.post("/api/auth/logout?user_id=attacker-target")

    assert logout_response.status_code == 200
    assert logout_response.json() == {"status": "logged_out"}
    assert deleted_user_ids == ["session-user"]


def test_instagram_me_uses_session_user_instead_of_request_parameter(monkeypatch) -> None:
    token_lookups: list[str] = []
    _mock_oauth_url_builder(monkeypatch)

    async def fake_exchange_code_for_token(code: str) -> dict[str, str]:
        assert code == "oauth-code"
        return {"access_token": "short-token"}

    async def fake_exchange_short_for_long_lived_token(token: str) -> dict[str, str | int]:
        assert token == "short-token"
        return {"access_token": "long-token", "expires_in": 3600}

    async def fake_fetch_instagram_profile(access_token: str) -> dict[str, str]:
        if access_token == "long-token":
            return {"id": "session-user", "username": "creator"}
        if access_token == "stored-access-token":
            return {"id": "session-user", "username": "creator"}
        raise AssertionError(f"Unexpected access token: {access_token}")

    def fake_save_token(user_id: str, token_data: dict[str, object]) -> None:
        assert user_id == "session-user"
        assert token_data["access_token"] == "long-token"

    def fake_get_token(user_id: str) -> dict[str, str] | None:
        token_lookups.append(user_id)
        if user_id == "session-user":
            return {"access_token": "stored-access-token"}
        return None

    monkeypatch.setattr("backend.app.api.instagram_auth_routes.exchange_code_for_token", fake_exchange_code_for_token)
    monkeypatch.setattr(
        "backend.app.api.instagram_auth_routes.exchange_short_for_long_lived_token",
        fake_exchange_short_for_long_lived_token,
    )
    monkeypatch.setattr("backend.app.api.instagram_auth_routes.fetch_instagram_profile", fake_fetch_instagram_profile)
    monkeypatch.setattr("backend.app.api.instagram_auth_routes.save_token", fake_save_token)
    monkeypatch.setattr("backend.app.api.instagram_auth_routes.get_token", fake_get_token)

    client = _build_test_client()
    state = _start_oauth_session(client)

    callback_response = client.get(f"/api/auth/instagram/callback?code=oauth-code&state={state}")
    assert callback_response.status_code == 200

    me_response = client.get("/api/auth/me?user_id=attacker-target")

    assert me_response.status_code == 200
    assert me_response.json() == {"id": "session-user", "username": "creator"}
    assert token_lookups == ["session-user"]


def test_instagram_callback_rejects_invalid_oauth_state(monkeypatch) -> None:
    _mock_oauth_url_builder(monkeypatch)

    async def fail_exchange_code_for_token(code: str) -> dict[str, str]:
        raise AssertionError(f"exchange_code_for_token should not be called for invalid state: {code}")

    monkeypatch.setattr("backend.app.api.instagram_auth_routes.exchange_code_for_token", fail_exchange_code_for_token)

    client = _build_test_client()
    _ = _start_oauth_session(client)

    callback_response = client.get("/api/auth/instagram/callback?code=oauth-code&state=forged-state")

    assert callback_response.status_code == 400
    assert callback_response.json() == {"detail": "Invalid state parameter"}
