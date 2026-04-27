from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app.domain.post_models import (
    BenchmarkMetrics,
    BrandSafetyScore,
    CoreMetrics,
    DerivedMetrics,
    SinglePostInsights,
    VisionAnalysis,
    VisionSignal,
    VisualQualityScore,
    WeightedPostScore,
)
from backend.main import app


def test_brand_post_analysis_route(monkeypatch) -> None:
    monkeypatch.setenv("BRAND_API_KEY", "test-key")

    async def _fake_run_post_insights(_payload: dict) -> SinglePostInsights:
        return SinglePostInsights(
            account_id="acct_123",
            media_id="post_123",
            media_url="https://example.com/post.jpg",
            media_type="IMAGE",
            caption_text="Test caption",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            core_metrics=CoreMetrics(likes=120, comments=15, impressions=5000, reach=4500),
            derived_metrics=DerivedMetrics(engagement_rate=0.06),
            benchmark_metrics=BenchmarkMetrics(),
            visual_quality_score=VisualQualityScore(total=42.0),
            brand_safety_score=BrandSafetyScore(total_0_50=46.0, s6_raw_0_100=92),
            weighted_post_score=WeightedPostScore(score=78.0, normalized_score_0_50=39.0),
            predicted_engagement_rate=0.047,
            vision_analysis=VisionAnalysis(
                provider="gemini",
                status="ok",
                signals=[VisionSignal(adult_content_detected=False)],
            ),
        )

    monkeypatch.setattr(
        "backend.app.api.brand_post_analysis_routes._run_post_insights",
        _fake_run_post_insights,
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/brand/post-analysis",
        headers={"X-API-Key": "test-key"},
        json={
            "brand_profile": {
                "brand_name": "FitCo",
                "niche": "fitness",
                "min_followers": 10000,
                "max_followers": 200000,
                "min_engagement_rate": 0.02,
                "required_brand_safety_min": 70.0,
                "content_quality_min": 50.0,
            },
            "post": {
                "post_id": "post_123",
                "account_id": "acct_123",
                "platform": "instagram",
                "post_type": "IMAGE",
                "media_url": "https://example.com/post.jpg",
                "caption_text": "Test caption",
                "likes": 120,
                "comments": 15,
                "views": 5000,
                "posted_at": "2024-01-01T00:00:00+00:00",
            },
            "account_id": "acct_123",
            "creator_dominant_category": "fitness",
            "follower_count": 75000,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "post_analysis" in payload
    assert "brand_fit" in payload
    assert isinstance(payload["brand_fit"]["total_match_score"], float)
    assert 0.0 <= payload["brand_fit"]["total_match_score"] <= 100.0
    assert payload["brand_fit"]["match_band"] in {"EXCELLENT", "GOOD", "MODERATE", "POOR"}
