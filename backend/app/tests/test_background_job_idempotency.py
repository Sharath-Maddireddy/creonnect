from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.domain.image_editor_models import CreatorImageGenerationSelection
from backend.app.infra import job_state_store
from backend.app.infra.models import BackgroundJob
from backend.app.services.creator_image_editor_job_service import create_creator_image_job


def _job_sessionmaker(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    BackgroundJob.__table__.create(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_concurrent_creator_requests_create_one_billable_job(tmp_path, monkeypatch) -> None:
    engine, sessions = _job_sessionmaker(tmp_path)
    monkeypatch.setattr(job_state_store, "get_sync_sessionmaker", lambda: sessions)
    barrier = Barrier(2)
    selection = CreatorImageGenerationSelection(goal_id="post", style_id="lofi_dusk")

    def create_job():
        barrier.wait()
        return create_creator_image_job(
            account_id="account-1",
            source_asset_id="asset-1",
            selection=selection,
            idempotency_key="same-request",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_job(), range(2)))

    assert sorted(created for _job, created in results) == [False, True]
    assert len({job["job_id"] for job, _created in results}) == 1
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(BackgroundJob)) == 1
    engine.dispose()


def test_creator_failure_keeps_original_idempotency_claim(tmp_path, monkeypatch) -> None:
    engine, sessions = _job_sessionmaker(tmp_path)
    monkeypatch.setattr(job_state_store, "get_sync_sessionmaker", lambda: sessions)
    selection = CreatorImageGenerationSelection(goal_id="post", style_id="lofi_dusk")

    first, first_created = create_creator_image_job(
        account_id="account-1",
        source_asset_id="asset-1",
        selection=selection,
        idempotency_key="permanent-request-key",
    )
    job_state_store.update_job_state(first["job_id"], status="failed")
    duplicate, duplicate_created = create_creator_image_job(
        account_id="account-1",
        source_asset_id="asset-2",
        selection=selection,
        idempotency_key="permanent-request-key",
    )

    assert first_created is True
    assert duplicate_created is False
    assert duplicate["job_id"] == first["job_id"]
    assert duplicate["status"] == "failed"
    engine.dispose()
