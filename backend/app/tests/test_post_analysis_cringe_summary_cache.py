"""Tests for cringe summary cache behavior in post analysis routes."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from backend.app.api import post_analysis_routes
from backend.app.domain.post_models import CoreMetrics, SinglePostInsights
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
    assert exc_info.value.detail == "Post insights not found for post_id. Run /api/post-analysis for this post first."
