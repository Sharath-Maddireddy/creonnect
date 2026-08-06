"""Tests for disconnect-driven account-analysis Redis invalidation."""

from __future__ import annotations

import asyncio

import fakeredis
import pytest

import backend.app.infra.redis_client as redis_client
from backend.app.api import grpc_analysis_server
from backend.app.services import account_analysis_jobs


def test_invalidation_removes_reusable_account_analysis_state(monkeypatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)

    account_id = "acct_disconnect"
    first_job_id = "job_first"
    second_job_id = "job_second"
    fake_redis.set(
        f"{account_analysis_jobs.ACCOUNT_ANALYSIS_DEDUPE_KEY_PREFIX}{account_id}:30",
        '{"job_id":"job_first"}',
    )
    fake_redis.set(
        f"{account_analysis_jobs.ACCOUNT_ANALYSIS_INPUTHASH_KEY_PREFIX}{account_id}:hash_one",
        first_job_id,
    )
    fake_redis.set(
        f"{account_analysis_jobs.ACCOUNT_ANALYSIS_INPUTHASH_KEY_PREFIX}{account_id}:hash_two",
        second_job_id,
    )
    fake_redis.set(f"{account_analysis_jobs.ACCOUNT_ANALYSIS_JOB_KEY_PREFIX}{first_job_id}", "{}")
    fake_redis.set(f"{account_analysis_jobs.ACCOUNT_ANALYSIS_JOB_KEY_PREFIX}{second_job_id}", "{}")
    fake_redis.set(f"{account_analysis_jobs.ACCOUNT_ANALYSIS_RATE_KEY_PREFIX}{account_id}", "2")
    fake_redis.set("account_analysis:dedupe:another_account:30", '{"job_id":"keep_me"}')

    result = account_analysis_jobs.invalidate_account_analysis_cache(account_id)

    assert result["account_id"] == account_id
    assert result["analysis_generation"] == 1
    assert result["invalidated_job_ids"] == [first_job_id, second_job_id]
    assert result["deleted_keys"] == 6
    assert list(fake_redis.scan_iter(match=f"account_analysis:dedupe:{account_id}:*")) == []
    assert list(fake_redis.scan_iter(match=f"account_analysis:inputhash:{account_id}:*")) == []
    assert fake_redis.get(f"account_analysis:rate:{account_id}") is None
    assert fake_redis.get(f"account_analysis:generation:{account_id}") == "1"
    assert fake_redis.get("account_analysis:dedupe:another_account:30") is not None


def test_old_generation_cannot_be_reused_after_invalidation(monkeypatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)

    account_id = "acct_generation"
    account_analysis_jobs._write_dedupe_job_id(account_id, 30, "job_old", 0)
    account_analysis_jobs._write_inputhash_job_id(account_id, "hash_same", "job_old", 0)

    result = account_analysis_jobs.invalidate_account_analysis_cache(account_id)

    # Simulate a pre-disconnect worker racing and writing after invalidation.
    account_analysis_jobs._write_dedupe_job_id(account_id, 30, "job_old", 0)
    account_analysis_jobs._write_inputhash_job_id(account_id, "hash_same", "job_old", 0)
    assert account_analysis_jobs._read_dedupe_job_id(account_id, 30) is None
    assert account_analysis_jobs._read_inputhash_job_id(account_id, "hash_same") is None

    account_analysis_jobs._write_dedupe_job_id(account_id, 30, "job_new", result["analysis_generation"])
    account_analysis_jobs._write_inputhash_job_id(
        account_id,
        "hash_same",
        "job_new",
        result["analysis_generation"],
    )
    assert account_analysis_jobs._read_dedupe_job_id(account_id, 30) == "job_new"
    assert account_analysis_jobs._read_inputhash_job_id(account_id, "hash_same") == "job_new"


def test_request_captured_before_disconnect_is_not_enqueued(monkeypatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    account_id = "acct_request_race"
    account_analysis_jobs.invalidate_account_analysis_cache(account_id)

    with pytest.raises(ValueError, match="invalidated by a disconnect"):
        account_analysis_jobs._enqueue_account_analysis_job_impl(
            {"account_id": account_id, "post_limit": 30},
            sanitized_payload={"account_id": account_id, "posts": []},
            requested_analysis_generation=0,
        )


def test_queued_pre_disconnect_worker_cannot_recreate_status(monkeypatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(account_analysis_jobs, "get_current_job", lambda: None)
    account_id = "acct_queued_race"
    account_analysis_jobs.invalidate_account_analysis_cache(account_id)

    account_analysis_jobs.run_account_analysis_job(
        {
            "job_id": "job_before_disconnect",
            "account_id": account_id,
            "analysis_generation": 0,
            "posts": [],
        }
    )

    assert fake_redis.get("account_analysis:job:job_before_disconnect") is None
    assert account_analysis_jobs._read_dedupe_job_id(account_id, 30) is None


def test_grpc_invalidation_requires_account_id() -> None:
    response = asyncio.run(grpc_analysis_server._invalidate_account_handler({}))

    assert response == {"ok": False, "error": {"message": "account_id is required"}}


def test_grpc_invalidation_forwards_canonical_account_id(monkeypatch) -> None:
    received: list[str] = []

    def _fake_invalidate(account_id: str) -> dict[str, object]:
        received.append(account_id)
        return {"account_id": account_id, "analysis_generation": 2, "deleted_keys": 4}

    monkeypatch.setattr(grpc_analysis_server, "invalidate_account_analysis_cache", _fake_invalidate)

    response = asyncio.run(
        grpc_analysis_server._invalidate_account_handler({"account_id": "instagram123"})
    )

    assert received == ["instagram123"]
    assert response == {
        "ok": True,
        "data": {"account_id": "instagram123", "analysis_generation": 2, "deleted_keys": 4},
    }
