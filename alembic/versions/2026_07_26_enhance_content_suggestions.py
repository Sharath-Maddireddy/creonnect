"""Enhance content suggestions tables with PRD fields

Revision ID: 20260726_cse
Revises: 20260726_csc
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '20260726_cse'
down_revision: Union[str, None] = '20260726_csc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        f"SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        f"WHERE table_name = '{table_name}' AND column_name = '{column_name}')"
    ))
    return result.scalar()


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"
    ))
    return result.scalar()


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        f"SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = '{index_name}')"
    ))
    return result.scalar()


def _constraint_exists(constraint_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        f"SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}')"
    ))
    return result.scalar()


def upgrade() -> None:
    # ── Create idea_scripts table if not exists ──
    if not _table_exists('idea_scripts'):
        op.create_table(
            'idea_scripts',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('idea_id', sa.String(36), sa.ForeignKey('ideas.id', ondelete='CASCADE'), nullable=False),
            sa.Column('script_type', sa.String(50), nullable=False),
            sa.Column('tone', sa.String(50), nullable=True),
            sa.Column('language', sa.String(50), nullable=True),
            sa.Column('content', sa.Text, nullable=True),
            sa.Column('scenes', JSONB, nullable=True),
            sa.Column('estimated_duration', sa.Integer, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_idea_scripts_idea_id', 'idea_scripts', ['idea_id'])

    # ── Create idea_captions table if not exists ──
    if not _table_exists('idea_captions'):
        op.create_table(
            'idea_captions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('idea_id', sa.String(36), sa.ForeignKey('ideas.id', ondelete='CASCADE'), nullable=False),
            sa.Column('tone', sa.String(50), nullable=True),
            sa.Column('language', sa.String(50), nullable=True),
            sa.Column('content', sa.Text, nullable=True),
            sa.Column('character_count', sa.Integer, nullable=True),
            sa.Column('hashtag_count', sa.Integer, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_idea_captions_idea_id', 'idea_captions', ['idea_id'])

    # ── ideas table: add missing columns ──
    ideas_columns = [
        ('parent_idea_id', sa.String(36), None, None),
        ('content_type', sa.String(50), None, 'reel'),
        ('opportunity_score', sa.Float, None, None),
        ('expected_reach_min', sa.Integer, None, None),
        ('expected_reach_max', sa.Integer, None, None),
        ('expected_views_min', sa.Integer, None, None),
        ('expected_views_max', sa.Integer, None, None),
        ('expected_saves_min', sa.Integer, None, None),
        ('expected_saves_max', sa.Integer, None, None),
        ('expected_shares_min', sa.Integer, None, None),
        ('expected_shares_max', sa.Integer, None, None),
        ('difficulty', sa.String(20), None, None),
        ('duration_seconds', sa.Integer, None, None),
        ('best_time_to_post', sa.String(100), None, None),
        ('trend_reference', sa.Text, None, None),
        ('tags', JSONB, None, '[]'),
        ('generation_job_id', sa.String(36), None, None),
    ]
    for col_name, col_type, _fk_unused, default in ideas_columns:
        if not _column_exists('ideas', col_name):
            kwargs = {}
            if default is not None:
                kwargs['server_default'] = sa.text(f"'{default}'") if isinstance(default, str) else default
            op.add_column('ideas', sa.Column(col_name, col_type, **kwargs))

    # Add foreign keys separately (after columns exist)
    if _column_exists('ideas', 'parent_idea_id'):
        conn = op.get_bind()
        fk_exists = conn.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ideas_parent_idea_id')"
        )).scalar()
        if not fk_exists:
            op.create_foreign_key('fk_ideas_parent_idea_id', 'ideas', 'ideas', ['parent_idea_id'], ['id'], ondelete='SET NULL')

    if _column_exists('ideas', 'generation_job_id'):
        conn = op.get_bind()
        fk_exists = conn.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ideas_generation_job_id')"
        )).scalar()
        if not fk_exists:
            op.create_foreign_key('fk_ideas_generation_job_id', 'ideas', 'idea_generation_jobs', ['generation_job_id'], ['id'], ondelete='SET NULL')

    # Indexes for new columns
    for idx_col in ['content_type', 'opportunity_score', 'parent_idea_id', 'generation_job_id']:
        idx_name = f'ix_ideas_{idx_col}'
        if not _index_exists(idx_name):
            op.create_index(idx_name, 'ideas', [idx_col])

    # ── scheduled_items: add date/time/notes/status columns + unique constraint ──
    if not _column_exists('scheduled_items', 'scheduled_date'):
        op.add_column('scheduled_items', sa.Column('scheduled_date', sa.Date, nullable=True))
    if not _column_exists('scheduled_items', 'scheduled_time'):
        op.add_column('scheduled_items', sa.Column('scheduled_time', sa.Time, nullable=True))
    if not _column_exists('scheduled_items', 'notes'):
        op.add_column('scheduled_items', sa.Column('notes', sa.Text, nullable=True))
    if not _column_exists('scheduled_items', 'status'):
        op.add_column('scheduled_items', sa.Column('status', sa.String(50), nullable=False, server_default='scheduled'))

    # Populate scheduled_date/scheduled_time from scheduled_at for existing rows
    op.execute(sa.text("""
        UPDATE scheduled_items
        SET scheduled_date = scheduled_at::date,
            scheduled_time = scheduled_at::time
        WHERE scheduled_date IS NULL AND scheduled_at IS NOT NULL
    """))

    # Unique constraint: one idea per account per date+time slot
    if not _constraint_exists('uq_scheduled_items_account_datetime'):
        op.create_unique_constraint(
            'uq_scheduled_items_account_datetime',
            'scheduled_items',
            ['account_id', 'scheduled_date', 'scheduled_time'],
        )

    # ── idea_generation_jobs: add missing columns ──
    if not _column_exists('idea_generation_jobs', 'total_requested'):
        op.add_column('idea_generation_jobs', sa.Column('total_requested', sa.Integer, nullable=False, server_default='20'))
    if not _column_exists('idea_generation_jobs', 'total_generated'):
        op.add_column('idea_generation_jobs', sa.Column('total_generated', sa.Integer, nullable=False, server_default='0'))
    if not _column_exists('idea_generation_jobs', 'started_at'):
        op.add_column('idea_generation_jobs', sa.Column('started_at', sa.DateTime, nullable=True))


def downgrade() -> None:
    # idea_generation_jobs
    for col in ['started_at', 'total_generated', 'total_requested']:
        if _column_exists('idea_generation_jobs', col):
            op.drop_column('idea_generation_jobs', col)

    # scheduled_items
    if _constraint_exists('uq_scheduled_items_account_datetime'):
        op.drop_constraint('uq_scheduled_items_account_datetime', 'scheduled_items')
    for col in ['status', 'notes', 'scheduled_time', 'scheduled_date']:
        if _column_exists('scheduled_items', col):
            op.drop_column('scheduled_items', col)

    # ideas
    ideas_cols_to_drop = [
        'generation_job_id', 'tags', 'trend_reference', 'best_time_to_post',
        'duration_seconds', 'difficulty', 'expected_shares_max', 'expected_shares_min',
        'expected_saves_max', 'expected_saves_min', 'expected_views_max', 'expected_views_min',
        'expected_reach_max', 'expected_reach_min', 'opportunity_score', 'content_type',
        'parent_idea_id',
    ]
    for col in ideas_cols_to_drop:
        if _column_exists('ideas', col):
            idx_name = f'ix_ideas_{col}'
            if _index_exists(idx_name):
                op.drop_index(idx_name)
            op.drop_column('ideas', col)

    # Drop foreign keys
    for fk_name in ['fk_ideas_generation_job_id', 'fk_ideas_parent_idea_id']:
        conn = op.get_bind()
        exists = conn.execute(sa.text(
            f"SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{fk_name}')"
        )).scalar()
        if exists:
            op.drop_constraint(fk_name, 'ideas')

    # Drop tables
    if _table_exists('idea_captions'):
        op.drop_index('ix_idea_captions_idea_id')
        op.drop_table('idea_captions')
    if _table_exists('idea_scripts'):
        op.drop_index('ix_idea_scripts_idea_id')
        op.drop_table('idea_scripts')
