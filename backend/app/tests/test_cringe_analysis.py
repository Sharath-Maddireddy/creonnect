"""Tests for cringe helper utilities and S6 integration penalties."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from backend.app.ai.cringe_analysis import (
    build_cringe_section_for_brand_safety,
    derive_cringe_label,
    enforce_cringe_floor,
)
from backend.app.analytics.s6_brand_safety_engine import compute_s6_brand_safety
from backend.app.api import post_analysis_routes
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights, VisionAnalysis, VisionSignal
from backend.main import app


def test_enforce_cringe_floor_raises_score_for_strong_signals() -> None:
    result = enforce_cringe_floor(30, ["awkward", "cringe", "forced"])
    assert result >= 70


def test_derive_cringe_label_thresholds() -> None:
    assert derive_cringe_label(None) is None
    assert derive_cringe_label(30) == "not_cringe"
    assert derive_cringe_label(45) == "uncertain"
    assert derive_cringe_label(65) == "cringe"


def test_vision_signal_cringe_fields_are_validated_and_derived() -> None:
    signal = VisionSignal(
        cringe_score=75,
        cringe_signals=["forced smile", "awkward pose", "confusing concept"],
    )
    assert signal.cringe_score == 75
    assert signal.cringe_label == "cringe"
    assert signal.is_cringe is True
    assert len(signal.cringe_signals) == 3


def test_vision_signal_uncertain_label_can_still_flag_cringe_detection() -> None:
    signal = VisionSignal(cringe_score=50, cringe_signals=["awkward delivery"])
    assert signal.cringe_label == "uncertain"
    assert signal.is_cringe is True


def test_build_cringe_section_for_brand_safety_extracts_signal() -> None:
    section = build_cringe_section_for_brand_safety(
        {
            "provider": "gemini",
            "status": "ok",
            "signals": [
                {
                    "cringe_score": 62,
                    "cringe_signals": ["awkward posing", "forced acting"],
                    "production_level": "low",
                    "adult_content_detected": False,
                }
            ],
        }
    )
    assert section == {
        "cringe_score": 62,
        "cringe_label": "cringe",
        "is_cringe": True,
        "cringe_signals": ["awkward posing", "forced acting"],
        "production_level": "low",
        "adult_content_detected": False,
    }


def test_s6_applies_cringe_adult_and_low_production_penalties() -> None:
    score = compute_s6_brand_safety(
        caption_text="Clean caption",
        vision={
            "provider": "gemini",
            "status": "ok",
            "signals": [
                {
                    "objects": ["person"],
                    "cringe_score": 82,
                    "cringe_signals": ["confusing concept", "awkward pose", "forced smile"],
                    "production_level": "low",
                    "adult_content_detected": True,
                }
            ],
        },
        s1_total_0_50=45.0,
        extracted_brand_mentions=None,
        extra_flags=None,
    )
    penalty_keys = {penalty.key for penalty in score.penalties}
    assert score.s6_raw_0_100 == 40
    assert score.total_0_50 == 20.0
    assert {"extreme_cringe", "adult_content", "low_production"}.issubset(penalty_keys)
    assert score.flags["cringe_detected"] is True
    assert score.flags["adult_content_detected"] is True
    assert score.flags["low_production"] is True


def test_cringe_summary_endpoint_returns_cached_payload(monkeypatch) -> None:
    async def _fake_build_single_post_insights(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        post = SinglePostInsights(
            account_id="acct_1",
            media_id="post_123",
            media_url="https://example.com/post.jpg",
            media_type="IMAGE",
            caption_text="Caption",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            core_metrics=CoreMetrics(reach=1000, impressions=1200, likes=100, comments=10),
            derived_metrics=DerivedMetrics(engagement_rate=0.05),
            benchmark_metrics=BenchmarkMetrics(),
            vision_analysis=VisionAnalysis(
                provider="gemini",
                status="ok",
                signals=[
                    {
                        "objects": ["person"],
                        "scene_description": "demo",
                        "detected_text": None,
                        "visual_style": "clean",
                        "hook_strength_score": 0.7,
                        "cringe_score": 66,
                        "cringe_signals": ["awkward pose", "confusing concept"],
                        "cringe_fixes": ["Use natural body language"],
                        "production_level": "low",
                        "adult_content_detected": False,
                        "adult_content_confidence": 5,
                    }
                ],
            ),
        )
        return {
            "post": post,
            "content_score": {"score": 0, "band": "NEEDS_WORK"},
            "ai_analysis": {"vision_status": "ok", "fallback_used": False},
        }

    monkeypatch.setattr(post_analysis_routes, "build_single_post_insights", _fake_build_single_post_insights)

    client = TestClient(app)
    post_response = client.post(
        "/api/post-analysis",
        json={
            "post_id": "post_123",
            "account_id": "acct_1",
            "platform": "instagram",
            "post_type": "IMAGE",
            "media_url": "https://example.com/post.jpg",
            "caption_text": "Caption",
            "likes": 100,
            "comments": 10,
        },
    )
    assert post_response.status_code == 200

    summary = client.get("/api/v1/posts/post_123/cringe-summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["cringe_score"] == 66
    assert payload["cringe_label"] == "cringe"
    assert payload["is_cringe"] is True
    assert payload["production_level"] == "low"
    assert payload["vision_status"] == "ok"
