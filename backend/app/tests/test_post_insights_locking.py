"""Tests for post insights orchestration lock lifecycle behavior."""

from __future__ import annotations

import pytest

from services import post_insights


class _DummyCacheRepo:
    def __init__(self) -> None:
        self.released: list[tuple[str, str]] = []
        self.cached_payloads: list[tuple[str, str, dict]] = []

    def get_cached_analysis(self, account_id: str, media_id: str) -> dict | None:
        return None

    def acquire_regen_lock(self, account_id: str, media_id: str) -> bool:
        return True

    def set_cached_analysis(self, account_id: str, media_id: str, payload: dict) -> None:
        self.cached_payloads.append((account_id, media_id, payload))

    def release_regen_lock(self, account_id: str, media_id: str) -> None:
        self.released.append((account_id, media_id))


def _post_metadata() -> dict:
    return {
        "account_id": "acct_1",
        "media_id": "media_1",
    }


def test_generate_post_insights_releases_lock_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    cache_repo = _DummyCacheRepo()
    monkeypatch.setattr(post_insights, "_cache_repo", cache_repo)
    monkeypatch.setattr(post_insights, "compute_post_signals", lambda **kwargs: {"signal": 1})
    monkeypatch.setattr(
        post_insights,
        "generate_post_ai_analysis",
        lambda **kwargs: {
            "status": "READY",
            "summary": "ok",
            "drivers": [],
            "recommendations": [],
        },
    )

    result = post_insights.generate_post_insights(
        post_metadata=_post_metadata(),
        metrics={},
        benchmarks={},
        reach_breakdown={},
        tier_name="gold",
    )

    assert result["ai_analysis"]["status"] == "READY"
    assert cache_repo.released == [("acct_1", "media_1")]
    assert len(cache_repo.cached_payloads) == 1


def test_generate_post_insights_releases_lock_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    cache_repo = _DummyCacheRepo()
    monkeypatch.setattr(post_insights, "_cache_repo", cache_repo)
    monkeypatch.setattr(post_insights, "compute_post_signals", lambda **kwargs: {"signal": 1})

    def _raise_ai(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("ai failure")

    monkeypatch.setattr(post_insights, "generate_post_ai_analysis", _raise_ai)

    with pytest.raises(RuntimeError, match="ai failure"):
        post_insights.generate_post_insights(
            post_metadata=_post_metadata(),
            metrics={},
            benchmarks={},
            reach_breakdown={},
            tier_name="gold",
        )

    assert cache_repo.released == [("acct_1", "media_1")]


def test_generate_post_insights_preserves_empty_reach_breakdown(monkeypatch: pytest.MonkeyPatch) -> None:
    cache_repo = _DummyCacheRepo()
    captured: dict[str, object] = {}

    monkeypatch.setattr(post_insights, "_cache_repo", cache_repo)

    def _capture_signals(**kwargs):  # type: ignore[no-untyped-def]
        captured["reach_breakdown"] = kwargs.get("reach_breakdown")
        return {"signal": 1}

    monkeypatch.setattr(post_insights, "compute_post_signals", _capture_signals)
    monkeypatch.setattr(
        post_insights,
        "generate_post_ai_analysis",
        lambda **kwargs: {
            "status": "ERROR",
            "summary": "",
            "drivers": [],
            "recommendations": [],
        },
    )

    post_insights.generate_post_insights(
        post_metadata=_post_metadata(),
        metrics={},
        benchmarks={},
        reach_breakdown={},
        tier_name="gold",
    )

    assert captured["reach_breakdown"] == {}
