"""Integration tests for AI Campaign Builder and Matchmaking."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.main import app

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

@pytest.fixture
def valid_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("BRAND_API_KEY", "test_key")
    return "test_key"

def test_integration_ai_campaign_discover(client: TestClient, valid_api_key: str):
    """
    Tests the full AI Campaign Builder flow:
    Route -> Parse Prompt -> Build Profile -> Query Pool -> Score Matches
    """
    # LLM Mock to return standard format
    toon_response = "brand_name: FitCo\nniche: fitness\nmin_followers: 50000"
    
    # Mock Creators representing what the DB would return
    mock_creators = [
        {
            "account_id": "perfect_fit",
            "creator_dominant_category": "fitness",
            "follower_count": 100000,
            "ahs_score": 90.0,
            "avg_brand_safety_score": 48.0,
            "predicted_engagement_rate": 0.05,
            "avg_visual_quality_score": 45.0,
            "adult_content_detected": False,
        },
        {
            "account_id": "wrong_niche",
            "creator_dominant_category": "cooking",
            "follower_count": 100000,
            "ahs_score": 90.0,
            "avg_brand_safety_score": 48.0,
            "predicted_engagement_rate": 0.05,
            "avg_visual_quality_score": 45.0,
            "adult_content_detected": False,
        }
    ]

    with patch("backend.app.ai.llm_client.LLMClient.generate", return_value=toon_response), \
         patch("backend.app.ai.llm_client.LLMClient.embed", return_value=[0.1]*1536), \
         patch("backend.app.api.campaign_routes.query_creator_pool", return_value=mock_creators):
        
        response = client.post(
            "/api/brand/campaign/discover",
            headers={"X-API-Key": valid_api_key},
            json={
                "prompt": "I need fitness creators with over 50k followers",
                "brand_name": "FitCo"
            }
        )

        assert response.status_code == 200
        data = response.json()
        
        # Verify the prompt was successfully parsed using the real prompt service
        assert data["parsed_brief"]["niche"] == "fitness"
        assert data["parsed_brief"]["min_followers"] == 50000
        
        # Verify both creators were evaluated using the real match engine
        assert data["total_evaluated"] == 2
        
        # 'perfect_fit' should score much higher than 'wrong_niche'
        assert data["matches"][0]["account_id"] == "perfect_fit"
        assert data["matches"][1]["account_id"] == "wrong_niche"
        assert data["matches"][0]["total_match_score"] > data["matches"][1]["total_match_score"]

def test_integration_manual_campaign_match(client: TestClient, valid_api_key: str):
    """
    Tests the full Manual Matchmaking flow:
    Route -> Score Matches against explicit Brand Profile
    """
    mock_creators = [
        {
            "account_id": "good_fit",
            "creator_dominant_category": "tech",
            "follower_count": 200000,
            "ahs_score": 85.0,
            "avg_brand_safety_score": 45.0,
            "predicted_engagement_rate": 0.04,
            "avg_visual_quality_score": 40.0,
            "adult_content_detected": False,
        },
        {
            "account_id": "disqualified_fit",
            "creator_dominant_category": "tech",
            "follower_count": 200000,
            "ahs_score": 85.0,
            "avg_brand_safety_score": 15.0, # Very low safety score (15 out of 50 -> 30 out of 100), should trigger disqualification
            "predicted_engagement_rate": 0.04,
            "avg_visual_quality_score": 40.0,
            "adult_content_detected": False,
        }
    ]

    with patch("backend.app.api.campaign_routes.query_creator_pool", return_value=mock_creators):
        response = client.post(
            "/api/brand/campaign/match",
            headers={"X-API-Key": valid_api_key},
            json={
                "brand_profile": {
                    "brand_name": "Tech Corp",
                    "niche": "tech",
                    "min_followers": 100000,
                    "max_followers": 500000,
                    "min_engagement_rate": 0.02,
                    "required_brand_safety_min": 40.0, # Required 40, creator has 20
                    "content_quality_min": 30.0
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_evaluated"] == 2
        assert data["disqualified_count"] == 1
        
        # Verify the real match engine ranked the good fit first and disqualified the second
        assert data["matches"][0]["account_id"] == "good_fit"
        assert data["matches"][0]["disqualified"] is False
        
        assert data["matches"][1]["account_id"] == "disqualified_fit"
        assert data["matches"][1]["disqualified"] is True
        assert len(data["matches"][1]["disqualify_reasons"]) > 0
