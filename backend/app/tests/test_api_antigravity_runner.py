"""Single anti-gravity API runner for post/account endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import fakeredis
import pytest
from fastapi.testclient import TestClient

import backend.app.infra.redis_client as redis_client
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.services import account_analysis_jobs
import backend.app.services.ai_analysis_service as ai_analysis_service
import backend.app.services.post_insights_service as post_insights_service
from backend.main import app


EXPECTED_POST_TOP_LEVEL_KEYS = {"status", "post", "scores", "vision", "ai", "warnings", "quality"}
EXPECTED_POST_SCORE_KEYS = {
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
        self.calls: list[tuple[object, dict, dict]] = []

    def enqueue(self, func, payload, **kwargs):  # noqa: ANN001
        self.calls.append((func, payload, kwargs))
        return SimpleNamespace(id=kwargs.get("job_id", "job_deferred"))


class _ImmediateQueue:
    def enqueue(self, func, payload, **kwargs):  # noqa: ANN001
        func(payload)
        return SimpleNamespace(id=kwargs.get("job_id", "job_immediate"))


def _post_payload(media_url: str = "https://example.com/post.jpg") -> dict:
    return {
        "post_id": "anti_gravity_post_1",
        "account_id": "anti_gravity_acct_1",
        "platform": "instagram",
        "post_type": "IMAGE",
        "media_url": media_url,
        "caption_text": "Deterministic caption for anti-gravity checks.",
        "likes": 100,
        "comments": 15,
        "views": 1200,
        "posted_at": "2024-01-01T00:00:00+00:00",
    }


def _build_post_dict(index: int, caption_text: str = "Short caption") -> dict:
    post = SinglePostInsights(
        account_id="acct_runner",
        media_id=f"m_{index}",
        media_type="IMAGE",
        media_url=f"https://example.com/{index}.jpg",
        caption_text=caption_text,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
        core_metrics=CoreMetrics(
            reach=2000 + index,
            impressions=2400 + index,
            likes=120 + index,
            comments=20 + index,
            saves=30,
            shares=10,
            profile_visits=6,
            website_taps=1,
        ),
        derived_metrics=DerivedMetrics(
            engagement_rate=0.08,
            save_rate=0.02,
            share_rate=0.01,
        ),
        benchmark_metrics=BenchmarkMetrics(account_avg_engagement_rate=0.06),
    )
    return post.model_dump(mode="json")


def _post_route_available(client: TestClient) -> bool:
    schema = client.get("/openapi.json")
    if schema.status_code != 200:
        return False
    paths = schema.json().get("paths", {})
    return isinstance(paths, dict) and "/api/post-analysis" in paths


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def require_post_route(client: TestClient) -> None:
    if not _post_route_available(client):
        pytest.skip("Skipping post-analysis anti-gravity tests: /api/post-analysis route not registered.")


@pytest.fixture
def patch_post_external_calls(monkeypatch: pytest.MonkeyPatch):
    ai_analysis_service._ANALYSIS_CACHE.clear()

    async def _vision_ok(_post):  # noqa: ANN001
        return {
            "provider": "gemini",
            "status": "ok",
            "signals": [
                {
                    "objects": ["person", "phone"],
                    "dominant_focus": "person",
                    "scene_description": "A creator speaking to camera.",
                    "visual_style": "clean",
                    "hook_strength_score": 0.8,
                    "subject_clarity": 8.0,
                    "aesthetic_quality": 8.0,
                }
            ],
        }

    valid_s5_json = json.dumps(
        {
            "summary": "Deterministic analysis summary.",
            "drivers": [
                {
                    "id": "driver_1",
                    "label": "Clear framing",
                    "type": "POSITIVE",
                    "explanation": "Composition is stable and readable.",
                }
            ],
            "recommendations": [
                {"id": "rec_1", "text": "Keep opening hook concise.", "impact_level": "LOW"}
            ],
            "engagement_potential_score": {
                "emotional_resonance": 5,
                "shareability": 5,
                "save_worthiness": 5,
                "comment_potential": 5,
                "novelty_or_value": 5,
                "total": 25,
                "notes": ["deterministic"],
            },
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )

    async def _llm_valid(_prompt, _llm_client):  # noqa: ANN001
        return valid_s5_json

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", _vision_ok)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", _llm_valid)
    yield
    ai_analysis_service._ANALYSIS_CACHE.clear()


def test_post_schema_lock(
    client: TestClient,
    require_post_route: None,
    patch_post_external_calls: None,
) -> None:
    response = client.post("/api/post-analysis", json=_post_payload())
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == EXPECTED_POST_TOP_LEVEL_KEYS
    assert set(payload["scores"].keys()) == EXPECTED_POST_SCORE_KEYS


def test_post_determinism_same_input(
    client: TestClient,
    require_post_route: None,
    patch_post_external_calls: None,
) -> None:
    request_payload = _post_payload()
    first = client.post("/api/post-analysis", json=request_payload)
    second = client.post("/api/post-analysis", json=request_payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


def test_post_vision_disabled_visible(
    client: TestClient,
    require_post_route: None,
    patch_post_external_calls: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post("/api/post-analysis", json=_post_payload())
    assert response.status_code == 200
    payload = response.json()
    warning_codes = {warning.get("code") for warning in payload.get("warnings", []) if isinstance(warning, dict)}
    assert "GEMINI_API_KEY_MISSING" in warning_codes
    assert payload["quality"]["vision_enabled"] is False
    assert payload["vision"]["status"] in {"disabled", "error"}


def test_post_media_url_failure_no_500(
    client: TestClient,
    require_post_route: None,
    patch_post_external_calls: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")

    async def _vision_error(_post):  # noqa: ANN001
        return {"provider": "gemini", "status": "error", "signals": []}

    async def _llm_malformed(_prompt, _llm_client):  # noqa: ANN001
        return "{malformed json"

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", _vision_error)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", _llm_malformed)

    response = client.post("/api/post-analysis", json=_post_payload(media_url="https://example.com/404.jpg"))
    assert response.status_code != 500
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert "S1" in payload["scores"]
    assert "S3" in payload["scores"]
    assert payload["quality"]["ai_fallback_used"] is True


def test_account_dedupe_storm(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    deferred_queue = _DeferredQueue()
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: deferred_queue)
    monkeypatch.setattr(account_analysis_jobs, "ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR", 999)

    client = TestClient(app)
    payload = {"account_id": "acct_runner_storm", "post_limit": 12}
    responses = [client.post("/api/account-analysis", json=payload) for _ in range(5)]

    assert all(response.status_code == 200 for response in responses)
    job_ids = {response.json()["job_id"] for response in responses}
    assert len(job_ids) == 1


def test_account_rate_limit_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    deferred_queue = _DeferredQueue()
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: deferred_queue)
    monkeypatch.setattr(account_analysis_jobs, "ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR", 3)

    client = TestClient(app)
    first = client.post("/api/account-analysis", json={"account_id": "acct_runner_rate", "post_limit": 5})
    second = client.post("/api/account-analysis", json={"account_id": "acct_runner_rate", "post_limit": 6})
    third = client.post("/api/account-analysis", json={"account_id": "acct_runner_rate", "post_limit": 7})
    fourth = client.post("/api/account-analysis", json={"account_id": "acct_runner_rate", "post_limit": 8})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert fourth.status_code == 429
    assert len(deferred_queue.calls) == 3


def test_poll_unknown_job_clean_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)

    client = TestClient(app)
    response = client.get(f"/api/account-analysis/{uuid4()}")
    assert response.status_code != 500
    assert response.status_code in {404, 400}


def test_posts_summary_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)

    client = TestClient(app)
    job_id = "job_bloat_summary"
    account_analysis_jobs._write_status(
        job_id,
        {
            "job_id": job_id,
            "status": "succeeded",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "progress": {"stage": "aggregate", "done": 40, "total": 40},
            "error": None,
            "warnings": [],
            "quality": {"vision_enabled": True, "vision_error_count": 0, "ai_fallback_count": 0},
            "result": {
                "ahs_score": 70.0,
                "ahs_band": "STRONG",
                "posts_summary": [
                    {
                        "post_id": f"p_{idx}",
                        "caption_preview": "x" * 300,
                        "vision": {"status": "ok", "signals": [{"objects": ["person"]}]},
                    }
                    for idx in range(40)
                ],
            },
        },
    )

    response = client.get(f"/api/account-analysis/{job_id}")
    assert response.status_code == 200
    payload = response.json()
    posts_summary = payload["result"]["posts_summary"]
    assert len(posts_summary) <= 30
    assert all(len(item.get("caption_preview", "")) <= 120 for item in posts_summary)
    assert all("signals" not in json.dumps(item, ensure_ascii=True) for item in posts_summary)


def test_quality_flags_correctness(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: _ImmediateQueue())

    client = TestClient(app)
    posts = [_build_post_dict(i) for i in range(3)]

    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")
    enabled_resp = client.post(
        "/api/account-analysis",
        json={"account_id": "acct_quality_enabled", "post_limit": 3, "posts": posts},
    )
    assert enabled_resp.status_code == 200
    enabled_job_id = enabled_resp.json()["job_id"]
    enabled_status = client.get(f"/api/account-analysis/{enabled_job_id}")
    assert enabled_status.status_code == 200
    enabled_payload = enabled_status.json()
    assert enabled_payload["quality"]["vision_enabled"] is True
    assert enabled_payload["quality"]["vision_error_count"] == 0

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    disabled_resp = client.post(
        "/api/account-analysis",
        json={"account_id": "acct_quality_disabled", "post_limit": 3, "posts": posts},
    )
    assert disabled_resp.status_code == 200
    disabled_job_id = disabled_resp.json()["job_id"]
    disabled_status = client.get(f"/api/account-analysis/{disabled_job_id}")
    assert disabled_status.status_code == 200
    disabled_payload = disabled_status.json()
    assert disabled_payload["quality"]["vision_enabled"] is False
    warning_codes = {
        warning.get("code")
        for warning in disabled_payload.get("warnings", [])
        if isinstance(warning, dict)
    }
    assert "GEMINI_API_KEY_MISSING" in warning_codes
