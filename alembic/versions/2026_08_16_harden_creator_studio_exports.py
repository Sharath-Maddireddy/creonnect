"""Add recoverable Creator Studio export request payloads.

Revision ID: 20260816_studio_hardening
Revises: 20260816_creator_studio
Create Date: 2026-08-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260816_studio_hardening"
down_revision: Union[str, None] = "20260816_creator_studio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("creator_studio_export_bundles")}
    if "request_json" not in columns:
        op.add_column(
            "creator_studio_export_bundles",
            sa.Column("request_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("creator_studio_export_bundles")}
    if "request_json" in columns:
        op.drop_column("creator_studio_export_bundles", "request_json")
