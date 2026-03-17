"""Tests for account-analysis enqueue rate-limit behavior around reusable jobs."""

from __future__ import annotations

from typing import Any

from backend.app.services import account_analysis_jobs


class _QueueStub:
    def __init__(self, assert_ready: callable) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self._assert_ready = assert_ready

    def enqueue(self, *args: Any, **kwargs: Any) -> None:
        self._assert_ready()
        self.calls.append((args, kwargs))


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
