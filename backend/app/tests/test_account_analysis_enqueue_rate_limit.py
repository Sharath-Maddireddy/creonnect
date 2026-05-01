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


def test_enqueue_failure_rolls_back_rate_counter_and_mappings(monkeypatch) -> None:
    calls = {
        "initialize": 0,
        "dedupe_writes": 0,
        "inputhash_writes": 0,
        "dedupe_deletes": 0,
        "inputhash_deletes": 0,
        "rate_restores": 0,
    }

    class _FailingQueue:
        def enqueue(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("rq unavailable")

    monkeypatch.setattr(account_analysis_jobs, "_resolve_reusable_job", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(account_analysis_jobs, "_enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: _FailingQueue())
    monkeypatch.setattr(account_analysis_jobs, "initialize_job_status", lambda _job_id: calls.__setitem__("initialize", calls["initialize"] + 1))
    monkeypatch.setattr(account_analysis_jobs, "_write_dedupe_job_id", lambda *args, **kwargs: calls.__setitem__("dedupe_writes", calls["dedupe_writes"] + 1))
    monkeypatch.setattr(account_analysis_jobs, "_write_inputhash_job_id", lambda *args, **kwargs: calls.__setitem__("inputhash_writes", calls["inputhash_writes"] + 1))
    monkeypatch.setattr(account_analysis_jobs, "_delete_dedupe_job_id", lambda *args, **kwargs: calls.__setitem__("dedupe_deletes", calls["dedupe_deletes"] + 1))
    monkeypatch.setattr(
        account_analysis_jobs,
        "_delete_inputhash_job_id",
        lambda _account_id, payload_hash, _job_id: calls.__setitem__(
            "inputhash_deletes",
            calls["inputhash_deletes"] + (1 if payload_hash else 0),
        ),
    )
    monkeypatch.setattr(account_analysis_jobs, "_restore_rate_limit_counter", lambda *args, **kwargs: calls.__setitem__("rate_restores", calls["rate_restores"] + 1))

    try:
        account_analysis_jobs.enqueue_account_analysis_job({"account_id": "acct_new", "post_limit": 5})
    except RuntimeError as exc:
        assert str(exc) == "rq unavailable"
    else:
        raise AssertionError("Expected enqueue failure to be re-raised")

    assert calls["initialize"] == 0
    assert calls["dedupe_writes"] == 0
    assert calls["inputhash_writes"] == 0
    assert calls["dedupe_deletes"] == 1
    assert calls["inputhash_deletes"] == 0
    assert calls["rate_restores"] == 1


def test_creonnect_bd_source_is_materialized_before_enqueue(monkeypatch) -> None:
    def _assert_ready() -> None:
        return None

    async def _fake_materialize_account_source_payload(payload: dict[str, Any], *, post_limit: int) -> dict[str, Any]:
        assert payload["source"] == "creonnect_bd"
        assert payload["connection_id"] == "conn_123"
        assert post_limit == 5
        return {
            "account_id": "acct_secure",
            "post_limit": 5,
            "posts": [_build_post(1).model_dump(mode="python")],
            "source": "creonnect_bd",
            "source_ref": "conn_123",
        }

    queue = _QueueStub(assert_ready=_assert_ready)
    monkeypatch.setattr(account_analysis_jobs, "_resolve_reusable_job", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(account_analysis_jobs, "_enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: queue)
    monkeypatch.setattr(account_analysis_jobs, "initialize_job_status", lambda _job_id: {"job_id": _job_id})
    monkeypatch.setattr(account_analysis_jobs, "_write_dedupe_job_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "_write_inputhash_job_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "materialize_account_source_payload", _fake_materialize_account_source_payload)

    payload = {"source": "creonnect_bd", "connection_id": "conn_123", "post_limit": 5}
    result = account_analysis_jobs.enqueue_account_analysis_job(payload)

    assert result["status"] == "queued"
    assert len(queue.calls) == 1
    enqueue_args, _enqueue_kwargs = queue.calls[0]
    queued_payload = enqueue_args[1]
    assert queued_payload["account_id"] == "acct_secure"
    assert queued_payload["post_limit"] == 5
    assert queued_payload["source"] == "creonnect_bd"
    assert queued_payload["source_ref"] == "conn_123"
    assert isinstance(queued_payload.get("posts"), list)
    assert len(queued_payload["posts"]) == 1


def test_source_materialization_requires_async_helper_inside_running_event_loop(monkeypatch) -> None:
    async def _fake_materialize_account_source_payload(payload: dict[str, Any], *, post_limit: int) -> dict[str, Any]:
        assert payload["source"] == "creonnect_bd"
        assert payload["connection_id"] == "conn_123"
        assert post_limit == 5
        return {
            "account_id": "acct_secure",
            "post_limit": 5,
            "posts": [_build_post(1).model_dump(mode="python")],
            "source": "creonnect_bd",
        }

    monkeypatch.setattr(account_analysis_jobs, "materialize_account_source_payload", _fake_materialize_account_source_payload)

    async def _run_sync_inside_loop() -> None:
        account_analysis_jobs._materialize_posts_for_enqueue(
            {"source": "creonnect_bd", "connection_id": "conn_123"},
            post_limit=5,
        )

    async def _run_async_inside_loop() -> dict[str, Any]:
        return await account_analysis_jobs._materialize_posts_for_enqueue_async(
            {"source": "creonnect_bd", "connection_id": "conn_123"},
            post_limit=5,
        )

    try:
        asyncio.run(_run_sync_inside_loop())
    except ValueError as exc:
        assert "cannot be used from a running event loop" in str(exc)
    else:
        raise AssertionError("Expected ValueError when sync materialization runs inside an event loop")

    result = asyncio.run(_run_async_inside_loop())
    assert result["source"] == "creonnect_bd"
    assert isinstance(result.get("posts"), list)
    assert len(result["posts"]) == 1


def test_async_enqueue_materializes_creonnect_bd_source(monkeypatch) -> None:
    def _assert_ready() -> None:
        return None

    async def _fake_materialize_account_source_payload(payload: dict[str, Any], *, post_limit: int) -> dict[str, Any]:
        assert payload["source"] == "creonnect_bd"
        assert payload["connection_id"] == "conn_123"
        assert post_limit == 5
        return {
            "account_id": "acct_secure",
            "post_limit": 5,
            "posts": [_build_post(1).model_dump(mode="python")],
            "source": "creonnect_bd",
            "source_ref": "conn_123",
        }

    queue = _QueueStub(assert_ready=_assert_ready)
    monkeypatch.setattr(account_analysis_jobs, "_resolve_reusable_job", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(account_analysis_jobs, "_enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "get_queue", lambda: queue)
    monkeypatch.setattr(account_analysis_jobs, "initialize_job_status", lambda _job_id: {"job_id": _job_id})
    monkeypatch.setattr(account_analysis_jobs, "_write_dedupe_job_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "_write_inputhash_job_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(account_analysis_jobs, "materialize_account_source_payload", _fake_materialize_account_source_payload)

    payload = {"source": "creonnect_bd", "connection_id": "conn_123", "post_limit": 5}
    result = asyncio.run(account_analysis_jobs.enqueue_account_analysis_job_async(payload))

    assert result["status"] == "queued"
    assert len(queue.calls) == 1
    enqueue_args, _enqueue_kwargs = queue.calls[0]
    queued_payload = enqueue_args[1]
    assert queued_payload["account_id"] == "acct_secure"
    assert queued_payload["post_limit"] == 5
    assert queued_payload["source"] == "creonnect_bd"
    assert queued_payload["source_ref"] == "conn_123"
    assert isinstance(queued_payload.get("posts"), list)
    assert len(queued_payload["posts"]) == 1


def test_source_materialization_wraps_failures(monkeypatch) -> None:
    async def _failing_materialize_account_source_payload(payload: dict[str, Any], *, post_limit: int) -> dict[str, Any]:
        raise RuntimeError("creonnect-bd unavailable")

    monkeypatch.setattr(account_analysis_jobs, "materialize_account_source_payload", _failing_materialize_account_source_payload)

    try:
        account_analysis_jobs._materialize_posts_for_enqueue(
            {"source": "creonnect_bd", "connection_id": "conn_123"},
            post_limit=5,
        )
    except ValueError as exc:
        assert str(exc) == "Failed to materialize account source payload: creonnect-bd unavailable"
    else:
        raise AssertionError("Expected ValueError when source materialization fails")
