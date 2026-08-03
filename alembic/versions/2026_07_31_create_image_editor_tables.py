"""Create image editor persistence tables

Revision ID: 20260731_imgedit
Revises: 20260726_cse
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260731_imgedit"
down_revision: Union[str, None] = "20260726_cse"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The application startup initializer may have created these tables before
    # Alembic ran. Complete only the schema difference in that case.
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("image_assets"):
        if inspector.has_table("image_edit_requests"):
            columns = {column["name"] for column in inspector.get_columns("image_edit_requests")}
            if "prompt" not in columns:
                op.add_column("image_edit_requests", sa.Column("prompt", sa.Text(), nullable=True))
        return

    op.create_table(
        "image_assets",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("original_asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("is_original", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_image_assets_account_id", "image_assets", ["account_id"])
    op.create_index("ix_image_assets_original_asset_id", "image_assets", ["original_asset_id"])
    op.create_index("ix_image_assets_created_at", "image_assets", ["created_at"])
    op.create_index("ix_image_assets_sha256", "image_assets", ["sha256"])

    op.create_table(
        "image_edit_requests",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("original_asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("config_version", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("style_id", sa.Text(), nullable=False),
        sa.Column("intensity_id", sa.Text(), nullable=False),
        sa.Column("quality_preset_id", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("enabled_control_ids", sa.JSON(), nullable=False),
        sa.Column("output_format", sa.Text(), nullable=True),
        sa.Column("applied_profile_json", sa.JSON(), nullable=True),
        sa.Column("warnings_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_image_edit_requests_account_id", "image_edit_requests", ["account_id"])
    op.create_index("ix_image_edit_requests_original_asset_id", "image_edit_requests", ["original_asset_id"])
    op.create_index("ix_image_edit_requests_request_hash", "image_edit_requests", ["request_hash"])
    op.create_index("ix_image_edit_requests_created_at", "image_edit_requests", ["created_at"])

    op.create_table(
        "image_edit_results",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("request_id", sa.Text(), sa.ForeignKey("image_edit_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result_asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("output_format", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_image_edit_results_request_id", "image_edit_results", ["request_id"])
    op.create_index("ix_image_edit_results_result_asset_id", "image_edit_results", ["result_asset_id"])


def downgrade() -> None:
    op.drop_table("image_edit_results")
    op.drop_table("image_edit_requests")
    op.drop_table("image_assets")
