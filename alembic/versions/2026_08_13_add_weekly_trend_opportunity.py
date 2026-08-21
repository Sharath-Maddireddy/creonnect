"""Store the generated weekly trend opportunity.

Revision ID: 20260813_weekly_trend
Revises: 20260803_trend_dismiss
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260813_weekly_trend"
down_revision = "20260803_trend_dismiss"
branch_labels = None
depends_on = None


def _column_exists(column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        column.get("name") == column_name
        for column in inspector.get_columns("creator_trend_results")
    )


def upgrade() -> None:
    # Application startup previously added this column as a compatibility
    # measure, so tolerate databases where it already exists.
    if _column_exists("weekly_opportunity_json"):
        return
    json_type = sa.JSON().with_variant(
        postgresql.JSONB(astext_type=sa.Text()),
        "postgresql",
    )
    op.add_column(
        "creator_trend_results",
        sa.Column("weekly_opportunity_json", json_type, nullable=True),
    )


def downgrade() -> None:
    if _column_exists("weekly_opportunity_json"):
        op.drop_column("creator_trend_results", "weekly_opportunity_json")
