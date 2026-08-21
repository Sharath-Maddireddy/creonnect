"""Regression coverage for the weekly trend opportunity migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "2026_08_13_add_weekly_trend_opportunity.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("weekly_trend_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _column_names(connection: sa.Connection) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(connection).get_columns("creator_trend_results")
    }


def test_weekly_opportunity_migration_is_idempotent(monkeypatch) -> None:
    migration = _load_migration()
    assert migration.revision == "20260813_weekly_trend"
    assert migration.down_revision == "20260803_trend_dismiss"

    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE creator_trend_results "
                "(account_id TEXT PRIMARY KEY)"
            )
        )
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )

        migration.upgrade()
        migration.upgrade()
        assert _column_names(connection) == {
            "account_id",
            "weekly_opportunity_json",
        }

        migration.downgrade()
        migration.downgrade()
        assert _column_names(connection) == {"account_id"}
