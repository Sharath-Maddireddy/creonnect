"""Regression coverage for the background-job idempotency migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "2026_08_13_add_background_job_idempotency_key.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("background_job_idempotency_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_idempotency_migration_backfills_one_claim_per_key(monkeypatch) -> None:
    migration = _load_migration()
    assert migration.revision == "20260813_job_idempotency"
    assert migration.down_revision == "20260813_weekly_trend"

    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("""
            CREATE TABLE background_jobs (
                job_id TEXT PRIMARY KEY,
                queue_name TEXT NOT NULL,
                account_id TEXT,
                payload_hash TEXT,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        connection.execute(sa.text("""
            INSERT INTO background_jobs
                (job_id, queue_name, account_id, payload_hash, status, created_at)
            VALUES
                ('creator-old', 'creator-image-editor', 'a1', 'same', 'failed', '2026-01-01'),
                ('creator-new', 'creator-image-editor', 'a1', 'same', 'succeeded', '2026-01-02'),
                ('filter-old', 'image-editor-filters', 'a1', 'filter', 'succeeded', '2026-01-01'),
                ('filter-new', 'image-editor-filters', 'a1', 'filter', 'started', '2026-01-02')
        """))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))

        migration.upgrade()
        migration.upgrade()
        claims = dict(connection.execute(sa.text(
            "SELECT job_id, idempotency_key_hash FROM background_jobs"
        )).all())
        assert claims == {
            "creator-old": "same",
            "creator-new": None,
            "filter-old": None,
            "filter-new": "filter",
        }

        with pytest.raises(IntegrityError):
            connection.execute(sa.text("""
                INSERT INTO background_jobs
                    (job_id, queue_name, account_id, payload_hash, idempotency_key_hash, status, created_at)
                VALUES ('duplicate', 'creator-image-editor', 'a1', 'same', 'same', 'queued', '2026-01-03')
            """))

    # Use a clean transaction because SQLite marks the prior one failed after
    # the deliberate unique-index violation.
    with engine.begin() as connection:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.downgrade()
        migration.downgrade()
        columns = {str(column["name"]) for column in sa.inspect(connection).get_columns("background_jobs")}
        assert "idempotency_key_hash" not in columns
