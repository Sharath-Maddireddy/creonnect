"""Tests for predicted engagement rate engine and pipeline wiring."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from backend.app.analytics.predicted_er_engine import compute_predicted_engagement_rate
from backend.app.analytics.derived_metrics import compute_derived_metrics
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.services import ai_analysis_service
from backend.app.services.post_insights_service import build_single_post_insights


def _build_post(media_id: str, reach: int = 2000, likes: int = 120, comments: int = 20) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_pred",
        media_id=media_id,
        media_url="https://example.com/post.jpg",
        media_type="IMAGE",
        caption_text="Practical content with clear value.",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(
            reach=reach,
            impressions=reach + 200,
            likes=likes,
            comments=comments,
            saves=15,
            shares=10,
            profile_visits=8,
            website_taps=2,
        ),
        derived_metrics=DerivedMetrics(engagement_rate=(likes + comments + 15 + 10) / reach),
        benchmark_metrics=BenchmarkMetrics(),
    )


def test_predicted_er_happy_path() -> None:
    predicted, notes = compute_predicted_engagement_rate(tier_avg_er=0.08, s5_total=25.0)
    assert predicted == 0.04
    assert notes == []


def test_missing_inputs() -> None:
    predicted_missing_tier, notes_missing_tier = compute_predicted_engagement_rate(tier_avg_er=None, s5_total=25.0)
    assert predicted_missing_tier is None
    assert "missing tier_avg_er" in notes_missing_tier

    predicted_missing_s5, notes_missing_s5 = compute_predicted_engagement_rate(tier_avg_er=0.08, s5_total=None)
    assert predicted_missing_s5 is None
    assert "missing s5_total" in notes_missing_s5


def test_clamp_s5_total() -> None:
    predicted_high, _ = compute_predicted_engagement_rate(tier_avg_er=0.08, s5_total=80.0)
    predicted_low, _ = compute_predicted_engagement_rate(tier_avg_er=0.08, s5_total=-10.0)
    assert predicted_high == 0.08
    assert predicted_low == 0.0


def test_unit_consistency() -> None:
    core = CoreMetrics(reach=1000, likes=30, comments=10, saves=5, shares=5)
    derived = compute_derived_metrics(core)
    assert derived.engagement_rate is not None
    assert 0.0 <= derived.engagement_rate <= 1.0  # Engagement rate is fraction in this codebase.

    predicted, _ = compute_predicted_engagement_rate(tier_avg_er=derived.engagement_rate, s5_total=25.0)
    assert predicted is not None
    assert 0.0 <= predicted <= 1.0


def test_predicted_er_integration_result_and_cache(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {
            "provider": "gemini",
            "status": "ok",
            "signals": [
                {
                    "objects": ["person", "product"],
                    "primary_objects": ["person", "product"],
                    "dominant_focus": "person",
                    "scene_description": "Person presenting product",
                    "detected_text": "3 growth tips",
                    "hook_strength_score": 0.8,
                }
            ],
        }

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        return json.dumps(
            {
                "summary": "Strong post with clear message and useful value.",
                "drivers": [
                    {
                        "id": "d1",
                        "label": "Clear value",
                        "type": "POSITIVE",
                        "explanation": "Visual and caption reinforce each other.",
                    }
                ],
                "recommendations": [
                    {
                        "id": "r1",
                        "text": "Repeat this structure in the next post.",
                        "impact_level": "MEDIUM",
                    }
                ],
                "engagement_potential_score": {
                    "emotional_resonance": 6.0,
                    "shareability": 7.0,
                    "save_worthiness": 8.0,
                    "comment_potential": 6.0,
                    "novelty_or_value": 8.0,
                    "total": 35.0,
                },
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    target_post = _build_post("m_pred_target")
    history = [
        _build_post("m_pred_h1", reach=1800, likes=90, comments=18),
        _build_post("m_pred_h2", reach=1900, likes=100, comments=19),
        _build_post("m_pred_h3", reach=2100, likes=115, comments=22),
    ]

    response = asyncio.run(build_single_post_insights(target_post=target_post, historical_posts=history, run_ai=True))

    assert response["ai_analysis"] is not None
    assert "tier_avg_engagement_rate" in response["ai_analysis"]
    assert "predicted_engagement_rate" in response["ai_analysis"]
    assert "predicted_engagement_rate_notes" in response["ai_analysis"]
    assert response["post"].predicted_engagement_rate == response["ai_analysis"]["predicted_engagement_rate"]
    assert response["post"].tier_avg_engagement_rate == response["ai_analysis"]["tier_avg_engagement_rate"]

    cache_key = ai_analysis_service._cache_key(target_post)
    assert cache_key in ai_analysis_service._ANALYSIS_CACHE
    assert "predicted_engagement_rate" in ai_analysis_service._ANALYSIS_CACHE[cache_key].result
