"""Persistence tests for Creator Intelligence reports and follower snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.domain.account_models import AccountHealthMetadata, AccountHealthScore
from backend.app.infra.database import get_sync_engine, reset_database_engines
from backend.app.infra.models import Base
from backend.app.services.creator_intelligence_report_service import build_creator_intelligence_report
from backend.app.services.creator_intelligence_report_store import (
    get_follower_snapshots,
    persist_creator_intelligence_report,
    record_follower_snapshot,
)


@pytest.fixture
def db_setup(tmp_path, monkeypatch):
    db_path = tmp_path / "creator_intelligence.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    reset_database_engines()
    Base.metadata.create_all(bind=get_sync_engine())
    yield
    reset_database_engines()


def test_report_is_immutable_per_analysis_job(db_setup) -> None:
    report = build_creator_intelligence_report(
        AccountHealthScore(metadata=AccountHealthMetadata(post_count_used=3, time_window_days=7))
    )
    persist_creator_intelligence_report(
        analysis_job_id="job_1",
        account_id="account_1",
        report=report,
    )

    changed_report = report.model_copy(update={"report_status": "complete"})
    persist_creator_intelligence_report(
        analysis_job_id="job_1",
        account_id="account_1",
        report=changed_report,
    )

    from backend.app.infra.database import get_sync_sessionmaker
    from backend.app.infra.models import CreatorIntelligenceReportRecord

    with get_sync_sessionmaker()() as session:
        stored = session.get(CreatorIntelligenceReportRecord, "job_1")

    assert stored is not None
    assert stored.report_status == "partial"
    assert stored.report_json["schema_version"] == "1.0"


def test_follower_snapshot_is_deduplicated_per_source_and_day(db_setup) -> None:
    observed_at = datetime(2026, 8, 6, 9, tzinfo=timezone.utc)

    assert record_follower_snapshot(
        account_id="account_1",
        follower_count=1000,
        source="instagram",
        observed_at=observed_at,
    )
    assert not record_follower_snapshot(
        account_id="account_1",
        follower_count=1200,
        source="instagram",
        observed_at=observed_at + timedelta(hours=3),
    )
    assert record_follower_snapshot(
        account_id="account_1",
        follower_count=1200,
        source="instagram",
        observed_at=observed_at + timedelta(days=1),
    )

    snapshots = get_follower_snapshots("account_1")

    assert [snapshot.follower_count for snapshot in snapshots] == [1000, 1200]
