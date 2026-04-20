"""Import demo creators into the database and generate embeddings."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.infra.database import get_sync_engine
from backend.app.infra.models import Base
from backend.app.workers.embedding_worker import generate_creator_embedding, upsert_creator


def main() -> None:
    try:
        engine = get_sync_engine()
        with engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as exc:
        print(f"Database initialization failed: {exc}")
        return

    pool_path = Path(__file__).resolve().parents[1] / "demo" / "creator_pool.json"
    with pool_path.open("r", encoding="utf-8") as handle:
        creators = json.load(handle)

    total = len(creators)
    for index, creator in enumerate(creators, start=1):
        upsert_creator(creator)
        generate_creator_embedding(str(creator.get("account_id") or ""))
        username = creator.get("username") or creator.get("account_id") or "unknown"
        print(f"[{index}/{total}] Imported {username} - embedding generated OK")


if __name__ == "__main__":
    main()
