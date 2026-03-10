"""Integration tests for S4/S6 pipeline wiring and weighted score usage."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.services import ai_analysis_service
from backend.app.services.post_insights_service import build_single_post_insights


def _build_post(media_id: str, category: str | None = "fitness") -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_s4s6",
        media_id=media_id,
        media_url="https://example.com/post.jpg",
        media_type="IMAGE",
        caption_text="How to build strength safely? Save this and follow for more #fitness #training",
        post_category=category,
        creator_dominant_category="sports",
        extracted_brand_mentions=[],
        safety_extra_flags={},
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(
            reach=1800,
            impressions=2100,
            likes=95,
            comments=18,
            saves=22,
            shares=11,
            profile_visits=8,
            website_taps=2,
        ),
        derived_metrics=DerivedMetrics(engagement_rate=0.0811),
        benchmark_metrics=BenchmarkMetrics(),
    )


def test_pipeline_result_and_cache_include_s4_s6_and_weighted_uses_them(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    captured_prompts: list[dict[str, str]] = []

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {
            "provider": "gemini",
            "status": "ok",
            "signals": [
                {
                    "objects": ["person", "dumbbell"],
                    "primary_objects": ["person", "dumbbell"],
                    "dominant_focus": "person",
                    "scene_description": "Fitness coach demo",
                    "detected_text": "3 safe strength tips",
                    "hook_strength_score": 0.82,
                }
            ],
        }

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        captured_prompts.append(prompt)
        return json.dumps(
            {
                "summary": "Clear value post with strong educational framing and healthy engagement signals.",
                "drivers": [
                    {
                        "id": "d1",
                        "label": "Strong value framing",
                        "type": "POSITIVE",
                        "explanation": "Caption and visual reinforce practical utility.",
                    }
                ],
                "recommendations": [
                    {
                        "id": "r1",
                        "text": "Repeat this problem-solution format next week.",
                        "impact_level": "MEDIUM",
                    }
                ],
                "engagement_potential_score": {
                    "emotional_resonance": 6.5,
                    "shareability": 7.0,
                    "save_worthiness": 8.0,
                    "comment_potential": 6.0,
                    "novelty_or_value": 7.5,
                    "total": 35.0,
                },
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    target_post = _build_post("m_s4s6_target")
    history = [
        _build_post("m_s4s6_h1"),
        _build_post("m_s4s6_h2"),
        _build_post("m_s4s6_h3"),
    ]

    response = asyncio.run(build_single_post_insights(target_post=target_post, historical_posts=history, run_ai=True))

    assert response["ai_analysis"] is not None
    assert "audience_relevance_score" in response["ai_analysis"]
    assert "brand_safety_score" in response["ai_analysis"]
    assert response["post"].audience_relevance_score.s4_raw_0_100 in {15, 50, 75, 100}
    assert 0 <= response["post"].brand_safety_score.s6_raw_0_100 <= 100
    assert "S4" in response["post"].weighted_post_score.weights_used
    assert "S6" in response["post"].weighted_post_score.weights_used

    assert captured_prompts
    prompt_payload = json.loads(captured_prompts[0]["user"])
    assert "s4_audience_relevance" in prompt_payload["context"]
    assert "s6_brand_safety" in prompt_payload["context"]

    cache_key = ai_analysis_service._cache_key(target_post)
    assert cache_key in ai_analysis_service._ANALYSIS_CACHE
    cache_payload = ai_analysis_service._ANALYSIS_CACHE[cache_key].result
    assert "audience_relevance_score" in cache_payload
    assert "brand_safety_score" in cache_payload
