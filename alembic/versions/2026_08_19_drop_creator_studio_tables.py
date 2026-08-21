"""Drop Creator Studio tables. The feature has been removed in favor of the
single-image Creator Image Editor.

Revision ID: 20260819_drop_studio
Revises: 20260816_studio_presets
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260819_drop_studio"
down_revision: Union[str, None] = "20260816_studio_presets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Children first, to respect foreign-key dependencies.
_TABLES_IN_DROP_ORDER = (
    "creator_studio_preset_previews",
    "creator_studio_export_bundles",
    "creator_studio_culling_flags",
    "creator_studio_signature_grades",
    "creator_studio_shoot_files",
    "creator_studio_shoots",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name in _TABLES_IN_DROP_ORDER:
        if inspector.has_table(table_name):
            op.drop_table(table_name)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("creator_studio_shoots"):
        op.create_table(
            "creator_studio_shoots",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("account_id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
            sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_creator_studio_shoots_account_id", "creator_studio_shoots", ["account_id"])
        op.create_index("ix_creator_studio_shoots_created_at", "creator_studio_shoots", ["created_at"])

    if not inspector.has_table("creator_studio_shoot_files"):
        op.create_table(
            "creator_studio_shoot_files",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("shoot_id", sa.Text(), sa.ForeignKey("creator_studio_shoots.id", ondelete="CASCADE"), nullable=False),
            sa.Column("asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("review_status", sa.Text(), nullable=False, server_default="pending"),
            sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("analysis_json", sa.JSON(), nullable=True),
            sa.Column("edit_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("shoot_id", "asset_id", name="uq_creator_studio_shoot_file_asset"),
        )
        op.create_index("ix_creator_studio_shoot_files_shoot_id", "creator_studio_shoot_files", ["shoot_id"])
        op.create_index("ix_creator_studio_shoot_files_asset_id", "creator_studio_shoot_files", ["asset_id"])

    if not inspector.has_table("creator_studio_culling_flags"):
        op.create_table(
            "creator_studio_culling_flags",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column(
                "shoot_file_id", sa.Text(),
                sa.ForeignKey("creator_studio_shoot_files.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("flag_type", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("shoot_file_id", "flag_type", name="uq_creator_studio_culling_flag_type"),
        )
        op.create_index(
            "ix_creator_studio_culling_flags_shoot_file_id", "creator_studio_culling_flags", ["shoot_file_id"]
        )

    if not inspector.has_table("creator_studio_signature_grades"):
        op.create_table(
            "creator_studio_signature_grades",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("account_id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("preset_id", sa.Text(), nullable=True),
            sa.Column("preset_version", sa.Text(), nullable=True),
            sa.Column("adjustments_json", sa.JSON(), nullable=False),
            sa.Column("fine_tuning_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("account_id", "name", "version", name="uq_creator_studio_signature_grade_version"),
        )
        op.create_index(
            "ix_creator_studio_signature_grades_account_id", "creator_studio_signature_grades", ["account_id"]
        )

    if not inspector.has_table("creator_studio_export_bundles"):
        op.create_table(
            "creator_studio_export_bundles",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("account_id", sa.Text(), nullable=False),
            sa.Column("shoot_id", sa.Text(), sa.ForeignKey("creator_studio_shoots.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="pending_enqueue"),
            sa.Column("platform_profiles_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("request_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("result_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_creator_studio_export_bundles_account_id", "creator_studio_export_bundles", ["account_id"])
        op.create_index("ix_creator_studio_export_bundles_shoot_id", "creator_studio_export_bundles", ["shoot_id"])

    if not inspector.has_table("creator_studio_preset_previews"):
        op.create_table(
            "creator_studio_preset_previews",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("account_id", sa.Text(), nullable=False),
            sa.Column(
                "shoot_file_id", sa.Text(),
                sa.ForeignKey("creator_studio_shoot_files.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("asset_id", sa.Text(), sa.ForeignKey("image_assets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("preset_id", sa.Text(), nullable=False),
            sa.Column("preset_version", sa.Text(), nullable=False),
            sa.Column("adjustments_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_creator_studio_preset_previews_account_id", "creator_studio_preset_previews", ["account_id"]
        )
        op.create_index(
            "ix_creator_studio_preset_previews_shoot_file_id", "creator_studio_preset_previews", ["shoot_file_id"]
        )
