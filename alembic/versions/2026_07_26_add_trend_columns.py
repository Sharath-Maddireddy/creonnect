"""add content_gaps_json daily_insights_json opportunity_bullets_json to creator_trend_results

Revision ID: 20260726_add_trend_columns
Revises: 20260619_create_creator_trend_results
Create Date: 2026-07-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260726_add_trend_columns'
down_revision = '20260619_create_creator_trend_results'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'creator_trend_results',
        sa.Column('content_gaps_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'creator_trend_results',
        sa.Column('daily_insights_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'creator_trend_results',
        sa.Column('opportunity_bullets_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('creator_trend_results', 'opportunity_bullets_json')
    op.drop_column('creator_trend_results', 'daily_insights_json')
    op.drop_column('creator_trend_results', 'content_gaps_json')
