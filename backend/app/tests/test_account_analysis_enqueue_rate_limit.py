"""Tests for account-analysis enqueue rate-limit behavior around reusable jobs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from backend.app.services import account_analysis_jobs
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights


class _QueueStub:
    def __init__(self, assert_ready: callable) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self._assert_ready = assert_ready

    def enqueue(self, *args: Any, **kwargs: Any) -> None:
        self._assert_ready()
        self.calls.append((args, kwargs))


def _build_post(index: int) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_secure",
        media_id=f"m_{index}",
        media_type="IMAGE",
        caption_text="Deterministic caption",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(
            reach=1000 + index,
            impressions=1100 + index,
            likes=120,
            comments=10,
            saves=5,
            shares=2,
            profile_visits=1,
            website_taps=0,
        ),
        derived_metrics=DerivedMetrics(
            engagement_rate=0.08,
            save_rate=0.01,
            share_rate=0.005,
        ),
        benchmark_metrics=BenchmarkMetrics(account_avg_engagement_rate=0.06),
    )


def test_reusable_job_bypasses_rate_limit(monkeypatch) -> None:
    calls = {"rate_limit_calls": 0}

    def _fake_resolve_reusable_job(account_id: str, post_limit: int, payload_hash: str | None) -> tuple[str, str]:
        assert account_id == "acct_reuse"
        assert post_limit == 7
        assert payload_hash is None
        return "job_existing", "queued"

    def _fake_enforce_rate_limit(account_id: str, running_job_id: str | None) -> None:
        calls["rate_limit_calls"] += 1

    monkeypatch.setattr(account_analysis_jobs, "_resolve_reusable_job", _fake_resolve_reusable_job)
    monkeypatch.setattr(account_analysis_jobs, "_enforce_rate_limit", _fake_enforce_rate_limit)

    payload = {"account_id": "acct_reuse", "post_limit": 7}
    result = account_analysis_jobs.enqueue_account_analysis_job(payload)

    assert result == {"job_id": "job_existing", "status": "queued"}
    assert calls["rate_limit_calls"] == 0


def test_new_job_enforces_rate_limit_before_enqueue(monkeypatch) -> None:
    calls = {"rate_limit_calls": 0, "rate_checked": False}

    def _fake_resolve_reusable_job(account_id: str, post_limit: int, payload_hash: str | None) -> tuple[None, None]:
        assert account_id == "acct_new"
        assert post_limit == 5
        assert payload_hash is None
        return None, None

    def _fake_enforce_rate_limit(account_id: str, running_job_id: str | None) -> None:
        assert account_id == "acct_new"
        assert running_job_id is None
        calls["rate_limit_calls"] += 1
        calls["rate_checked"] = True

    def _assert_rate_checked() -> None:
        assert calls["rate_checked"] is True

    queue = _QueueStub(assert_ready=_assert_rate_checked)
    monkeypatch.setattr(account_analysis_jobs, "_resolve_reusable_job", _fake_resolve_reusable_job)
    monkeypatch.setattr(account_analysis_jobs, "_enforce_rate_limit", _fake_enforce_rate_limit)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: queue)
    monkeypatch.setattr(account_analysis_jobs, "initialize_job_status", lambda _job_id: {"job_id": _job_id})
    monkeypatch.setattr(account_analysis_jobs, "_write_dedupe_job_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "_write_inputhash_job_id", lambda *args, **kwargs: None)

    payload = {"account_id": "acct_new", "post_limit": 5}
    result = account_analysis_jobs.enqueue_account_analysis_job(payload)

    assert result["status"] == "queued"
    assert calls["rate_limit_calls"] == 1
    assert len(queue.calls) == 1


def test_access_token_is_not_enqueued_in_job_payload(monkeypatch) -> None:
    def _assert_ready() -> None:
        return None

    async def _fake_fetch_instagram_media(access_token: str, limit: int = 30) -> list[dict[str, str]]:
        assert access_token == "secret-token"
        assert limit == 5
        return [{"id": "m_1"}]

    def _fake_map_instagram_posts(raw_media: list[dict[str, str]]) -> list[SinglePostInsights]:
        assert raw_media == [{"id": "m_1"}]
        return [_build_post(1)]

    queue = _QueueStub(assert_ready=_assert_ready)
    monkeypatch.setattr(account_analysis_jobs, "_resolve_reusable_job", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(account_analysis_jobs, "_enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: queue)
    monkeypatch.setattr(account_analysis_jobs, "initialize_job_status", lambda _job_id: {"job_id": _job_id})
    monkeypatch.setattr(account_analysis_jobs, "_write_dedupe_job_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "_write_inputhash_job_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "fetch_instagram_media", _fake_fetch_instagram_media)
    monkeypatch.setattr(account_analysis_jobs, "map_instagram_posts", _fake_map_instagram_posts)

    payload = {"account_id": "acct_secure", "post_limit": 5, "access_token": "secret-token"}
    result = account_analysis_jobs.enqueue_account_analysis_job(payload)

    assert result["status"] == "queued"
    assert len(queue.calls) == 1
    enqueue_args, _enqueue_kwargs = queue.calls[0]
    queued_payload = enqueue_args[1]
    assert "access_token" not in queued_payload
    assert queued_payload["account_id"] == "acct_secure"
    assert queued_payload["post_limit"] == 5
    assert isinstance(queued_payload.get("posts"), list)
    assert len(queued_payload["posts"]) == 1


def test_access_token_materialization_works_inside_running_event_loop(monkeypatch) -> None:
    async def _fake_fetch_instagram_media(access_token: str, limit: int = 30) -> list[dict[str, str]]:
        assert access_token == "secret-token"
        assert limit == 5
        return [{"id": "m_1"}]

    def _fake_map_instagram_posts(raw_media: list[dict[str, str]]) -> list[SinglePostInsights]:
        assert raw_media == [{"id": "m_1"}]
        return [_build_post(1)]

    monkeypatch.setattr(account_analysis_jobs, "fetch_instagram_media", _fake_fetch_instagram_media)
    monkeypatch.setattr(account_analysis_jobs, "map_instagram_posts", _fake_map_instagram_posts)

    async def _run_inside_loop() -> dict[str, Any]:
        return account_analysis_jobs._materialize_posts_for_enqueue(
            {"account_id": "acct_secure", "access_token": "secret-token"},
            post_limit=5,
        )

    result = asyncio.run(_run_inside_loop())

    assert "access_token" not in result
    assert isinstance(result.get("posts"), list)
    assert len(result["posts"]) == 1


def test_access_token_materialization_wraps_fetch_failures(monkeypatch) -> None:
    async def _failing_fetch_instagram_media(access_token: str, limit: int = 30) -> list[dict[str, str]]:
        raise RuntimeError("instagram api unavailable")

    monkeypatch.setattr(account_analysis_jobs, "fetch_instagram_media", _failing_fetch_instagram_media)

    try:
        account_analysis_jobs._materialize_posts_for_enqueue(
            {"account_id": "acct_secure", "access_token": "secret-token"},
            post_limit=5,
        )
    except ValueError as exc:
        assert str(exc) == "Failed to fetch Instagram media: instagram api unavailable"
    else:
        raise AssertionError("Expected ValueError when Instagram media fetch fails")
