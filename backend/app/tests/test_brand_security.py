from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend import main
from backend.app.api import campaign_routes
from backend.app.api.auth import verify_api_key
from backend.app.api.rate_limiter import InMemoryRateLimiter


def test_verify_api_key_accepts_matching_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAND_API_KEY", "brand-secret")

    assert verify_api_key("brand-secret") == "brand-secret"


def test_verify_api_key_rejects_missing_or_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAND_API_KEY", "brand-secret")

    with pytest.raises(HTTPException, match="Invalid or missing API key."):
        verify_api_key(None)

    with pytest.raises(HTTPException, match="Invalid or missing API key."):
        verify_api_key("wrong-secret")


def test_brand_api_key_configuration_succeeds_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("BRAND_API_KEY", "brand-secret")

    assert main._validate_brand_api_key_configuration() is True


def test_campaign_route_rate_limiter_blocks_repeated_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(campaign_routes, "rate_limiter", InMemoryRateLimiter(max_requests=1, window_seconds=3600))

    assert campaign_routes._rate_limit_by_api_key(api_key="brand-secret") == "brand-secret"

    with pytest.raises(HTTPException, match="Rate limit exceeded"):
        campaign_routes._rate_limit_by_api_key(api_key="brand-secret")
