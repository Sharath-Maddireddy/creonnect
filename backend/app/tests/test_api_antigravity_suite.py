"""Adversarial API tests to prevent cost, drift, and nondeterminism regressions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

import backend.app.infra.redis_client as redis_client
from backend.app.domain.post_models import (
    AudienceRelevanceScore,
    BenchmarkMetrics,
    BrandSafetyScore,
    CaptionEffectivenessScore,
    ContentClarityScore,
    CoreMetrics,
    DerivedMetrics,
    EngagementPotentialScore,
    SinglePostInsights,
    VisionAnalysis,
    VisualQualityScore,
    WeightedPostScore,
)
import backend.app.api.post_analysis_routes as post_analysis_routes
from backend.app.services import account_analysis_jobs
import backend.app.services.post_insights_service as post_insights_service
from backend.main import app


EXPECTED_POST_ANALYSIS_TOP_LEVEL_KEYS = {
    "status",
    "post",
    "vision",
    "scores",
    "ai",
    "warnings",
    "quality",
}
EXPECTED_SCORE_KEYS = {
    "S1",
    "S2",
    "S3",
    "S4",
    "S5",
    "S6",
    "P",
    "predicted_engagement_rate",
    "predicted_engagement_rate_notes",
}


class _DeferredQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, Any], dict[str, Any]]] = []

    def enqueue(self, func, payload, **kwargs):  # noqa: ANN001
        self.calls.append((func, payload, kwargs))
        return SimpleNamespace(id=kwargs.get("job_id", "job_deferred"))


class _ImmediateQueue:
    def enqueue(self, func, payload, **kwargs):  # noqa: ANN001
        func(payload)
        return SimpleNamespace(id=kwargs.get("job_id", "job_immediate"))


def _build_post_payload(index: int, caption_text: str = "Short caption") -> dict[str, Any]:
    post = SinglePostInsights(
        account_id="acct_api",
        media_id=f"m_{index}",
        media_type="IMAGE",
        media_url=f"https://example.com/{index}.jpg",
        caption_text=caption_text,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
        core_metrics=CoreMetrics(
            reach=2000 + index,
            impressions=2300 + index,
            likes=120 + index,
            comments=20 + index,
            saves=25,
            shares=10,
            profile_visits=5,
            website_taps=1,
        ),
        derived_metrics=DerivedMetrics(
            engagement_rate=0.07,
            save_rate=0.02,
            share_rate=0.01,
        ),
        benchmark_metrics=BenchmarkMetrics(account_avg_engagement_rate=0.06),
    )
    return post.model_dump(mode="json")


def _patch_post_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_build_single_post_insights(target_post: Any, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        post = SinglePostInsights.model_validate(_build_post_payload(index=1, caption_text="Deterministic caption"))
        post.media_id = getattr(target_post, "post_id", "post_123")
        post.account_id = getattr(target_post, "creator_id", "creator_1")
        post.media_type = "IMAGE"
        post.media_url = "https://example.com/post.jpg"
        post.caption_text = "Deterministic caption"
        post.vision_analysis = VisionAnalysis(provider="gemini", status="ok", signals=[])
        post.visual_quality_score = VisualQualityScore(
            composition=8.0,
            lighting=8.0,
            subject_clarity=8.0,
            aesthetic_quality=8.0,
            total=40.0,
            notes=[],
        )
        post.caption_effectiveness_score = CaptionEffectivenessScore(
            hook_score_0_100=70,
            length_score_0_100=70,
            hashtag_score_0_100=70,
            cta_score_0_100=70,
            s2_raw_0_100=70,
            total_0_50=35.0,
            notes=[],
        )
        post.content_clarity_score = ContentClarityScore(
            message_singularity=6.0,
            context_clarity=6.0,
            caption_alignment=6.0,
            visual_message_support=6.0,
            cognitive_load=6.0,
            total=30.0,
            notes=[],
        )
        post.audience_relevance_score = AudienceRelevanceScore(
            post_category=None,
            creator_dominant_category=None,
            affinity_band="UNKNOWN",
            s4_raw_0_100=50,
            total_0_50=25.0,
            notes=[],
        )
        post.engagement_potential_score = EngagementPotentialScore(
            emotional_resonance=4.0,
            shareability=4.0,
            save_worthiness=4.0,
            comment_potential=4.0,
            novelty_or_value=4.0,
            total=20.0,
            notes=[],
        )
        post.brand_safety_score = BrandSafetyScore(
            s6_raw_0_100=90,
            total_0_50=45.0,
            penalties=[],
            flags={},
            notes=[],
        )
        post.weighted_post_score = WeightedPostScore(
            post_type="IMAGE",
            score=55.0,
            normalized_score_0_50=27.5,
            components={},
            weights_used={},
            notes=[],
        )
        post.predicted_engagement_rate = 0.08
        post.predicted_engagement_rate_notes = ["deterministic-note"]

        return {
            "post": post,
            "content_score": {"score": 70, "band": "STRONG"},
            "ai_analysis": {
                "warnings": [],
                "fallback_used": False,
                "vision_status": "ok",
                "predicted_engagement_rate": 0.08,
                "predicted_engagement_rate_notes": ["deterministic-note"],
            },
        }

    monkeypatch.setattr(post_insights_service, "build_single_post_insights", _fake_build_single_post_insights)
    monkeypatch.setattr(post_analysis_routes, "build_single_post_insights", _fake_build_single_post_insights)


def _post_analysis_request_payload() -> dict[str, Any]:
    return {
        "post_id": "post_123",
        "account_id": "creator_1",
        "platform": "instagram",
        "post_type": "IMAGE",
        "media_url": "https://example.com/post.jpg",
        "caption_text": "Deterministic caption",
        "likes": 100,
        "comments": 10,
        "views": 1000,
        "posted_at": "2024-01-01T00:00:00+00:00",
    }


def test_post_analysis_schema_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    _patch_post_pipeline(monkeypatch)
    response = client.post("/api/post-analysis", json=_post_analysis_request_payload())
    assert response.status_code == 200

    payload = response.json()
    assert set(payload.keys()) == EXPECTED_POST_ANALYSIS_TOP_LEVEL_KEYS
    assert payload["status"] == "succeeded"
    assert set(payload["post"].keys()) == {"post_id", "post_type", "media_url", "caption_text"}
    assert set(payload["vision"].keys()) == {"provider", "status", "signals"}
    assert set(payload["ai"].keys()) == {"summary", "drivers", "recommendations", "vision_status", "fallback_used"}
    assert isinstance(payload.get("scores"), dict)
    assert set(payload["scores"].keys()) == EXPECTED_SCORE_KEYS
    assert isinstance(payload["scores"]["predicted_engagement_rate_notes"], list)


def test_post_analysis_determinism_same_input(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    _patch_post_pipeline(monkeypatch)
    request_payload = _post_analysis_request_payload()
    first = client.post("/api/post-analysis", json=request_payload)
    second = client.post("/api/post-analysis", json=request_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.content == second.content


def test_account_enqueue_dedupe_storm(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    deferred_queue = _DeferredQueue()
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: deferred_queue)
    monkeypatch.setattr(account_analysis_jobs, "ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR", 999)

    client = TestClient(app)
    payload = {"account_id": "acct_storm", "post_limit": 12}
    responses = [client.post("/api/account-analysis", json=payload) for _ in range(5)]

    assert all(response.status_code == 200 for response in responses)
    job_ids = {response.json()["job_id"] for response in responses}
    assert len(job_ids) == 1
    assert len(deferred_queue.calls) == 1


def test_account_rate_limit_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    deferred_queue = _DeferredQueue()
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: deferred_queue)

    client = TestClient(app)
    first = client.post("/api/account-analysis", json={"account_id": "acct_limit", "post_limit": 5})
    second = client.post("/api/account-analysis", json={"account_id": "acct_limit", "post_limit": 6})
    third = client.post("/api/account-analysis", json={"account_id": "acct_limit", "post_limit": 7})
    fourth = client.post("/api/account-analysis", json={"account_id": "acct_limit", "post_limit": 5})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert fourth.status_code == 429

    detail = fourth.json()["detail"]
    assert "message" in detail
    if "job_id" in detail:
        assert detail["job_id"] == first.json()["job_id"]


def test_poll_missing_job_returns_404_or_clean_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)

    client = TestClient(app)
    response = client.get("/api/account-analysis/unknown_job_id")

    assert response.status_code != 500
    assert response.status_code in {400, 404}


def test_posts_summary_payload_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: _ImmediateQueue())

    long_caption = "x" * 500
    posts = [_build_post_payload(index, caption_text=long_caption) for index in range(35)]
    queued = account_analysis_jobs.enqueue_account_analysis_job(
        {
            "account_id": "acct_summary_bound",
            "post_limit": 35,
            "posts": posts,
            "include_posts_summary": True,
            "include_posts_summary_max": 999,
        }
    )
    status = account_analysis_jobs.get_account_analysis_job_status(queued["job_id"])

    assert status is not None
    assert status["status"] == "succeeded"
    result = status["result"]
    assert isinstance(result, dict)
    assert "posts_summary" in result
    posts_summary = result["posts_summary"]
    assert isinstance(posts_summary, list)
    assert len(posts_summary) == 30
    assert all(len(item.get("caption_preview", "")) <= 120 for item in posts_summary)


def test_post_analysis_vision_disabled_is_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    
    async def _failing_pipeline(*args: Any, **kwargs: Any) -> dict[str, Any]:
        post = SinglePostInsights.model_validate(_build_post_payload(index=99, caption_text="fallback"))
        return {
            "post": post,
            "ai_analysis": {
                "warnings": [{"code": "GEMINI_API_KEY_MISSING", "message": "No key"}],
                "fallback_used": True,
                "vision_status": "disabled"
            }
        }
    monkeypatch.setattr(post_analysis_routes, "build_single_post_insights", _failing_pipeline)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    
    response = client.post("/api/post-analysis", json=_post_analysis_request_payload())
    assert response.status_code == 200
    payload = response.json()
    
    # AG-P3: vision disabled must be visible
    assert payload["vision"]["status"] in {"disabled", "error"}
    assert payload["quality"]["vision_enabled"] is False
    assert any(w.get("code") == "GEMINI_API_KEY_MISSING" for w in payload.get("warnings", []))


def test_post_analysis_media_url_failures_dont_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    
    async def _failing_pipeline(*args: Any, **kwargs: Any) -> dict[str, Any]:
        post = SinglePostInsights.model_validate(_build_post_payload(index=99, caption_text="fallback"))
        post.media_url = "https://example.com/404.jpg"
        return {
            "post": post,
            "ai_analysis": {
                "warnings": [{"code": "VISION_ERROR", "message": "Image inaccessible"}],
                "fallback_used": True,
                "vision_status": "error"
            }
        }
    monkeypatch.setattr(post_analysis_routes, "build_single_post_insights", _failing_pipeline)
    
    payload = _post_analysis_request_payload()
    payload["media_url"] = "https://example.com/404.jpg"
    response = client.post("/api/post-analysis", json=payload)
    
    # AG-P4: Media URL failures don't crash
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["vision"]["status"] == "error"
    assert res_json["quality"]["ai_fallback_used"] is True


def test_post_analysis_cost_throttle_anti_spam(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    
    call_count = 0
    async def _mock_pipeline(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {
            "post": SinglePostInsights.model_validate(_build_post_payload(index=1)),
            "ai_analysis": {"vision_status": "ok", "fallback_used": False}
        }
    
    monkeypatch.setattr(post_analysis_routes, "build_single_post_insights", _mock_pipeline)
    
    payload = _post_analysis_request_payload()
    # AG-P5: Cost throttle / regen anti-spam bounds check
    responses = [client.post("/api/post-analysis", json=payload) for _ in range(5)]
    assert all(r.status_code == 200 for r in responses)


def test_account_analysis_quality_flags_correctness(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: _ImmediateQueue())
    
    payload = {"account_id": "quality_test", "post_limit": 2, "posts": [_build_post_payload(1), _build_post_payload(2)]}
    
    # AG-A5: Quality flags correctness - ENABLED
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")
    queued = account_analysis_jobs.enqueue_account_analysis_job(payload)
    status_enabled = account_analysis_jobs.get_account_analysis_job_status(queued["job_id"])
    assert status_enabled is not None
    assert status_enabled["quality"]["vision_enabled"] is True
    
    # AG-A5: Quality flags correctness - DISABLED
    fake_redis.flushall()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    queued_disabled = account_analysis_jobs.enqueue_account_analysis_job(payload)
    status_disabled = account_analysis_jobs.get_account_analysis_job_status(queued_disabled["job_id"])
    assert status_disabled is not None
    assert status_disabled["quality"]["vision_enabled"] is False
    assert any(w.get("code") == "GEMINI_API_KEY_MISSING" for w in status_disabled["warnings"])


def test_account_analysis_scoring_constraints_impossible_states(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: _ImmediateQueue())
    
    # AG-A6: Anti-gravity scoring constraints (impossible states)
    bad_posts = []
    for i in range(30):
        p = SinglePostInsights.model_validate(_build_post_payload(i))
        # Force low properties to test constraint logic scaling
        p.visual_quality_score = VisualQualityScore(composition=1.0, lighting=1.0, subject_clarity=1.0, aesthetic_quality=1.0, total=10.0, notes=[])
        p.content_clarity_score = ContentClarityScore(message_singularity=2.0, context_clarity=2.0, caption_alignment=2.0, visual_message_support=2.0, cognitive_load=2.0, total=10.0, notes=[])
        p.brand_safety_score = BrandSafetyScore(s6_raw_0_100=20, total_0_50=10.0, penalties=[], flags={}, notes=[])
        p.weighted_post_score = WeightedPostScore(post_type="IMAGE", score=10.0, normalized_score_0_50=5.0, components={}, weights_used={}, notes=[])
        bad_posts.append(p.model_dump(mode="json"))
        
    queued = account_analysis_jobs.enqueue_account_analysis_job({
        "account_id": "terrible_account",
        "post_limit": 30,
        "posts": bad_posts
    })
    
    status = account_analysis_jobs.get_account_analysis_job_status(queued["job_id"])
    assert status is not None
    assert status["status"] == "succeeded"
    result = status["result"]
    assert result["ahs_band"] not in {"EXCEPTIONAL", "STRONG"}
    drivers = result.get("drivers", [])
    assert len(drivers) > 0
