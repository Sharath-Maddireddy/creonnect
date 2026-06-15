from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.app.api.draft_analysis_routes as draft_analysis_routes
from backend.app.domain.draft_models import DraftPostOptimizationResponse, DraftVisualAnalysis
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.services.draft_history_service import DraftHistoryContext


def _build_app() -> TestClient:
    app = FastAPI()
    app.include_router(draft_analysis_routes.router)
    return TestClient(app)


def _history_post() -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_1",
        media_id="m_1",
        media_type="REEL",
        caption_text="Historical caption",
        follower_count=1500,
        core_metrics=CoreMetrics(reach=1200, likes=90, comments=14, shares=7, saves=11),
        derived_metrics=DerivedMetrics(engagement_rate=8.2),
        benchmark_metrics=BenchmarkMetrics(),
    )


def test_draft_optimize_success(monkeypatch) -> None:
    client = _build_app()

    def _fake_load(account_id: str) -> DraftHistoryContext:
        assert account_id == "acct_1"
        return DraftHistoryContext(
            historical_posts=[_history_post()],
            account_data={"account_id": account_id, "username": "creator", "follower_count": 1500},
        )

    async def _fake_optimize_draft_post(**kwargs) -> DraftPostOptimizationResponse:  # noqa: ANN003
        assert kwargs["draft_caption"] == "Draft hook"
        assert kwargs["post_type"] == "REEL"
        return DraftPostOptimizationResponse(
            optimized_caption_options=["Option 1", "Option 2"],
            predicted_reach_band="High",
            optimal_posting_times=["Tuesday 4:00 PM - 6:00 PM"],
            safety_flags=["Avoid repetitive spammy wording"],
            content_format_recommendation="Turn this into a Reel",
            tone_alignment_warning="",
            visual_analysis=DraftVisualAnalysis(
                visual_quality_score=7,
                hook_strength_score=0.65,
                primary_objects=["creator"],
                detected_text="Hello",
                lighting_feedback="A bit dim",
                composition_feedback="Tighten the crop",
                aesthetic_fixes=["Raise exposure"],
                is_cringe=False,
                adult_content_detected=False,
            ),
        )

    monkeypatch.setattr(draft_analysis_routes, "load_draft_history_context", _fake_load)
    monkeypatch.setattr(draft_analysis_routes, "optimize_draft_post", _fake_optimize_draft_post)

    response = client.post(
        "/api/v1/draft-optimize",
        json={
            "account_id": "acct_1",
            "draft_caption": "Draft hook",
            "post_type": "REEL",
            "media_url": "https://example.com/draft.jpg",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_reach_band"] == "High"
    assert payload["visual_analysis"]["visual_quality_score"] == 7


def test_draft_optimize_not_found_without_history(monkeypatch) -> None:
    client = _build_app()

    def _fake_load(_account_id: str) -> DraftHistoryContext:
        return DraftHistoryContext(historical_posts=[], account_data={"account_id": "acct_1"})

    monkeypatch.setattr(draft_analysis_routes, "load_draft_history_context", _fake_load)

    response = client.post(
        "/api/v1/draft-optimize",
        json={"account_id": "acct_1", "draft_caption": "Draft hook", "post_type": "IMAGE"},
    )

    assert response.status_code == 404
    assert "No historical posts found" in response.json()["detail"]

