"""Add Creator Studio preset provenance and cached previews.

Revision ID: 20260816_studio_presets
Revises: 20260816_studio_hardening
Create Date: 2026-08-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260816_studio_presets"
down_revision: Union[str, None] = "20260816_studio_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    grade_columns = {
        column["name"]
        for column in inspector.get_columns("creator_studio_signature_grades")
    }
    if "preset_id" not in grade_columns:
        op.add_column(
            "creator_studio_signature_grades",
            sa.Column("preset_id", sa.Text(), nullable=True),
        )
    if "preset_version" not in grade_columns:
        op.add_column(
            "creator_studio_signature_grades",
            sa.Column("preset_version", sa.Text(), nullable=True),
        )
    if "fine_tuning_json" not in grade_columns:
        op.add_column(
            "creator_studio_signature_grades",
            sa.Column(
                "fine_tuning_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("creator_studio_preset_previews"):
        op.create_table(
            "creator_studio_preset_previews",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("account_id", sa.Text(), nullable=False),
            sa.Column(
                "shoot_file_id",
                sa.Text(),
                sa.ForeignKey("creator_studio_shoot_files.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "asset_id",
                sa.Text(),
                sa.ForeignKey("image_assets.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("preset_id", sa.Text(), nullable=False),
            sa.Column("preset_version", sa.Text(), nullable=False),
            sa.Column("adjustments_json", sa.JSON(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_creator_studio_preset_previews_account_id",
            "creator_studio_preset_previews",
            ["account_id"],
        )
        op.create_index(
            "ix_creator_studio_preset_previews_shoot_file_id",
            "creator_studio_preset_previews",
            ["shoot_file_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("creator_studio_preset_previews"):
        op.drop_table("creator_studio_preset_previews")

    grade_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("creator_studio_signature_grades")
    }
    for column_name in ("fine_tuning_json", "preset_version", "preset_id"):
        if column_name in grade_columns:
            op.drop_column("creator_studio_signature_grades", column_name)
