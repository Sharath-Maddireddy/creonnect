"""Tests for S5 engagement potential scoring and guardrails."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from backend.app.ai.toon import dumps as toon_dumps
from backend.app.domain.post_models import (
    BenchmarkMetrics,
    ContentClarityScore,
    CoreMetrics,
    DerivedMetrics,
    SinglePostInsights,
    VisualQualityScore,
)
from backend.app.services import ai_analysis_service
from backend.app.services.post_insights_service import build_single_post_insights


def _build_post(
    media_id: str = "m_s5",
    caption_text: str = "A useful post with practical steps.",
) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_s5",
        media_id=media_id,
        media_url="https://example.com/post.jpg",
        media_type="IMAGE",
        caption_text=caption_text,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(
            reach=2000,
            impressions=2300,
            likes=120,
            comments=25,
            saves=30,
            shares=15,
            profile_visits=11,
            website_taps=3,
        ),
        derived_metrics=DerivedMetrics(engagement_rate=0.08),
        benchmark_metrics=BenchmarkMetrics(),
    )


def _valid_llm_payload(engagement_block: dict[str, object]) -> str:
    return toon_dumps(
        {
            "summary": "Solid post with clear positioning and above-average audience response.",
            "drivers": [
                {
                    "id": "d1",
                    "label": "Clear visual anchor",
                    "type": "POSITIVE",
                    "explanation": "Dominant focus and concise message aid comprehension.",
                }
            ],
            "recommendations": [
                {
                    "id": "r1",
                    "text": "Repeat this framing style and CTA structure.",
                    "impact_level": "MEDIUM",
                }
            ],
            "engagement_potential_score": engagement_block,
        }
    )


def test_s5_parse_valid_output() -> None:
    raw = _valid_llm_payload(
        {
            "emotional_resonance": 7.0,
            "shareability": 8.0,
            "save_worthiness": 7.0,
            "comment_potential": 6.0,
            "novelty_or_value": 8.0,
            "total": 36.0,
            "notes": ["valid"],
        }
    )
    summary, drivers, recommendations, engagement = asyncio.run(
        ai_analysis_service._parse_llm_response_with_repair(raw, llm_client=None)
    )
    assert summary is not None
    assert drivers
    assert recommendations
    assert ai_analysis_service._sanitize_engagement_potential_score(engagement) is not None


def test_s5_parse_invalid_then_repair(monkeypatch) -> None:
    async def fake_repair(raw_text: str | None, llm_client):
        return _valid_llm_payload(
            {
                "emotional_resonance": 6.0,
                "shareability": 6.0,
                "save_worthiness": 6.0,
                "comment_potential": 6.0,
                "novelty_or_value": 6.0,
                "total": 30.0,
                "notes": [],
            }
        )

    monkeypatch.setattr(ai_analysis_service, "_repair_llm_toon_output", fake_repair)
    summary, _, _, engagement = asyncio.run(
        ai_analysis_service._parse_llm_response_with_repair("not-json-output", llm_client=None)
    )
    assert summary is not None
    sanitized = ai_analysis_service._sanitize_engagement_potential_score(engagement)
    assert sanitized is not None
    assert sanitized.total == 30.0


def test_s5_still_fallback_if_repair_fails(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {"provider": "gemini", "status": "ok", "signals": [{"dominant_focus": "person"}]}

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        return "INVALID_NON_JSON_OUTPUT"

    async def fake_repair(raw_text: str | None, llm_client):
        return "STILL_INVALID"

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)
    monkeypatch.setattr(ai_analysis_service, "_repair_llm_toon_output", fake_repair)

    post = _build_post(media_id="m_s5_repair_fail")
    result = asyncio.run(ai_analysis_service.analyze_single_post_ai(post))
    s5 = result["engagement_potential_score"]

    assert s5["total"] == 25.0
    assert s5["notes"] == ["fallback: invalid AI output"]


def test_s5_numeric_strings_parse_without_fallback(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {"provider": "gemini", "status": "ok", "signals": [{"dominant_focus": "person"}]}

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        return _valid_llm_payload(
            {
                "emotional_resonance": "7",
                "shareability": "8.5",
                "save_worthiness": "7",
                "comment_potential": "6",
                "novelty_or_value": "8",
                "total": "99",
                "notes": [],
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    post = _build_post(media_id="m_s5_numeric_strings")
    result = asyncio.run(ai_analysis_service.analyze_single_post_ai(post))

    assert result["fallback_used"] is False
    s5 = result["engagement_potential_score"]
    assert s5["total"] == (
        s5["emotional_resonance"]
        + s5["shareability"]
        + s5["save_worthiness"]
        + s5["comment_potential"]
        + s5["novelty_or_value"]
    )


def test_s5_notes_string_parse_without_fallback(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {"provider": "gemini", "status": "ok", "signals": [{"dominant_focus": "person"}]}

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        return _valid_llm_payload(
            {
                "emotional_resonance": 6.0,
                "shareability": 6.0,
                "save_worthiness": 6.0,
                "comment_potential": 6.0,
                "novelty_or_value": 6.0,
                "total": 30.0,
                "notes": "single note",
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    post = _build_post(media_id="m_s5_notes_string")
    result = asyncio.run(ai_analysis_service.analyze_single_post_ai(post))

    assert result["fallback_used"] is False
    assert result["engagement_potential_score"]["notes"] == ["single note"]


def test_s5_extra_keys_dropped_without_fallback(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {"provider": "gemini", "status": "ok", "signals": [{"dominant_focus": "person"}]}

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        return _valid_llm_payload(
            {
                "emotional_resonance": 6.0,
                "shareability": 6.0,
                "save_worthiness": 6.0,
                "comment_potential": 6.0,
                "novelty_or_value": 6.0,
                "total": 30.0,
                "notes": [],
                "virality_score": 9.0,
                "nested": {"ignored": True},
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    post = _build_post(media_id="m_s5_extra_keys")
    result = asyncio.run(ai_analysis_service.analyze_single_post_ai(post))

    assert result["fallback_used"] is False
    s5 = result["engagement_potential_score"]
    assert s5["total"] == 30.0


def test_s5_validation_success(monkeypatch) -> None:
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
                    "scene_description": "Presenter explaining a concept",
                    "detected_text": "3 growth tips",
                    "hook_strength_score": 0.82,
                }
            ],
        }

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        return _valid_llm_payload(
            {
                "emotional_resonance": 7.0,
                "shareability": 8.0,
                "save_worthiness": 7.0,
                "comment_potential": 6.0,
                "novelty_or_value": 8.0,
                "total": 36.0,
                "notes": ["highly useful and relatable"],
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    post = _build_post()
    result = asyncio.run(ai_analysis_service.analyze_single_post_ai(post))
    s5 = result["engagement_potential_score"]

    assert s5["total"] == 36.0
    assert s5["total"] == (
        s5["emotional_resonance"]
        + s5["shareability"]
        + s5["save_worthiness"]
        + s5["comment_potential"]
        + s5["novelty_or_value"]
    )


def test_s5_validation_failure_fallback(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {"provider": "gemini", "status": "ok", "signals": [{"objects": ["poster"]}]}

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        # Missing required keys in engagement_potential_score payload.
        return _valid_llm_payload(
            {
                "emotional_resonance": 7.0,
                "shareability": 8.0,
                "total": 15.0,
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    post = _build_post(media_id="m_s5_invalid")
    result = asyncio.run(ai_analysis_service.analyze_single_post_ai(post))
    s5 = result["engagement_potential_score"]

    assert s5["total"] == 25.0
    assert s5["emotional_resonance"] == 5.0
    assert s5["notes"] == ["fallback: invalid AI output"]


def test_s5_clamping_and_deterministic_postprocessing(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {"provider": "gemini", "status": "ok", "signals": [{"dominant_focus": "person"}]}

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        return _valid_llm_payload(
            {
                "emotional_resonance": 12,
                "shareability": -1,
                "save_worthiness": 8.4,
                "comment_potential": 11,
                "novelty_or_value": -4,
                "total": 999,
                "notes": ["raw values out of bounds"],
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    post_1 = _build_post(media_id="m_s5_clamp_1")
    result_1 = asyncio.run(ai_analysis_service.analyze_single_post_ai(post_1))
    s5_1 = result_1["engagement_potential_score"]

    post_2 = _build_post(media_id="m_s5_clamp_2")
    result_2 = asyncio.run(ai_analysis_service.analyze_single_post_ai(post_2))
    s5_2 = result_2["engagement_potential_score"]

    assert 0.0 <= s5_1["emotional_resonance"] <= 10.0
    assert 0.0 <= s5_1["shareability"] <= 10.0
    assert 0.0 <= s5_1["save_worthiness"] <= 10.0
    assert 0.0 <= s5_1["comment_potential"] <= 10.0
    assert 0.0 <= s5_1["novelty_or_value"] <= 10.0
    assert s5_1["total"] == (
        s5_1["emotional_resonance"]
        + s5_1["shareability"]
        + s5_1["save_worthiness"]
        + s5_1["comment_potential"]
        + s5_1["novelty_or_value"]
    )
    assert s5_1 == s5_2


def test_s5_consistency_cap_for_low_s1_s3(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {"provider": "gemini", "status": "ok", "signals": [{"objects": ["a", "b", "c", "d", "e", "f"]}]}

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        return _valid_llm_payload(
            {
                "emotional_resonance": 9.0,
                "shareability": 9.0,
                "save_worthiness": 9.0,
                "comment_potential": 9.0,
                "novelty_or_value": 9.0,
                "total": 45.0,
                "notes": [],
            }
        )

    def fake_s1(_vision: dict[str, object]) -> VisualQualityScore:
        return VisualQualityScore(
            composition=2.0,
            lighting=2.0,
            subject_clarity=2.0,
            aesthetic_quality=2.0,
            total=10.0,
        )

    async def fake_s3(_vision: dict[str, object], _caption: str) -> ContentClarityScore:
        return ContentClarityScore(
            message_singularity=2.0,
            context_clarity=2.0,
            caption_alignment=2.0,
            visual_message_support=2.0,
            cognitive_load=2.0,
            total=10.0,
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)
    monkeypatch.setattr(ai_analysis_service, "compute_visual_quality_score", fake_s1)
    monkeypatch.setattr(ai_analysis_service, "analyze_content_clarity_via_llm", fake_s3)

    post = _build_post(media_id="m_s5_cap")
    result = asyncio.run(ai_analysis_service.analyze_single_post_ai(post))
    s5 = result["engagement_potential_score"]

    assert s5["total"] == 30.0
    assert any("consistency cap applied" in note for note in s5["notes"])


def test_s5_integration_in_pipeline_prompt_and_cache(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    captured_prompts: list[dict[str, str]] = []

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {
            "provider": "gemini",
            "status": "ok",
            "signals": [
                {
                    "objects": ["person", "laptop"],
                    "primary_objects": ["person", "laptop"],
                    "dominant_focus": "person",
                    "detected_text": "Build in public",
                    "hook_strength_score": 0.88,
                    "scene_description": "Person presenting content",
                    "visual_style": "clean",
                }
            ],
        }

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        captured_prompts.append(prompt)
        return _valid_llm_payload(
            {
                "emotional_resonance": 6.0,
                "shareability": 7.0,
                "save_worthiness": 7.0,
                "comment_potential": 6.0,
                "novelty_or_value": 8.0,
                "total": 34.0,
                "notes": [],
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    target_post = _build_post(media_id="m_s5_pipe", caption_text="Build in public and save this workflow.")
    history = [
        _build_post(media_id="m_s5_h1"),
        _build_post(media_id="m_s5_h2"),
        _build_post(media_id="m_s5_h3"),
    ]

    response = asyncio.run(build_single_post_insights(target_post=target_post, historical_posts=history, run_ai=True))

    assert response["post"].engagement_potential_score.total > 0.0
    assert response["ai_analysis"] is not None
    assert (
        response["ai_analysis"]["engagement_potential_score"]["total"]
        == response["post"].engagement_potential_score.total
    )
    assert captured_prompts
    assert "engagement_potential_score" in captured_prompts[0]["system"]

    cache_key = ai_analysis_service._cache_key(target_post)
    assert cache_key in ai_analysis_service._ANALYSIS_CACHE
    assert "engagement_potential_score" in ai_analysis_service._ANALYSIS_CACHE[cache_key].result
