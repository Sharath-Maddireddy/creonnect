"""Store per-account dismissed trend opportunities.

Revision ID: 20260803_trend_dismiss
Revises: 20260731_imgedit
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260803_trend_dismiss"
down_revision = "20260731_imgedit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "creator_trend_results",
        sa.Column("dismissed_content_opportunities_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("creator_trend_results", "dismissed_content_opportunities_json")
