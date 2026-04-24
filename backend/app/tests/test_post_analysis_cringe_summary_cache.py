"""Tests for cringe summary cache behavior in post analysis routes."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from backend.app.api import post_analysis_routes
from backend.app.domain.post_models import CoreMetrics, SinglePostInsights, VisionAnalysis
from backend.app.services import post_snapshot_store


def test_cringe_summary_uses_redis_shared_cache(monkeypatch) -> None:
    shared_store: dict[str, dict] = {}

    def _fake_set_json(key: str, payload: dict, ttl_seconds: int | None = None) -> None:
        assert ttl_seconds == post_analysis_routes.CRINGE_SUMMARY_CACHE_TTL_SECONDS
        shared_store[key] = dict(payload)

    def _fake_get_json(key: str) -> dict | None:
        value = shared_store.get(key)
        return dict(value) if isinstance(value, dict) else None

    monkeypatch.setattr(post_analysis_routes, "set_json", _fake_set_json)
    monkeypatch.setattr(post_analysis_routes, "get_json", _fake_get_json)

    with post_analysis_routes._CRINGE_SUMMARY_CACHE_LOCK:
        post_analysis_routes._CRINGE_SUMMARY_CACHE.clear()

    payload = {"cringe_score": 66, "cringe_label": "cringe"}
    post_analysis_routes._write_cringe_summary("post_1", payload)

    loaded = post_analysis_routes._read_cringe_summary("post_1")
    assert loaded == payload


def test_cringe_summary_falls_back_to_process_cache_on_redis_failure(monkeypatch) -> None:
    def _raise_on_set_json(key: str, payload: dict, ttl_seconds: int | None = None) -> None:
        raise RuntimeError("redis-down")

    def _raise_on_get_json(key: str) -> dict | None:
        raise RuntimeError("redis-down")

    monkeypatch.setattr(post_analysis_routes, "set_json", _raise_on_set_json)
    monkeypatch.setattr(post_analysis_routes, "get_json", _raise_on_get_json)

    with post_analysis_routes._CRINGE_SUMMARY_CACHE_LOCK:
        post_analysis_routes._CRINGE_SUMMARY_CACHE.clear()

    payload = {"cringe_score": 50, "cringe_label": "uncertain"}
    post_analysis_routes._write_cringe_summary("post_fallback", payload)
    loaded = post_analysis_routes._read_cringe_summary("post_fallback")
    assert loaded == payload


def test_cringe_summary_process_cache_expires_stale_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_now = 10_000.0
    monkeypatch.setattr(post_analysis_routes.time, "monotonic", lambda: fake_now)
    monkeypatch.setattr(post_analysis_routes, "set_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("redis-down")))
    monkeypatch.setattr(post_analysis_routes, "get_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("redis-down")))

    with post_analysis_routes._CRINGE_SUMMARY_CACHE_LOCK:
        post_analysis_routes._CRINGE_SUMMARY_CACHE.clear()

    payload = {"cringe_score": 42, "cringe_label": "watch"}
    post_analysis_routes._write_cringe_summary("post_expiring", payload)

    fake_now += post_analysis_routes.CRINGE_SUMMARY_CACHE_TTL_SECONDS + 1
    loaded = post_analysis_routes._read_cringe_summary("post_expiring")

    assert loaded is None
    with post_analysis_routes._CRINGE_SUMMARY_CACHE_LOCK:
        assert "post_expiring" not in post_analysis_routes._CRINGE_SUMMARY_CACHE


def test_cringe_summary_process_cache_evicts_oldest_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(post_analysis_routes.time, "monotonic", lambda: 5_000.0)
    monkeypatch.setattr(post_analysis_routes, "set_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("redis-down")))

    with post_analysis_routes._CRINGE_SUMMARY_CACHE_LOCK:
        post_analysis_routes._CRINGE_SUMMARY_CACHE.clear()

    original_max_entries = post_analysis_routes.CRINGE_SUMMARY_CACHE_MAX_ENTRIES
    monkeypatch.setattr(post_analysis_routes, "CRINGE_SUMMARY_CACHE_MAX_ENTRIES", 2)

    post_analysis_routes._write_cringe_summary("post_1", {"cringe_score": 1})
    post_analysis_routes._write_cringe_summary("post_2", {"cringe_score": 2})
    post_analysis_routes._write_cringe_summary("post_3", {"cringe_score": 3})

    with post_analysis_routes._CRINGE_SUMMARY_CACHE_LOCK:
        assert list(post_analysis_routes._CRINGE_SUMMARY_CACHE.keys()) == ["post_2", "post_3"]
        assert len(post_analysis_routes._CRINGE_SUMMARY_CACHE) == 2
    assert original_max_entries != 2


def test_stable_post_id_avoids_delimiter_collisions() -> None:
    first = post_analysis_routes._stable_post_id(
        media_url="a|b",
        post_type="c",
        caption_text="d",
    )
    second = post_analysis_routes._stable_post_id(
        media_url="a",
        post_type="b|c",
        caption_text="d",
    )
    assert first != second


def test_post_analysis_raises_clear_error_when_pipeline_returns_no_post(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_build_single_post_insights(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"post": None, "ai_analysis": {}}

    monkeypatch.setattr(post_analysis_routes, "build_single_post_insights", _fake_build_single_post_insights)

    request = post_analysis_routes.PostAnalysisRequest(
        post_id="post_missing",
        account_id="acct_1",
        post_type="IMAGE",
        media_url="https://example.com/post.jpg",
        caption_text="Caption",
        likes=1,
        comments=0,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(post_analysis_routes.post_analysis(request))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Analysis pipeline returned no post data."


def test_post_insights_snapshot_uses_redis_shared_cache(monkeypatch) -> None:
    shared_store: dict[str, dict] = {}

    def _fake_set_json(key: str, payload: dict, ttl_seconds: int | None = None) -> None:
        assert ttl_seconds == post_snapshot_store.POST_INSIGHTS_CACHE_TTL_SECONDS
        shared_store[key] = dict(payload)

    def _fake_get_json(key: str) -> dict | None:
        value = shared_store.get(key)
        return dict(value) if isinstance(value, dict) else None

    monkeypatch.setattr(post_snapshot_store, "set_json", _fake_set_json)
    monkeypatch.setattr(post_snapshot_store, "get_json", _fake_get_json)

    with post_snapshot_store._POST_INSIGHTS_CACHE_LOCK:
        post_snapshot_store._POST_INSIGHTS_CACHE.clear()

    post = SinglePostInsights(
        account_id="acct_1",
        media_id="post_1",
        media_url="https://example.com/post.jpg",
        media_type="IMAGE",
        caption_text="Caption",
        core_metrics=CoreMetrics(reach=100, impressions=120, likes=10, comments=2),
    )
    ai_analysis = {"summary": "Strong post", "fallback_used": False}
    post_snapshot_store.write_post_insights_snapshot("post_1", post=post, ai_analysis=ai_analysis)

    loaded = post_snapshot_store.read_post_insights_snapshot("post_1")
    assert loaded == {"post": post.model_dump(mode="json"), "ai_analysis": ai_analysis}


def test_get_post_insights_returns_cached_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    cached_payload = {
        "post": {
            "media_id": "post_123",
            "media_url": "https://example.com/post.jpg",
            "caption_text": "Caption",
            "core_metrics": {"reach": 100},
            "benchmark_metrics": {"reach_percent_vs_avg": 12.0},
        },
        "ai_analysis": {"summary": "Strong hook", "fallback_used": False},
    }

    monkeypatch.setattr(
        post_analysis_routes,
        "read_post_insights_snapshot",
        lambda post_id: cached_payload if post_id == "post_123" else None,
    )

    response = post_analysis_routes.get_post_insights("post_123")
    assert response == {
        "status": "succeeded",
        "post": cached_payload["post"],
        "ai_analysis": cached_payload["ai_analysis"],
    }


def test_get_post_insights_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(post_analysis_routes, "read_post_insights_snapshot", lambda _post_id: None)

    with pytest.raises(HTTPException) as exc_info:
        post_analysis_routes.get_post_insights("missing_post")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Post insights not found for post_id. Run /api/v1/post-analysis for this post first."


def test_vision_payload_preserves_unexpected_post_status_and_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(
        post_analysis_routes.logger,
        "warning",
        lambda message, *args: warnings.append(message % args),
    )
    post = SinglePostInsights(
        account_id="acct_1",
        media_id="post_vision_1",
        vision_analysis=VisionAnalysis(provider="gemini", status="unknown", signals=[]),
    )

    payload = post_analysis_routes._vision_payload(post, ai_analysis={"vision_status": "ok"})

    assert payload["status"] == "unknown"
    assert warnings
    assert "Unexpected post vision status 'unknown'" in warnings[0]
    assert "post_vision_1" in warnings[0]


def test_vision_payload_uses_valid_ai_status_for_cached_payload() -> None:
    post = SinglePostInsights(account_id="acct_1", media_id="post_vision_2")

    payload = post_analysis_routes._vision_payload(
        post,
        ai_analysis={
            "vision_status": "disabled",
            "vision_analysis": {"provider": "gemini", "status": "ok", "signals": []},
        },
    )

    assert payload["status"] == "disabled"


def test_vision_payload_falls_back_to_error_for_invalid_ai_status() -> None:
    post = SinglePostInsights(account_id="acct_1", media_id="post_vision_3")

    payload = post_analysis_routes._vision_payload(
        post,
        ai_analysis={"vision_status": "unexpected", "vision_analysis": {"provider": "gemini", "status": "ok", "signals": []}},
    )

    assert payload["status"] == "error"
