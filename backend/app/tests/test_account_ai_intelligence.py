"""Tests for account-level creator AI intelligence generation."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from backend.app.domain.account_models import CreatorIntelligence
from backend.app.domain.post_models import (
    AudienceRelevanceScore,
    BrandSafetyScore,
    SinglePostInsights,
    VisionAnalysis,
    VisionSignal,
    WeightedPostScore,
)
from backend.app.services.account_ai_intelligence import generate_creator_intelligence


def _build_mock_post(weighted_score: float, production_level: str) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="test_acct",
        media_id=f"test_media_{weighted_score}",
        media_url="https://example.com/media.jpg",
        media_type="REEL",
        caption_text="Test caption",
        audience_relevance_score=AudienceRelevanceScore(post_category="fitness"),
        brand_safety_score=BrandSafetyScore(s6_raw_0_100=95),
        vision_analysis=VisionAnalysis(
            signals=[VisionSignal(production_level=production_level)]
        ),
        weighted_post_score=WeightedPostScore(score=weighted_score),
    )


def test_generate_creator_intelligence_success() -> None:
    posts = [
        _build_mock_post(90.0, "high"),
        _build_mock_post(80.0, "medium"),
    ]

    mock_llm_response = '''
    ```json
    {
      "creator_persona": "Fitness enthusiast focused on holistic health.",
      "content_style_summary": "High-energy workouts with clear instructions.",
      "top_performing_themes": ["HIIT", "Nutrition tips"],
      "brand_fit": {
        "fit_categories": ["Activewear", "Supplements"],
        "red_flags": []
      }
    }
    ```
    '''

    with patch("backend.app.services.account_ai_intelligence.LLMClient.generate", return_value=mock_llm_response):
        result = asyncio.run(
            generate_creator_intelligence(
                posts=posts,
                account_id="test_acct",
                username="fit_guru",
                niche_tags=["fitness", "health"],
                creator_dominant_category="Sports",
            )
        )

    assert isinstance(result, CreatorIntelligence)
    assert result.creator_persona == "Fitness enthusiast focused on holistic health."
    assert "Activewear" in result.brand_fit.fit_categories
    assert "HIIT" in result.top_performing_themes


def test_generate_creator_intelligence_timeout_fallback() -> None:
    posts = [_build_mock_post(85.0, "high")]

    async def _mock_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch("backend.app.services.account_ai_intelligence.asyncio.wait_for", side_effect=_mock_timeout):
        result = asyncio.run(
            generate_creator_intelligence(
                posts=posts, account_id="test_acct"
            )
        )

    assert isinstance(result, CreatorIntelligence)
    assert result.creator_persona is None


def test_generate_creator_intelligence_bad_json() -> None:
    posts = [_build_mock_post(85.0, "high")]

    with patch("backend.app.services.account_ai_intelligence.LLMClient.generate", return_value="Invalid JSON response"):
        result = asyncio.run(
            generate_creator_intelligence(
                posts=posts, account_id="test_acct"
            )
        )

    assert isinstance(result, CreatorIntelligence)
    assert result.creator_persona is None
