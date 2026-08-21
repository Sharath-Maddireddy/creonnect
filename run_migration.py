"""Run the missing columns migration directly via SQLAlchemy."""
import asyncio
from backend.app.utils.env import load_app_env

load_app_env(override=True)

from backend.app.infra.database import initialize_database_engines
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import os

DATABASE_URL = os.environ["DATABASE_URL"]


async def main():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        # Add missing columns one by one with IF NOT EXISTS check
        for col in [
            "content_gaps_json",
            "daily_insights_json",
            "opportunity_bullets_json",
        ]:
            try:
                await conn.execute(
                    text(
                        f"ALTER TABLE creator_trend_results ADD COLUMN IF NOT EXISTS {col} JSONB NULL"
                    )
                )
                print(f"[OK] Added column: {col}")
            except Exception as e:
                print(f"[WARN] {col}: {e}")

    await engine.dispose()
    print("\nDone. Re-run your trend test now.")


if __name__ == "__main__":
    asyncio.run(main())
