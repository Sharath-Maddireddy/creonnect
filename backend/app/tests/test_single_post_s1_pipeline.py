"""Integration-ish tests for S1 wiring in single-post insights pipeline."""

import asyncio
import json
import sys
import types
from datetime import datetime, timezone

from backend.app.domain.post_models import (
    BenchmarkMetrics,
    CoreMetrics,
    DerivedMetrics,
    SinglePostInsights,
)
from backend.app.services import ai_analysis_service
from backend.app.services.post_insights_service import build_single_post_insights


def _build_post(
    media_id: str,
    reach: int,
    engagement_rate: float,
    media_url: str | None = None,
    caption_text: str = "",
) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_1",
        media_id=media_id,
        media_url=media_url,
        media_type="IMAGE",
        caption_text=caption_text,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(
            reach=reach,
            impressions=reach + 200,
            likes=120,
            comments=20,
            saves=15,
            shares=10,
            profile_visits=8,
            website_taps=2,
        ),
        derived_metrics=DerivedMetrics(engagement_rate=engagement_rate),
        benchmark_metrics=BenchmarkMetrics(),
    )


def test_build_single_post_insights_includes_s1(monkeypatch) -> None:
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
        return json.dumps(
            {
                "summary": "Strong post performance with clear visual hook and above-average engagement.",
                "drivers": [
                    {
                        "id": "d1",
                        "label": "Strong hook",
                        "type": "POSITIVE",
                        "explanation": "hook_strength_score is high.",
                    }
                ],
                "recommendations": [
                    {
                        "id": "r1",
                        "text": "Repeat this framing style in upcoming posts.",
                        "impact_level": "MEDIUM",
                    }
                ],
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    target_post = _build_post(
        "m_target",
        reach=2000,
        engagement_rate=0.07,
        media_url="https://example.com/post.jpg",
        caption_text="Build in public and save this workflow.",
    )
    history = [
        _build_post("m_1", reach=1500, engagement_rate=0.05),
        _build_post("m_2", reach=1700, engagement_rate=0.06),
        _build_post("m_3", reach=1900, engagement_rate=0.08),
    ]

    response = asyncio.run(build_single_post_insights(target_post=target_post, historical_posts=history, run_ai=True))

    assert response["post"].visual_quality_score.total > 0.0
    assert response["post"].content_clarity_score.total > 0.0
    assert response["ai_analysis"] is not None
    assert response["ai_analysis"]["visual_quality_score"]["total"] == response["post"].visual_quality_score.total
    assert response["ai_analysis"]["content_clarity_score"]["total"] == response["post"].content_clarity_score.total
    assert captured_prompts

    prompt_user_payload = json.loads(captured_prompts[0]["user"])
    assert "s1_visual_quality" in prompt_user_payload["context"]
    assert "s3_content_clarity" in prompt_user_payload["context"]
    assert prompt_user_payload["context"]["s1_visual_quality"]["total"] == response["post"].visual_quality_score.total
    assert prompt_user_payload["context"]["s3_content_clarity"]["total"] == response["post"].content_clarity_score.total


def test_run_vision_analysis_reads_gemini_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-visible")

    async def fake_generate_gemini_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
        assert api_key == "test-key-visible"
        assert isinstance(instruction, str) and instruction
        assert media_url == "https://example.com/post.jpg"
        return json.dumps(
            {
                "objects": ["person"],
                "scene_description": "Person presenting",
                "detected_text": None,
                "visual_style": "clean",
                "technical_flaws": "Slight blur on subject edges",
                "hook_strength_score": 0.75,
            }
        )

    monkeypatch.setattr(ai_analysis_service, "_generate_gemini_vision_json", fake_generate_gemini_vision_json)

    post = _build_post(
        "m_vision_env",
        reach=1000,
        engagement_rate=0.05,
        media_url="https://example.com/post.jpg",
    )
    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert result["status"] == "ok"
    assert isinstance(result["signals"], list)
    assert result["signals"][0]["technical_flaws"] == ["Slight blur on subject edges"]


def test_call_gemini_vision_api_falls_back_when_google_genai_client_is_missing(monkeypatch) -> None:
    class FakeLegacyModel:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def generate_content(self, contents: list[object]):
            assert contents[0]
            assert contents[1]["mime_type"] == "image/jpeg"
            assert contents[1]["file_uri"] == "https://example.com/post.jpg"
            return types.SimpleNamespace(
                text=json.dumps(
                    {
                        "objects": ["person"],
                        "scene_description": "Person presenting",
                        "detected_text": None,
                        "visual_style": "clean",
                        "hook_strength_score": 0.75,
                    }
                )
            )

    fake_genai_module = types.ModuleType("google.genai")
    fake_genai_types_module = types.ModuleType("google.genai.types")
    fake_genai_module.types = fake_genai_types_module

    fake_legacy_genai = types.ModuleType("google.generativeai")
    fake_legacy_genai.configure = lambda **_kwargs: None
    fake_legacy_genai.GenerativeModel = FakeLegacyModel

    fake_google_module = types.ModuleType("google")
    fake_google_module.__path__ = []
    fake_google_module.genai = fake_genai_module

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_genai_types_module)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_legacy_genai)

    text = ai_analysis_service._call_gemini_vision_api(
        api_key="test-key",
        instruction="Describe this image",
        media_url="https://example.com/post.jpg",
    )

    payload = json.loads(text)
    assert payload["scene_description"] == "Person presenting"


def test_run_vision_analysis_repairs_malformed_output(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-visible")

    async def fake_generate_gemini_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
        assert api_key == "test-key-visible"
        assert media_url == "https://example.com/post.jpg"
        return "scene_description Person presenting\n  broken indentation"

    async def fake_repair_gemini_vision_json(*, api_key: str, raw_text: str) -> str:
        assert api_key == "test-key-visible"
        assert "broken indentation" in raw_text
        return json.dumps(
            {
                "objects": ["person"],
                "scene_description": "Person presenting",
                "detected_text": None,
                "visual_style": "clean",
                "technical_flaws": ["Slight blur"],
                "hook_strength_score": 0.75,
            }
        )

    monkeypatch.setattr(ai_analysis_service, "_generate_gemini_vision_json", fake_generate_gemini_vision_json)
    monkeypatch.setattr(ai_analysis_service, "_repair_gemini_vision_json", fake_repair_gemini_vision_json)

    post = _build_post("m_repair", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.jpg")
    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert result["status"] == "ok"
    assert result["signals"][0]["scene_description"] == "Person presenting"
    assert result["signals"][0]["technical_flaws"] == ["Slight blur"]


def test_run_vision_analysis_retries_with_simplified_prompt(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-visible")
    calls: list[str] = []

    async def fake_generate_gemini_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
        assert api_key == "test-key-visible"
        assert media_url == "https://example.com/post.jpg"
        calls.append(instruction)
        if len(calls) == 1:
            return ""
        assert instruction == ai_analysis_service._SIMPLIFIED_GEMINI_VISION_PROMPT
        return json.dumps(
            {
                "objects": ["person"],
                "scene_description": "Recovered on retry",
                "detected_text": None,
                "visual_style": "clean",
                "technical_flaws": [],
                "hook_strength_score": 0.55,
            }
        )

    async def fake_repair_gemini_vision_json(*, api_key: str, raw_text: str) -> str:
        raise AssertionError("Repair should not run for empty primary response in this scenario")

    monkeypatch.setattr(ai_analysis_service, "_generate_gemini_vision_json", fake_generate_gemini_vision_json)
    monkeypatch.setattr(ai_analysis_service, "_repair_gemini_vision_json", fake_repair_gemini_vision_json)

    post = _build_post("m_retry", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.jpg")
    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert result["status"] == "ok"
    assert result["signals"][0]["scene_description"] == "Recovered on retry"
    assert len(calls) == 2
