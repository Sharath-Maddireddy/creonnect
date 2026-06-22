"""create creator_trend_results table

Revision ID: 20260619_create_creator_trend_results
Revises: 
Create Date: 2026-06-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260619_create_creator_trend_results'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'creator_trend_results',
        sa.Column('account_id', sa.Text(), primary_key=True),
        sa.Column('niche_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('global_trends_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('recommendations_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_creator_trend_results_updated_at', 'creator_trend_results', ['updated_at'])


def downgrade() -> None:
    op.drop_index('ix_creator_trend_results_updated_at', table_name='creator_trend_results')
    op.drop_table('creator_trend_results')
