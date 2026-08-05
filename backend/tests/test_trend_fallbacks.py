from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.analytics import niche_discovery_engine, trend_recommendation_engine
from backend.app.domain.account_models import CreatorIntelligence
from backend.app.domain.post_models import CoreMetrics, SinglePostInsights
from backend.app.domain.trend_models import CreatorNiche, GlobalTrend
from backend.app.services import creator_trend_service


def _post(caption: str, media_type: str = "REEL") -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_trends",
        media_id=f"post_{abs(hash(caption))}",
        media_type=media_type,
        caption_text=caption,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(likes=100, comments=12, impressions=2000),
    )


@pytest.mark.asyncio
async def test_niche_discovery_falls_back_to_keyword_classification(monkeypatch) -> None:
    def _raise_generate(*_args, **_kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(niche_discovery_engine.LLMClient, "generate", _raise_generate)

    niche = await niche_discovery_engine.discover_creator_niche(
        posts=[
            _post("Save this HIIT workout for abs and strength training."),
            _post("Protein tips for muscle growth after gym sessions."),
        ],
        bio="Fitness coach sharing workouts and fatloss tips",
        username="bajpayee_fitnessjourney",
    )

    assert niche.primary_category == "Fitness"
    assert niche.confidence_score > 0.1
    assert "fitness" in {item.lower() for item in niche.sub_niches}


@pytest.mark.asyncio
async def test_recommendations_fall_back_when_llm_fails(monkeypatch) -> None:
    def _raise_generate(*_args, **_kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(trend_recommendation_engine.LLMClient, "generate", _raise_generate)

    trends = [
        GlobalTrend(
            topic_name="Workout form checks",
            trend_type="format",
            momentum="rising",
            description="Creators break down common exercise form mistakes.",
        ),
        GlobalTrend(
            topic_name="Protein snack prep",
            trend_type="topic",
            momentum="rising",
            description="Short recipes for easy high-protein snacks.",
        ),
    ]

    recommendations, _content_gaps, _daily_insights, _opportunity_bullets = await trend_recommendation_engine.generate_trend_recommendations(
        CreatorIntelligence(
            content_style_summary="Direct-to-camera fitness reels.",
            creator_strengths=["Clear coaching hooks"],
        ),
        trends,
    )

    assert len(recommendations) == 2
    assert recommendations[0].trend_reference == "Workout form checks"
    assert recommendations[0].suggested_title


def test_creator_trend_service_enriches_empty_creator_intelligence() -> None:
    niche = CreatorNiche(primary_category="Fitness", sub_niches=["workout", "protein"], confidence_score=0.75)
    enriched = creator_trend_service._derive_creator_intelligence(
        CreatorIntelligence(),
        [_post("Workout routine for strength"), _post("Protein meal prep ideas")],
        niche,
    )

    assert enriched.content_style_summary
    assert enriched.creator_strengths
    assert enriched.top_performing_themes
