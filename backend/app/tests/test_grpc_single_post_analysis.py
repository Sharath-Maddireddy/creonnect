"""Regression tests for gRPC single-post analysis startup."""

from __future__ import annotations

from typing import Any

import pytest

from backend.app.api import grpc_analysis_server


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
