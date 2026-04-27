"""Tests for Redis + RQ account analysis job orchestration."""

from __future__ import annotations

import json
import concurrent.futures
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import fakeredis
from fastapi.testclient import TestClient

from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
import backend.app.infra.redis_client as redis_client
import backend.app.infra.redis_client as _redis_client_module
from backend.app.services import account_analysis_jobs
from backend.main import app


def _build_post_payload(index: int) -> dict:
    post = SinglePostInsights(
        account_id="acct_queue",
        media_id=f"m_{index}",
        media_type="IMAGE",
        caption_text="How to improve content quality? Save this guide.",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
        core_metrics=CoreMetrics(
            reach=2000 + index,
            impressions=2200 + index,
            likes=120,
            comments=20,
            saves=25,
            shares=15,
            profile_visits=8,
            website_taps=2,
        ),
        derived_metrics=DerivedMetrics(
            engagement_rate=0.08,
            save_rate=0.02,
            share_rate=0.01,
        ),
        benchmark_metrics=BenchmarkMetrics(account_avg_engagement_rate=0.06),
    )
    return post.model_dump(mode="json")


def _build_post_payload_with_caption(index: int, caption_text: str) -> dict:
    payload = _build_post_payload(index)
    payload["caption_text"] = caption_text
    return payload


class _DeferredQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict, dict]] = []

    def enqueue(self, func, payload, **kwargs):  # noqa: ANN001
        self.calls.append((func, payload, kwargs))
        return SimpleNamespace(id=kwargs.get("job_id", "job_deferred"))


class _ImmediateQueue:
    def enqueue(self, func, payload, **kwargs):  # noqa: ANN001
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(func, payload)
            future.result()  # Wait for completion and propagate exceptions
        return SimpleNamespace(id=kwargs.get("job_id", "job_immediate"))


def test_enqueue_returns_job_id_and_writes_queued_status(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    deferred_queue = _DeferredQueue()

    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: deferred_queue)
    monkeypatch.setattr(account_analysis_jobs, "incr_with_expire", lambda key, ttl: 1)
    monkeypatch.setattr(_redis_client_module, "incr_with_expire", lambda key, ttl: 1)

    client = TestClient(app)
    response = client.post("/api/account-analysis", json={"account_id": "acct_queue", "post_limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    job_id = data["job_id"]

    status = account_analysis_jobs.get_account_analysis_job_status(job_id)
    assert status is not None
    assert status["status"] == "queued"
    assert status["progress"] is None

    assert deferred_queue.calls
    _, _, enqueue_kwargs = deferred_queue.calls[0]
    assert "job_timeout" in enqueue_kwargs
    assert "retry" in enqueue_kwargs

    key = f"{account_analysis_jobs.ACCOUNT_ANALYSIS_JOB_KEY_PREFIX}{job_id}"
    assert fake_redis.ttl(key) > 0


def test_job_function_writes_started_then_succeeded(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)

    payload = {
        "job_id": "job_success",
        "account_id": "acct_queue",
        "post_limit": 12,
        "posts": [_build_post_payload(i) for i in range(12)],
        "account_avg_engagement_rate": 0.06,
        "niche_avg_engagement_rate": 0.055,
        "follower_band": "10k-50k",
    }
    account_analysis_jobs.run_account_analysis_job(payload)

    status = account_analysis_jobs.get_account_analysis_job_status("job_success")
    assert status is not None
    assert status["status"] == "succeeded"
    assert status["started_at"] is not None
    assert status["finished_at"] is not None
    assert status["error"] is None
    assert isinstance(status["result"], dict)
    assert "ahs_score" in status["result"]
    assert "pillars" in status["result"]


def test_job_function_failure_writes_failed_status(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)

    payload = {
        "job_id": "job_failed",
        "account_id": "acct_queue",
        "post_limit": 5,
    }
    with pytest.raises(ValueError):
        account_analysis_jobs.run_account_analysis_job(payload)

    status = account_analysis_jobs.get_account_analysis_job_status("job_failed")
    assert status is not None
    assert status["status"] == "failed"
    assert status["error"] is not None
    assert status["error"]["type"] == "ValueError"
    assert status["result"] is None


def test_polling_endpoint_returns_stored_result(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: _ImmediateQueue())
    monkeypatch.setattr(account_analysis_jobs, "incr_with_expire", lambda key, ttl: 1)
    monkeypatch.setattr(_redis_client_module, "incr_with_expire", lambda key, ttl: 1)

    client = TestClient(app)
    response = client.post(
        "/api/account-analysis",
        json={
            "account_id": "acct_queue",
            "post_limit": 10,
            "posts": [_build_post_payload(i) for i in range(10)],
        },
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    poll = client.get(f"/api/account-analysis/{job_id}")
    assert poll.status_code == 200
    payload = poll.json()
    assert payload["status"] == "succeeded"
    assert isinstance(payload["result"], dict)
    assert "metadata" in payload["result"]

    unknown = client.get("/api/account-analysis/unknown-job-id")
    assert unknown.status_code == 404


def test_status_ttl_is_set(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)

    account_analysis_jobs.initialize_job_status("job_ttl")
    key = f"{account_analysis_jobs.ACCOUNT_ANALYSIS_JOB_KEY_PREFIX}job_ttl"
    ttl = fake_redis.ttl(key)
    assert ttl > 0


def test_stale_queued_job_auto_fails_on_poll(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "ACCOUNT_ANALYSIS_QUEUED_STALE_SECONDS", 60)

    job_id = "job_stale_queued"
    payload = account_analysis_jobs.initialize_job_status(job_id)
    payload["created_at"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    account_analysis_jobs._write_status(job_id, payload)

    status = account_analysis_jobs.get_account_analysis_job_status(job_id)
    assert status is not None
    assert status["status"] == "failed"
    assert status["finished_at"] is not None
    assert status["error"]["type"] == "TimeoutError"
    assert "queued" in status["error"]["message"]
    persisted = account_analysis_jobs._read_status(job_id)
    assert persisted is not None
    assert persisted["status"] == "queued"
    assert persisted["finished_at"] is None


def test_stale_started_job_auto_fails_on_poll(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "ACCOUNT_ANALYSIS_STARTED_STALE_SECONDS", 60)

    job_id = "job_stale_started"
    payload = account_analysis_jobs.initialize_job_status(job_id)
    payload["status"] = "started"
    payload["started_at"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    payload["progress"] = {"stage": "fetch", "done": 1, "total": 30}
    account_analysis_jobs._write_status(job_id, payload)

    status = account_analysis_jobs.get_account_analysis_job_status(job_id)
    assert status is not None
    assert status["status"] == "failed"
    assert status["finished_at"] is not None
    assert status["error"]["type"] == "TimeoutError"
    assert "started" in status["error"]["message"]
    persisted = account_analysis_jobs._read_status(job_id)
    assert persisted is not None
    assert persisted["status"] == "started"
    assert persisted["finished_at"] is None


def test_dedupe_returns_same_job_id(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    deferred_queue = _DeferredQueue()
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: deferred_queue)
    monkeypatch.setattr(account_analysis_jobs, "incr_with_expire", lambda key, ttl: 1)

    client = TestClient(app)
    first = client.post("/api/account-analysis", json={"account_id": "acct_dedupe", "post_limit": 12})
    second = client.post("/api/account-analysis", json={"account_id": "acct_dedupe", "post_limit": 12})

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["job_id"] == second_payload["job_id"]
    assert second_payload["status"] == "queued"
    assert len(deferred_queue.calls) == 1


def test_rate_limit_blocks_after_threshold(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: _DeferredQueue())
    monkeypatch.setattr(account_analysis_jobs, "_resolve_reusable_job", lambda *args, **kwargs: (None, None))

    # Mock incr_with_expire to simulate rate limit
    _counts = {}

    def _fake_incr(key, ttl):
        _counts[key] = _counts.get(key, 0) + 1
        return _counts[key]

    monkeypatch.setattr(account_analysis_jobs, "incr_with_expire", _fake_incr)

    payload = {"account_id": "acct_rate", "post_limit": 5}

    # Attempt 1-3 should pass
    account_analysis_jobs.enqueue_account_analysis_job(payload)
    account_analysis_jobs.enqueue_account_analysis_job(payload)
    account_analysis_jobs.enqueue_account_analysis_job(payload)

    # Attempt 4 should fail
    with pytest.raises(account_analysis_jobs.AccountAnalysisRateLimitError):
        account_analysis_jobs.enqueue_account_analysis_job(payload)


def test_failed_job_allows_new_enqueue(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    deferred_queue = _DeferredQueue()
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: deferred_queue)
    monkeypatch.setattr(account_analysis_jobs, "incr_with_expire", lambda key, ttl: 1)

    account_id = "acct_fail_retry"
    payload = {"account_id": account_id, "posts": []}

    # 1. Manually set a failed status for a previous job
    job_id_old = "job_old"
    account_analysis_jobs._update_status(job_id_old, status="failed")
    account_analysis_jobs._write_dedupe_job_id(account_id, 30, job_id_old)

    # 2. Enqueue should NOT reuse the failed job, but create a NEW one
    result = account_analysis_jobs.enqueue_account_analysis_job(payload)
    assert result["job_id"] != job_id_old
    assert result["status"] == "queued"
    assert len(deferred_queue.calls) == 1


def test_inputhash_idempotency_reuses_job(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    deferred_queue = _DeferredQueue()
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: deferred_queue)
    monkeypatch.setattr(account_analysis_jobs, "incr_with_expire", lambda key, ttl: 1)

    posts_payload = [_build_post_payload(i) for i in range(8)]
    client = TestClient(app)
    first = client.post(
        "/api/account-analysis",
        json={"account_id": "acct_hash", "post_limit": 8, "posts": posts_payload},
    )
    second = client.post(
        "/api/account-analysis",
        json={"account_id": "acct_hash", "post_limit": 12, "posts": posts_payload},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["job_id"] == second.json()["job_id"]
    assert len(deferred_queue.calls) == 1


def test_missing_gemini_key_adds_warning(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    payload = {
        "job_id": "job_missing_gemini",
        "account_id": "acct_queue",
        "post_limit": 3,
        "posts": [_build_post_payload(i) for i in range(3)],
    }
    account_analysis_jobs.run_account_analysis_job(payload)

    status = account_analysis_jobs.get_account_analysis_job_status("job_missing_gemini")
    assert status is not None
    assert status["quality"]["vision_enabled"] is False
    warning_codes = {warning.get("code") for warning in status.get("warnings", [])}
    assert "GEMINI_API_KEY_MISSING" in warning_codes


def test_posts_summary_included_when_flag_true(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)

    long_caption = "x" * 200
    payload = {
        "job_id": "job_posts_summary_true",
        "account_id": "acct_queue",
        "post_limit": 7,
        "posts": [_build_post_payload_with_caption(i, long_caption) for i in range(7)],
        "include_posts_summary": True,
        "include_posts_summary_max": 5,
    }
    account_analysis_jobs.run_account_analysis_job(payload)

    status = account_analysis_jobs.get_account_analysis_job_status("job_posts_summary_true")
    assert status is not None
    result = status["result"]
    assert isinstance(result, dict)
    assert "posts_summary" in result
    posts_summary = result["posts_summary"]
    assert isinstance(posts_summary, list)
    assert len(posts_summary) == 5
    assert all(len(item.get("caption_preview", "")) <= 120 for item in posts_summary)
    assert all("signals" not in json.dumps(item) for item in posts_summary)


def test_posts_summary_not_included_by_default(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)

    payload = {
        "job_id": "job_posts_summary_default",
        "account_id": "acct_queue",
        "post_limit": 4,
        "posts": [_build_post_payload(i) for i in range(4)],
    }
    account_analysis_jobs.run_account_analysis_job(payload)

    status = account_analysis_jobs.get_account_analysis_job_status("job_posts_summary_default")
    assert status is not None
    assert "posts_summary" not in status["result"]


def test_posts_summary_determinism(monkeypatch) -> None:
    fake_server = fakeredis.FakeServer()
    fake_redis = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(redis_client, "_redis_client", fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_redis", lambda: fake_redis)

    posts_payload = [_build_post_payload_with_caption(i, f"caption-{i}" * 20) for i in range(7)]
    payload_one = {
        "job_id": "job_posts_summary_det_1",
        "account_id": "acct_queue",
        "post_limit": 7,
        "posts": posts_payload,
        "include_posts_summary": True,
        "include_posts_summary_max": 7,
    }
    payload_two = {
        "job_id": "job_posts_summary_det_2",
        "account_id": "acct_queue",
        "post_limit": 7,
        "posts": posts_payload,
        "include_posts_summary": True,
        "include_posts_summary_max": 7,
    }
    account_analysis_jobs.run_account_analysis_job(payload_one)
    account_analysis_jobs.run_account_analysis_job(payload_two)

    status_one = account_analysis_jobs.get_account_analysis_job_status("job_posts_summary_det_1")
    status_two = account_analysis_jobs.get_account_analysis_job_status("job_posts_summary_det_2")
    assert status_one is not None and status_two is not None
    assert status_one["result"]["posts_summary"] == status_two["result"]["posts_summary"]
