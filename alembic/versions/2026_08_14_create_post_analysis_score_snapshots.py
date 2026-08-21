"""Create durable score history for single-post analysis.

Revision ID: 20260814_post_score_history
Revises: 20260813_job_idempotency
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_post_score_history"
down_revision = "20260813_job_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "post_analysis_score_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("post_id", sa.Text(), nullable=False),
        sa.Column("contract_version", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_components_json", sa.JSON(), nullable=True),
        sa.Column("confidence_level", sa.Text(), nullable=False),
        sa.Column("source_posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_post_score_snapshots_account_analyzed",
        "post_analysis_score_snapshots",
        ["account_id", "analyzed_at"],
    )
    op.create_index(
        "ix_post_score_snapshots_account_post",
        "post_analysis_score_snapshots",
        ["account_id", "post_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_post_score_snapshots_account_post", table_name="post_analysis_score_snapshots")
    op.drop_index("ix_post_score_snapshots_account_analyzed", table_name="post_analysis_score_snapshots")
    op.drop_table("post_analysis_score_snapshots")
