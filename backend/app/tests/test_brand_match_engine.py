"""Unit tests for brand-creator match scoring engine."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.api.brand_match_routes import router as brand_match_router
from backend.app.domain.brand_models import BrandProfile


def _brand(**kwargs: float | int | str) -> BrandProfile:
    return BrandProfile(brand_name="TestBrand", niche="fitness", **kwargs)


def test_exact_niche_match_scores_20() -> None:
    result = score_creator_against_brand("c1", _brand(), creator_dominant_category="fitness")
    assert result.niche_fit == 20.0


def test_no_niche_match_scores_3() -> None:
    result = score_creator_against_brand("c1", _brand(), creator_dominant_category="cooking")
    assert result.niche_fit == 3.0


def test_unknown_niche_scores_neutral() -> None:
    result = score_creator_against_brand("c1", _brand(), creator_dominant_category=None)
    assert result.niche_fit == 8.0


def test_adult_content_disqualifies() -> None:
    result = score_creator_against_brand(
        "c1",
        _brand(),
        creator_dominant_category="fitness",
        adult_content_detected=True,
    )
    assert result.disqualified is True
    assert result.total_match_score == 0.0
    assert result.match_band == "POOR"


def test_low_brand_safety_disqualifies() -> None:
    result = score_creator_against_brand(
        "c1",
        _brand(required_brand_safety_min=80.0),
        brand_safety_score_total_0_50=30.0,
    )
    assert result.disqualified is True


def test_top_creator_scores_excellent() -> None:
    result = score_creator_against_brand(
        "c1",
        _brand(min_followers=10000, max_followers=500000),
        creator_dominant_category="fitness",
        follower_count=85000,
        ahs_score=85.0,
        predicted_engagement_rate=0.06,
        visual_quality_score_total=45.0,
        brand_safety_score_total_0_50=48.0,
    )
    assert result.total_match_score >= 80.0
    assert result.match_band == "EXCELLENT"
    assert not result.disqualified


def test_ranking_order_in_route() -> None:
    """Verify that higher-scoring creators appear first."""
    app = FastAPI()
    app.include_router(brand_match_router)
    client = TestClient(app)
    response = client.post(
        "/api/brand-match",
        json={
            "brand": {"brand_name": "FitCo", "niche": "fitness"},
            "creators": [
                {
                    "account_id": "low",
                    "creator_dominant_category": "cooking",
                    "ahs_score": 20.0,
                    "avg_brand_safety_score": 25.0,
                },
                {
                    "account_id": "high",
                    "creator_dominant_category": "fitness",
                    "ahs_score": 90.0,
                    "avg_brand_safety_score": 48.0,
                    "predicted_engagement_rate": 0.05,
                },
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    scores = [match["total_match_score"] for match in payload["matches"] if not match["disqualified"]]
    assert scores == sorted(scores, reverse=True), "Matches must be ranked highest first."
    assert payload["matches"][0]["account_id"] == "high"
