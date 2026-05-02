"""Tests for durable account-analysis result persistence."""

from __future__ import annotations

from datetime import datetime, timezone

import fakeredis
import pytest

import backend.app.infra.redis_client as redis_client
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.infra.database import get_sync_engine, get_sync_sessionmaker, reset_database_engines
from backend.app.infra.models import AccountAnalysisResult, Base
from backend.app.services.account_analysis_jobs import run_account_analysis_job


def _build_post_payload(index: int) -> dict:
    post = SinglePostInsights(
        account_id="acct_persist",
        media_id=f"m_{index}",
        media_type="IMAGE",
        caption_text="Persist this result",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(
            reach=1000 + index,
            impressions=1100 + index,
            likes=120,
            comments=12,
            saves=5,
            shares=2,
        ),
        derived_metrics=DerivedMetrics(engagement_rate=0.08),
        benchmark_metrics=BenchmarkMetrics(account_avg_engagement_rate=0.06),
    )
    return post.model_dump(mode="python")


@pytest.fixture
def db_setup(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis_results.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    reset_database_engines()
    Base.metadata.create_all(bind=get_sync_engine())
    yield
    reset_database_engines()


def test_run_account_analysis_job_persists_result_row(db_setup, monkeypatch) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)

    payload = {
        "job_id": "job_persisted",
        "account_id": "acct_persist",
        "username": "persist_user",
        "post_limit": 2,
        "source": "precomputed",
        "posts": [_build_post_payload(1), _build_post_payload(2)],
    }

    run_account_analysis_job(payload)

    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        row = session.get(AccountAnalysisResult, "job_persisted")

    assert row is not None
    assert row.account_id == "acct_persist"
    assert row.username == "persist_user"
    assert row.source_type == "precomputed"
    assert row.status == "succeeded"
    assert isinstance(row.result_json, dict)
    assert "ahs_score" in row.result_json
