"""Create persisted GPT Image and Gemini edit comparisons.

Revision ID: 20260814_imgcmp
Revises: 20260814_post_score_history
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_imgcmp"
down_revision: Union[str, None] = "20260814_post_score_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("image_edit_comparisons"):
        return
    op.create_table(
        "image_edit_comparisons",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("original_asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gpt_result_asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("gemini_result_asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("filter_id", sa.Text(), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("gpt_metrics_json", sa.JSON(), nullable=False),
        sa.Column("gemini_metrics_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_image_edit_comparisons_account_id", "image_edit_comparisons", ["account_id"])
    op.create_index("ix_image_edit_comparisons_original_asset_id", "image_edit_comparisons", ["original_asset_id"])
    op.create_index("ix_image_edit_comparisons_request_hash", "image_edit_comparisons", ["request_hash"])
    op.create_index("ix_image_edit_comparisons_created_at", "image_edit_comparisons", ["created_at"])


def downgrade() -> None:
    op.drop_table("image_edit_comparisons")
