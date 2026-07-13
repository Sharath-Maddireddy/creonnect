from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api.campaign_routes import rate_limiter
from backend.app.services.creator_pool_service import LookalikeEmbeddingError
from backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_campaign_rate_limiter() -> None:
    rate_limiter.reset()


@pytest.fixture
def valid_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("BRAND_API_KEY", "test_key")
    return "test_key"


def test_manual_campaign_match(client: TestClient, valid_api_key: str) -> None:
    mock_creators = [
        {
            "account_id": "creator1_id",
            "username": "creator1",
            "creator_dominant_category": "fitness",
            "follower_count": 150000,
            "avg_views": 10000,
            "avg_likes": 1000,
            "avg_comments": 100,
            "ahs_score": 85.0,
            "predicted_engagement_rate": 0.05,
            "avg_visual_quality_score": 40.0,
            "avg_brand_safety_score": 45.0,
            "adult_content_detected": False,
        }
    ]

    with patch("backend.app.api.campaign_routes.query_creator_pool", return_value=mock_creators):
        response = client.post(
            "/api/brand/campaign/match",
            headers={"X-API-Key": valid_api_key},
            json={
                "brand_profile": {
                    "brand_name": "Test Brand",
                    "niche": "fitness",
                    "min_followers": 100000,
                    "max_followers": 500000,
                    "min_engagement_rate": 0.02,
                    "required_brand_safety_min": 50.0,
                    "content_quality_min": 30.0,
                }
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_evaluated"] == 1
        assert len(data["matches"]) == 1
        assert data["matches"][0]["account_id"] == "creator1_id"
        assert data["matches"][0]["disqualified"] is False


def test_ai_campaign_discover(client: TestClient, valid_api_key: str) -> None:
    mock_creators = [
        {
            "account_id": "creator2_id",
            "username": "creator2",
            "creator_dominant_category": "fashion",
            "follower_count": 250000,
            "avg_views": 20000,
            "avg_likes": 2000,
            "avg_comments": 200,
            "ahs_score": 90.0,
            "predicted_engagement_rate": 0.08,
            "avg_visual_quality_score": 45.0,
            "avg_brand_safety_score": 48.0,
            "adult_content_detected": False,
        }
    ]

    parsed_brief = {
        "brand_name": "Fashion Brand",
        "niche": "fashion",
        "min_followers": 200000,
        "max_followers": None,
        "min_engagement_rate": None,
        "campaign_goal": "promotions",
        "content_type_preference": "reels",
        "additional_requirements": [],
    }

    with (
        patch("backend.app.api.campaign_routes.parse_campaign_prompt", return_value=parsed_brief),
        patch("backend.app.api.campaign_routes.build_ai_campaign_summary", return_value="AI summary"),
        patch("backend.app.api.campaign_routes.LLMClient") as mock_llm_client_cls,
        patch("backend.app.api.campaign_routes.query_creator_pool", return_value=mock_creators),
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.embed.return_value = [0.1] * 1536
        mock_llm_client_cls.return_value = mock_llm_instance

        response = client.post(
            "/api/brand/campaign/discover",
            headers={"X-API-Key": valid_api_key},
            json={
                "prompt": "Find fashion creators with over 200k followers.",
                "brand_name": "Fashion Brand",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["parsed_brief"]["niche"] == "fashion"
        assert data["total_evaluated"] == 1
        assert len(data["matches"]) == 1
        assert data["matches"][0]["account_id"] == "creator2_id"
        assert data["ai_explanation"] == "AI summary"


def test_get_creator_lookalikes(client: TestClient, valid_api_key: str) -> None:
    mock_lookalikes = [
        {"account_id": "lookalike1_id", "username": "lookalike1"},
        {"account_id": "lookalike2_id", "username": "lookalike2"},
    ]

    with patch("backend.app.api.campaign_routes.find_lookalikes", return_value=mock_lookalikes):
        response = client.get(
            "/api/brand/campaign/lookalikes/target_id",
            headers={"X-API-Key": valid_api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == "target_id"
        assert len(data["lookalikes"]) == 2
        assert data["lookalikes"][0]["account_id"] == "lookalike1_id"


def test_get_creator_lookalikes_not_found(client: TestClient, valid_api_key: str) -> None:
    with patch("backend.app.api.campaign_routes.find_lookalikes", return_value=None):
        response = client.get(
            "/api/brand/campaign/lookalikes/nonexistent_id",
            headers={"X-API-Key": valid_api_key},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Creator not found."


def test_get_creator_lookalikes_returns_503_when_embedding_missing(client: TestClient, valid_api_key: str) -> None:
    with patch(
        "backend.app.api.campaign_routes.find_lookalikes",
        side_effect=LookalikeEmbeddingError("missing embedding"),
    ):
        response = client.get(
            "/api/brand/campaign/lookalikes/target_id",
            headers={"X-API-Key": valid_api_key},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Lookalike search is temporarily unavailable."


def test_get_creator_lookalikes_rejects_invalid_account_id(client: TestClient, valid_api_key: str) -> None:
    response = client.get(
        "/api/brand/campaign/lookalikes/bad-id!",
        headers={"X-API-Key": valid_api_key},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid account_id format."


def test_campaign_rate_limiter_returns_429_after_limit(client: TestClient, valid_api_key: str) -> None:
    payload = {
        "brand_profile": {
            "brand_name": "Test Brand",
            "niche": "fitness",
            "min_followers": None,
            "max_followers": None,
            "min_engagement_rate": None,
            "required_brand_safety_min": 50.0,
            "content_quality_min": 30.0,
        }
    }

    with patch("backend.app.api.campaign_routes.query_creator_pool", return_value=[]):
        for _ in range(10):
            ok_response = client.post(
                "/api/brand/campaign/match",
                headers={"X-API-Key": valid_api_key},
                json=payload,
            )
            assert ok_response.status_code == 200

        limited_response = client.post(
            "/api/brand/campaign/match",
            headers={"X-API-Key": valid_api_key},
            json=payload,
        )

    assert limited_response.status_code == 429
    assert limited_response.json()["detail"] == "Rate limit exceeded. Try again later."

