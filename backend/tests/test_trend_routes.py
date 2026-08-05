import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.app.domain.trend_models import (
    CreatorNiche,
    GlobalTrend,
    TrendAnalysisResult,
    TrendRecommendation,
)

from backend.app.api import trend_routes
from backend.app.services.creator_trend_service import TrendDataUnavailableError


def _build_sample_result() -> TrendAnalysisResult:
    niche = CreatorNiche(primary_category="Fitness", sub_niches=["HIIT"], confidence_score=0.95)
    trends = [
        GlobalTrend(
            topic_name="Short HIIT Series",
            trend_type="format",
            momentum="rising",
            description="Short, high-intensity clips are trending",
        )
    ]
    recs = [
        TrendRecommendation(
            suggested_title="5-min HIIT to Start Your Day",
            rationale="Fits creator niche and current format momentum",
            expected_impact="Higher discovery",
        )
    ]
    return TrendAnalysisResult(niche=niche, global_trends=trends, recommendations=recs)


@pytest.mark.asyncio
async def test_get_trends_returns_stored():
    sample = _build_sample_result()

    # Mock DB row with JSON attributes
    row = MagicMock()
    row.niche_json = sample.niche.model_dump(mode="python")
    row.global_trends_json = [t.model_dump(mode="python") for t in sample.global_trends]
    row.recommendations_json = [r.model_dump(mode="python") for r in sample.recommendations]
    row.weekly_opportunity_json = {"score": 88, "label": "High", "idea_count": 1, "summary_reason": "Stored", "bullets": ["Stored bullet"]}
    row.dismissed_content_opportunities_json = []

    db = AsyncMock()
    db.get = AsyncMock(return_value=row)

    res = await trend_routes.get_trends("acct1", db=db)

    assert isinstance(res, TrendAnalysisResult)
    assert res.niche.primary_category == "Fitness"
    assert len(res.global_trends) == 1
    assert res.weekly_opportunity is not None
    assert res.weekly_opportunity.score == 88


@pytest.mark.asyncio
async def test_refresh_trends_rate_limited_queues_background_work(monkeypatch):
    monkeypatch.setenv("TREND_REFRESH_RATE_LIMIT", "1")
    monkeypatch.setattr(trend_routes, "aincr_with_expire", AsyncMock(return_value=2))  # rate count > 1
    monkeypatch.setattr(
        trend_routes,
        "enqueue_trend_analysis_job",
        lambda _account_id: MagicMock(id="trend-analysis:acct-rate:1"),
    )

    db = AsyncMock()
    result = await trend_routes.refresh_trends("acct-rate", db=db)
    assert result == {"status": "queued", "job_id": "trend-analysis:acct-rate:1"}


@pytest.mark.asyncio
async def test_refresh_trends_upserts(monkeypatch):
    sample = _build_sample_result()

    # Rate limit passes
    monkeypatch.setattr(trend_routes, "aincr_with_expire", AsyncMock(return_value=1))
    monkeypatch.setattr(trend_routes.TrendAnalysisCache, "aget", AsyncMock(return_value=None))
    monkeypatch.setattr(trend_routes.TrendAnalysisCache, "aset", AsyncMock(return_value=None))

    # load history returns empty posts and basic account_data
    fake_ctx = MagicMock()
    fake_ctx.historical_posts = []
    fake_ctx.account_data = {"bio": "bio", "username": "uname"}
    monkeypatch.setattr(trend_routes, "load_draft_history_context", lambda account_id: fake_ctx)

    # Mock generate_creator_intelligence to avoid calling actual AI
    monkeypatch.setattr(trend_routes, "generate_creator_intelligence", AsyncMock(return_value=MagicMock()))

    # Patch CreatorTrendService.get_trends_and_recommendations
    async def fake_get_trends_and_recommendations(*args, **kwargs):
        return sample

    fake_service = MagicMock()
    fake_service.get_trends_and_recommendations = AsyncMock(side_effect=fake_get_trends_and_recommendations)
    monkeypatch.setattr(trend_routes, "CreatorTrendService", lambda: fake_service)

    # DB: no existing row
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.commit = AsyncMock()

    res = await trend_routes.refresh_trends("acct-upsert", db=db)

    assert isinstance(res, TrendAnalysisResult)
    db.add.assert_called()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_refresh_trends_uses_cache(monkeypatch):
    sample = _build_sample_result()

    monkeypatch.setattr(trend_routes, "aincr_with_expire", AsyncMock(return_value=1))
    fake_ctx = MagicMock()
    fake_ctx.historical_posts = []
    fake_ctx.account_data = {"bio": "bio", "username": "uname"}
    monkeypatch.setattr(trend_routes, "load_draft_history_context", lambda account_id: fake_ctx)
    monkeypatch.setattr(trend_routes.TrendAnalysisCache, "aget", AsyncMock(return_value=sample))

    fake_service = MagicMock()
    fake_service.get_trends_and_recommendations = AsyncMock(side_effect=AssertionError("service should not be called"))
    monkeypatch.setattr(trend_routes, "CreatorTrendService", lambda: fake_service)

    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.commit = AsyncMock()

    result = await trend_routes.refresh_trends("acct-cache", db=db)

    assert isinstance(result, TrendAnalysisResult)
    assert result.niche.primary_category == "Fitness"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_refresh_trends_returns_503_when_trends_unavailable(monkeypatch):
    monkeypatch.setattr(trend_routes, "aincr_with_expire", AsyncMock(return_value=1))
    monkeypatch.setattr(trend_routes.TrendAnalysisCache, "aget", AsyncMock(return_value=None))

    fake_ctx = MagicMock()
    fake_ctx.historical_posts = []
    fake_ctx.account_data = {"bio": "bio", "username": "uname"}
    monkeypatch.setattr(trend_routes, "load_draft_history_context", lambda account_id: fake_ctx)
    monkeypatch.setattr(trend_routes, "generate_creator_intelligence", AsyncMock(return_value=MagicMock()))

    fake_service = MagicMock()
    fake_service.get_trends_and_recommendations = AsyncMock(side_effect=TrendDataUnavailableError("Global trends unavailable"))
    monkeypatch.setattr(trend_routes, "CreatorTrendService", lambda: fake_service)

    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await trend_routes.refresh_trends("acct-unavailable", db=db)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Global trends unavailable"


@pytest.mark.asyncio
async def test_get_trend_topics_returns_detailed_rows(monkeypatch):
    sample = _build_sample_result()
    sample.global_trends[0].audience_match_pct = 91

    db = AsyncMock()
    monkeypatch.setattr(trend_routes, "_get_trends_inner", AsyncMock(return_value=sample))

    res = await trend_routes.get_trend_topics("acct1", db=db)

    assert res["total"] == 1
    assert res["topics"][0]["topic_name"] == "Short HIIT Series"
    assert res["topics"][0]["audience_match_pct"] == 91
    assert "why_it_fits" in res["topics"][0]
    assert res["topics"][0]["growth_pct"] == 30


def test_normalize_trend_result_filters_legacy_audio_rows():
    payload = _build_sample_result().model_dump(mode="python")
    payload["global_trends"].append(
        GlobalTrend(
            topic_name="Unverified Sound",
            trend_type="audio",
            momentum="rising",
            description="Legacy audio-shaped trend",
        ).model_dump(mode="python")
    )

    normalized = trend_routes._normalize_trend_result(payload)

    assert all(trend.trend_type != "audio" for trend in normalized.global_trends)


@pytest.mark.asyncio
async def test_get_trend_topics_applies_filters_and_sort(monkeypatch):
    sample = _build_sample_result()
    sample.global_trends = [
        GlobalTrend(
            topic_name="Alpha Topic",
            trend_type="topic",
            momentum="rising",
            description="A rising topic",
            audience_match_pct=70,
        ),
        GlobalTrend(
            topic_name="Beta Format",
            trend_type="format",
            momentum="peaking",
            description="A peaking format",
            audience_match_pct=91,
        ),
    ]
    sample.recommendations = [
        TrendRecommendation(suggested_title="Alpha Idea", rationale="Alpha fit", expected_impact="Good", trend_reference="Alpha Topic"),
        TrendRecommendation(suggested_title="Beta Idea", rationale="Beta fit", expected_impact="Great", trend_reference="Beta Format"),
    ]

    db = AsyncMock()
    monkeypatch.setattr(trend_routes, "_get_trends_inner", AsyncMock(return_value=sample))

    res = await trend_routes.get_trend_topics(
        "acct1",
        trend_type="format",
        sort_by="audience_match",
        sort_dir="desc",
        db=db,
    )

    assert res["total"] == 1
    assert res["topics"][0]["topic_name"] == "Beta Format"
