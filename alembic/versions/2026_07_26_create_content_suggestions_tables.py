"""Create content suggestions tables

Revision ID: 20260726_csc
Revises: 20260726_add_trend_columns
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '20260726_csc'
down_revision: Union[str, None] = '20260726_add_trend_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_table_if_not_exists(table_name: str, *columns, **kwargs) -> None:
    """Create table only if it doesn't exist."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"))
    exists = result.scalar()
    if not exists:
        op.create_table(table_name, *columns, **kwargs)


def _create_index_if_not_exists(index_name: str, table_name: str, columns: list) -> None:
    """Create index only if it doesn't exist."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = '{index_name}')"))
    exists = result.scalar()
    if not exists:
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    # Ideas table
    _create_table_if_not_exists(
        'ideas',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(120), nullable=False),
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('platform', sa.String(50), nullable=True),
        sa.Column('hook', sa.Text, nullable=True),
        sa.Column('script', JSONB, nullable=True),
        sa.Column('captions', JSONB, nullable=True),
        sa.Column('variations', JSONB, nullable=True, server_default='[]'),
        sa.Column('engagement_score', sa.Float, nullable=True),
        sa.Column('generation_metadata', JSONB, nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    _create_index_if_not_exists('ix_ideas_account_id', 'ideas', ['account_id'])
    _create_index_if_not_exists('ix_ideas_status', 'ideas', ['status'])
    _create_index_if_not_exists('ix_ideas_created_at', 'ideas', ['created_at'])

    # Collections table
    _create_table_if_not_exists(
        'collections',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(120), nullable=False),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    _create_index_if_not_exists('ix_collections_account_id', 'collections', ['account_id'])

    # Collection-Idea junction table
    _create_table_if_not_exists(
        'collection_ideas',
        sa.Column('collection_id', sa.String(36), sa.ForeignKey('collections.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('idea_id', sa.String(36), sa.ForeignKey('ideas.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('added_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # Scheduled items table
    _create_table_if_not_exists(
        'scheduled_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(120), nullable=False),
        sa.Column('idea_id', sa.String(36), sa.ForeignKey('ideas.id'), nullable=False),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('scheduled_at', sa.DateTime, nullable=False),
        sa.Column('conflict_acknowledged', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    _create_index_if_not_exists('ix_scheduled_items_account_id', 'scheduled_items', ['account_id'])
    _create_index_if_not_exists('ix_scheduled_items_scheduled_at', 'scheduled_items', ['scheduled_at'])

    # Idea generation jobs table
    _create_table_if_not_exists(
        'idea_generation_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(120), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='queued'),
        sa.Column('current_step', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_steps', sa.Integer, nullable=False, server_default='5'),
        sa.Column('step_label', sa.String(255), nullable=True),
        sa.Column('percent_complete', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('optimization_goals', JSONB, nullable=True),
        sa.Column('content_type', sa.String(50), nullable=True),
        sa.Column('topic', sa.String(255), nullable=True),
        sa.Column('audience', sa.String(100), nullable=True),
        sa.Column('tone_of_voice', JSONB, nullable=True),
        sa.Column('result_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )
    _create_index_if_not_exists('ix_idea_generation_jobs_account_id', 'idea_generation_jobs', ['account_id'])
    _create_index_if_not_exists('ix_idea_generation_jobs_status', 'idea_generation_jobs', ['status'])


def downgrade() -> None:
    op.drop_table('idea_generation_jobs')
    op.drop_table('scheduled_items')
    op.drop_table('collection_ideas')
    op.drop_table('collections')
    op.drop_table('ideas')
