import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.domain.trend_models import (
    CreatorNiche,
    GlobalTrend,
    TrendAnalysisResult,
    TrendRecommendation,
)

from backend.app.api import trend_routes


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

    db = AsyncMock()
    db.get = AsyncMock(return_value=row)

    res = await trend_routes.get_trends("acct1", db=db, current_user=MagicMock())

    assert isinstance(res, TrendAnalysisResult)
    assert res.niche.primary_category == "Fitness"
    assert len(res.global_trends) == 1


@pytest.mark.asyncio
async def test_refresh_trends_rate_limited(monkeypatch):
    # make aincr_with_expire return >1
    monkeypatch.setattr(trend_routes, "aincr_with_expire", AsyncMock(return_value=2))

    db = AsyncMock()
    with pytest.raises(Exception) as excinfo:
        await trend_routes.refresh_trends("acct-rate", db=db, current_user=MagicMock())
    assert "Rate limit" in str(excinfo.value)


@pytest.mark.asyncio
async def test_refresh_trends_upserts(monkeypatch):
    sample = _build_sample_result()

    # Rate limit passes
    monkeypatch.setattr(trend_routes, "aincr_with_expire", AsyncMock(return_value=1))

    # load history returns empty posts and basic account_data
    fake_ctx = MagicMock()
    fake_ctx.historical_posts = []
    fake_ctx.account_data = {"bio": "bio", "username": "uname"}
    monkeypatch.setattr(trend_routes, "load_draft_history_context", lambda account_id: fake_ctx)

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

    res = await trend_routes.refresh_trends("acct-upsert", db=db, current_user=MagicMock())

    assert isinstance(res, TrendAnalysisResult)
    db.add.assert_called()
    db.commit.assert_awaited()
