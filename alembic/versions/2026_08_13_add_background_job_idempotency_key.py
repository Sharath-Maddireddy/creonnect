"""Add an atomic idempotency claim to background jobs.

Revision ID: 20260813_job_idempotency
Revises: 20260813_weekly_trend
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260813_job_idempotency"
down_revision = "20260813_weekly_trend"
branch_labels = None
depends_on = None


_INDEX_NAME = "uq_background_jobs_idempotency_key"


def _column_exists(column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        column.get("name") == column_name
        for column in inspector.get_columns("background_jobs")
    )


def _index_exists(index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        index.get("name") == index_name
        for index in inspector.get_indexes("background_jobs")
    )


def _backfill_existing_claims() -> None:
    # Preserve existing explicit creator idempotency keys. If historical races
    # created duplicates, the oldest/original job owns the key.
    op.execute(
        sa.text(
            """
            UPDATE background_jobs
            SET idempotency_key_hash = payload_hash
            WHERE job_id IN (
                SELECT job_id FROM (
                    SELECT job_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY queue_name, account_id, payload_hash
                               ORDER BY created_at ASC, job_id ASC
                           ) AS claim_order
                    FROM background_jobs
                    WHERE queue_name = 'creator-image-editor'
                      AND account_id IS NOT NULL
                      AND payload_hash IS NOT NULL
                ) ranked
                WHERE claim_order = 1
            )
            """
        )
    )

    # Deterministic filters may retry after failure. Claim only reusable work,
    # preferring the newest job to match the previous lookup behavior.
    op.execute(
        sa.text(
            """
            UPDATE background_jobs
            SET idempotency_key_hash = payload_hash
            WHERE job_id IN (
                SELECT job_id FROM (
                    SELECT job_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY queue_name, account_id, payload_hash
                               ORDER BY created_at DESC, job_id DESC
                           ) AS claim_order
                    FROM background_jobs
                    WHERE queue_name = 'image-editor-filters'
                      AND account_id IS NOT NULL
                      AND payload_hash IS NOT NULL
                      AND status IN ('queued', 'started', 'processing', 'succeeded')
                ) ranked
                WHERE claim_order = 1
            )
            """
        )
    )


def upgrade() -> None:
    if not _column_exists("idempotency_key_hash"):
        op.add_column(
            "background_jobs",
            sa.Column("idempotency_key_hash", sa.Text(), nullable=True),
        )
    _backfill_existing_claims()
    if not _index_exists(_INDEX_NAME):
        op.create_index(
            _INDEX_NAME,
            "background_jobs",
            ["queue_name", "account_id", "idempotency_key_hash"],
            unique=True,
        )


def downgrade() -> None:
    if _index_exists(_INDEX_NAME):
        op.drop_index(_INDEX_NAME, table_name="background_jobs")
    if _column_exists("idempotency_key_hash"):
        op.drop_column("background_jobs", "idempotency_key_hash")
