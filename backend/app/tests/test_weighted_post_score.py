"""Tests for spec-aligned weighted post score P."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from backend.app.analytics.post_weighted_score_engine import compute_weighted_post_score
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.services import ai_analysis_service
from backend.app.services.post_insights_service import build_single_post_insights


def _assert_close(left: float, right: float, tol: float = 1e-6) -> None:
    assert abs(left - right) <= tol


def _build_post(media_id: str, media_type: str = "IMAGE") -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_weighted",
        media_id=media_id,
        media_url="https://example.com/post.jpg",
        media_type=media_type,
        caption_text="Useful post with practical insights.",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(
            reach=2000,
            impressions=2200,
            likes=100,
            comments=15,
            saves=12,
            shares=8,
            profile_visits=7,
            website_taps=2,
        ),
        derived_metrics=DerivedMetrics(engagement_rate=0.07),
        benchmark_metrics=BenchmarkMetrics(),
    )


def test_image_with_s1_s3_s5_only() -> None:
    result = compute_weighted_post_score(
        post_type="IMAGE",
        s1=40.0,
        s2=None,
        s3=30.0,
        s4=None,
        s5=20.0,
        s6=None,
        s7=None,
    )
    expected = (40.0 * 0.23 + 30.0 * 0.15 + 20.0 * 0.15) / (0.23 + 0.15 + 0.15)

    _assert_close(result.normalized_score_0_50, round(expected, 2))
    _assert_close(result.score, round(expected * 2.0, 2))
    assert any("missing" in note.lower() for note in result.notes)


def test_image_all_components_exact() -> None:
    result = compute_weighted_post_score(
        post_type="IMAGE",
        s1=10.0,
        s2=20.0,
        s3=30.0,
        s4=40.0,
        s5=50.0,
        s6=25.0,
        s7=None,
    )
    expected = (10.0 * 0.23 + 20.0 * 0.22 + 30.0 * 0.15 + 40.0 * 0.15 + 50.0 * 0.15 + 25.0 * 0.10)

    _assert_close(result.normalized_score_0_50, round(expected, 2))
    _assert_close(result.score, round(expected * 2.0, 2))
    assert not any("missing" in note.lower() for note in result.notes)


def test_reel_with_missing_s7() -> None:
    result = compute_weighted_post_score(
        post_type="REEL",
        s1=45.0,
        s2=42.0,
        s3=37.0,
        s4=35.0,
        s5=30.0,
        s6=28.0,
        s7=None,
    )
    expected = (
        45.0 * 0.20
        + 42.0 * 0.20
        + 37.0 * 0.15
        + 35.0 * 0.15
        + 30.0 * 0.15
        + 28.0 * 0.10
    ) / 0.95

    _assert_close(result.normalized_score_0_50, round(expected, 2))
    assert any("missing" in note.lower() for note in result.notes)


def test_unknown_post_type_defaults_image() -> None:
    result = compute_weighted_post_score(
        post_type="CAROUSEL",
        s1=50.0,
        s2=None,
        s3=None,
        s4=None,
        s5=None,
        s6=None,
        s7=None,
    )
    assert result.post_type == "IMAGE"
    assert any("defaulted to image" in note.lower() for note in result.notes)


def test_fallback_when_all_missing() -> None:
    result = compute_weighted_post_score(
        post_type="IMAGE",
        s1=None,
        s2=None,
        s3=None,
        s4=None,
        s5=None,
        s6=None,
        s7=None,
    )
    assert result.normalized_score_0_50 == 25.0
    assert result.score == 50.0
    assert result.weights_used == {}
    assert any("fallback" in note.lower() for note in result.notes)


def test_bounds_clamp_and_max_guard() -> None:
    result = compute_weighted_post_score(
        post_type="REEL",
        s1=120.0,
        s2=-20.0,
        s3=75.0,
        s4=999.0,
        s5=-5.0,
        s6=60.0,
        s7=500.0,
    )
    assert 0.0 <= result.normalized_score_0_50 <= 50.0
    assert 0.0 <= result.score <= 100.0
    assert result.score <= 100.0


def test_missing_components_normalize_not_zero_fill() -> None:
    normalized_case = compute_weighted_post_score(
        post_type="IMAGE",
        s1=40.0,
        s2=None,
        s3=30.0,
        s4=None,
        s5=20.0,
        s6=None,
        s7=None,
    )
    zero_fill_case = compute_weighted_post_score(
        post_type="IMAGE",
        s1=40.0,
        s2=0.0,
        s3=30.0,
        s4=0.0,
        s5=20.0,
        s6=0.0,
        s7=None,
    )
    assert normalized_case.normalized_score_0_50 > zero_fill_case.normalized_score_0_50


def test_integration_single_post_includes_weighted_score_and_cache(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    captured_prompts: list[dict[str, str]] = []

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {
            "provider": "gemini",
            "status": "ok",
            "signals": [
                {
                    "objects": ["person", "whiteboard"],
                    "primary_objects": ["person", "whiteboard"],
                    "dominant_focus": "person",
                    "scene_description": "Presenter and board",
                    "detected_text": "3 growth tips",
                    "hook_strength_score": 0.88,
                }
            ],
        }

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        captured_prompts.append(prompt)
        return json.dumps(
            {
                "summary": "Good post performance with clear value and a solid hook.",
                "drivers": [
                    {
                        "id": "d1",
                        "label": "Strong clarity",
                        "type": "POSITIVE",
                        "explanation": "Visual and caption align on a single message.",
                    }
                ],
                "recommendations": [
                    {
                        "id": "r1",
                        "text": "Keep this exact framing structure for future posts.",
                        "impact_level": "MEDIUM",
                    }
                ],
                "engagement_potential_score": {
                    "emotional_resonance": 7.0,
                    "shareability": 7.0,
                    "save_worthiness": 8.0,
                    "comment_potential": 6.0,
                    "novelty_or_value": 8.0,
                    "total": 36.0,
                },
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    target_post = _build_post("m_weighted_target", media_type="IMAGE")
    history = [
        _build_post("m_weighted_h1"),
        _build_post("m_weighted_h2"),
        _build_post("m_weighted_h3"),
    ]

    response = asyncio.run(build_single_post_insights(target_post=target_post, historical_posts=history, run_ai=True))

    assert response["post"].weighted_post_score.score > 0.0
    assert response["ai_analysis"] is not None
    assert "weighted_post_score" in response["ai_analysis"]
    assert response["ai_analysis"]["weighted_post_score"]["score"] == response["post"].weighted_post_score.score
    assert response["post"].weighted_post_score.score == round(
        response["post"].weighted_post_score.normalized_score_0_50 * 2.0, 2
    )

    assert captured_prompts
    payload = json.loads(captured_prompts[0]["user"])
    assert "weighted_post_score" in payload["context"]

    cache_key = ai_analysis_service._cache_key(target_post)
    assert cache_key in ai_analysis_service._ANALYSIS_CACHE
    assert "weighted_post_score" in ai_analysis_service._ANALYSIS_CACHE[cache_key].result
