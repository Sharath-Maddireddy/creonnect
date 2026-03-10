"""Anti-gravity and integration tests for S2 caption effectiveness."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from backend.app.analytics.caption_s2_engine import compute_s2_caption_effectiveness
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.services import ai_analysis_service
from backend.app.services.post_insights_service import build_single_post_insights


def _build_post(media_id: str, caption_text: str) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_s2",
        media_id=media_id,
        media_url="https://example.com/post.jpg",
        media_type="IMAGE",
        caption_text=caption_text,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(
            reach=2000,
            impressions=2200,
            likes=100,
            comments=20,
            saves=15,
            shares=10,
            profile_visits=8,
            website_taps=2,
        ),
        derived_metrics=DerivedMetrics(engagement_rate=0.0725),
        benchmark_metrics=BenchmarkMetrics(),
    )


def test_hashtag_first_line_only_keeps_total_bounded() -> None:
    caption = " ".join(f"#tag{i}" for i in range(30))
    score = compute_s2_caption_effectiveness(caption)
    assert score.hook_score_0_100 == 30
    assert score.total_0_50 <= 30.0


def test_cta_spam_without_real_hook_is_moderate() -> None:
    caption = ("comment " * 30).strip()
    score = compute_s2_caption_effectiveness(caption)
    assert score.hook_score_0_100 == 30
    assert score.total_0_50 < 40.0


def test_empty_caption_is_deterministic_low_band() -> None:
    first = compute_s2_caption_effectiveness("")
    second = compute_s2_caption_effectiveness("")
    assert first.model_dump(mode="python") == second.model_dump(mode="python")
    assert first.total_0_50 <= 20.0


def test_integration_result_and_cache_include_s2(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {
            "provider": "gemini",
            "status": "ok",
            "signals": [
                {
                    "objects": ["person", "whiteboard"],
                    "primary_objects": ["person", "whiteboard"],
                    "dominant_focus": "person",
                    "scene_description": "Presenter with whiteboard",
                    "detected_text": "Growth tips",
                    "hook_strength_score": 0.8,
                }
            ],
        }

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        return json.dumps(
            {
                "summary": "Strong post with clear value and practical takeaways.",
                "drivers": [
                    {
                        "id": "d1",
                        "label": "Clear teaching angle",
                        "type": "POSITIVE",
                        "explanation": "Caption and visual both support an instructional message.",
                    }
                ],
                "recommendations": [
                    {
                        "id": "r1",
                        "text": "Reuse this hook + CTA format in upcoming posts.",
                        "impact_level": "MEDIUM",
                    }
                ],
                "engagement_potential_score": {
                    "emotional_resonance": 6.0,
                    "shareability": 7.0,
                    "save_worthiness": 8.0,
                    "comment_potential": 6.0,
                    "novelty_or_value": 7.0,
                    "total": 34.0,
                },
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    target_post = _build_post("m_s2_target", "How this works?\nLearn the process #growth #creator comment below")
    history = [
        _build_post("m_s2_h1", "Simple caption #a"),
        _build_post("m_s2_h2", "Another caption #a #b"),
        _build_post("m_s2_h3", "Third caption #a #b #c"),
    ]

    response = asyncio.run(build_single_post_insights(target_post=target_post, historical_posts=history, run_ai=True))

    assert response["ai_analysis"] is not None
    assert "caption_effectiveness_score" in response["ai_analysis"]
    assert response["post"].caption_effectiveness_score.s2_raw_0_100 >= 0
    assert response["post"].caption_effectiveness_score.total_0_50 >= 0.0
    assert (
        response["ai_analysis"]["caption_effectiveness_score"]["s2_raw_0_100"]
        == response["post"].caption_effectiveness_score.s2_raw_0_100
    )

    cache_key = ai_analysis_service._cache_key(target_post)
    assert cache_key in ai_analysis_service._ANALYSIS_CACHE
    assert "caption_effectiveness_score" in ai_analysis_service._ANALYSIS_CACHE[cache_key].result
