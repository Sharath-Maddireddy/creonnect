"""Regression tests for gRPC single-post analysis startup."""

from __future__ import annotations

from typing import Any

import pytest

from backend.app.api import grpc_analysis_server
from backend.app.api import post_analysis_routes


@pytest.mark.asyncio
async def test_start_single_post_handler_falls_back_inline_when_enqueue_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _enqueue_fails(_payload: dict[str, Any]) -> dict[str, str]:
        raise RuntimeError("queue unavailable")

    async def _inline_succeeds(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": f"inline_{payload['post_id']}",
            "status": "succeeded",
            "mode": "inline_fallback",
            "result": {"status": "succeeded"},
        }

    monkeypatch.setattr(grpc_analysis_server, "enqueue_single_post_analysis_job_async", _enqueue_fails)
    monkeypatch.setattr(grpc_analysis_server, "run_single_post_analysis_inline", _inline_succeeds)

    response = await grpc_analysis_server._start_single_post_handler(
        {
            "post_id": "post_1",
            "media_url": "https://example.com/post.jpg",
            "post_type": "IMAGE",
        }
    )

    assert response == {
        "ok": True,
        "data": {
            "job_id": "inline_post_1",
            "status": "succeeded",
            "mode": "inline_fallback",
            "result": {"status": "succeeded"},
        },
    }


@pytest.mark.asyncio
async def test_rest_single_post_analysis_returns_503_when_enqueue_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _enqueue_fails(_payload: dict[str, Any]) -> dict[str, str]:
        raise RuntimeError("queue unavailable")

    async def _inline_must_not_run(_payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("REST queue failure must not run expensive analysis inline")

    monkeypatch.setattr(post_analysis_routes, "enqueue_single_post_analysis_job_async", _enqueue_fails)
    monkeypatch.setattr(post_analysis_routes, "run_single_post_analysis_inline", _inline_must_not_run)

    with pytest.raises(post_analysis_routes.HTTPException) as exc_info:
        await post_analysis_routes.enqueue_single_post_analysis(
            post_analysis_routes.PostAnalysisRequest(
                post_id="post_1",
                media_url="https://example.com/post.jpg",
                post_type="IMAGE",
            ),
            current_user=post_analysis_routes.AuthenticatedInstagramUser(id="acct_1"),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Analysis queue is temporarily unavailable. Please try again shortly."


@pytest.mark.asyncio
async def test_rest_single_post_analysis_stamps_the_authenticated_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _enqueue(payload: dict[str, Any]) -> dict[str, str]:
        captured.update(payload)
        return {"job_id": "job_1", "status": "queued"}

    monkeypatch.setattr(post_analysis_routes, "enqueue_single_post_analysis_job_async", _enqueue)
    response = await post_analysis_routes.enqueue_single_post_analysis(
        post_analysis_routes.PostAnalysisRequest(post_id="post_1", media_url="https://example.com/post.jpg"),
        current_user=post_analysis_routes.AuthenticatedInstagramUser(id="acct_1"),
    )

    assert response == {"job_id": "job_1", "status": "queued"}
    assert captured["account_id"] == "acct_1"
    assert captured["creator_id"] == "acct_1"


def test_single_post_job_status_is_owner_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        post_analysis_routes,
        "get_single_post_analysis_job_status",
        lambda _job_id: {"job_id": "job_1", "account_id": "acct_1", "status": "queued"},
    )

    with pytest.raises(post_analysis_routes.HTTPException) as exc_info:
        post_analysis_routes.get_single_post_analysis_status(
            "job_1",
            current_user=post_analysis_routes.AuthenticatedInstagramUser(id="acct_2"),
        )

    assert exc_info.value.status_code == 404
