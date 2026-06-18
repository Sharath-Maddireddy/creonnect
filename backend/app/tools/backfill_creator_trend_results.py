"""Backfill script to compute and persist CreatorTrendResult for all creators.

Usage:
    python -m backend.app.tools.backfill_creator_trend_results

This will iterate creators in `creator_discovery_meta`, compute trends via
`CreatorTrendService.get_trends_and_recommendations`, and upsert rows into
`creator_trend_results`.
"""

from __future__ import annotations

import asyncio
import logging

from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import CreatorDiscoveryMeta, CreatorTrendResult
from backend.app.services.creator_trend_service import CreatorTrendService
from backend.app.services.draft_history_service import load_draft_history_context
from backend.app.domain.account_models import CreatorIntelligence

logger = logging.getLogger("backfill")


def upsert_trend_result_sync(account_id: str, result) -> None:
    Session = get_sync_sessionmaker()
    with Session() as session:
        existing = session.get(CreatorTrendResult, account_id)
        niche_payload = result.niche.model_dump(mode="python") if hasattr(result.niche, "model_dump") else {}
        global_trends_payload = [t.model_dump(mode="python") for t in result.global_trends]
        recommendations_payload = [r.model_dump(mode="python") for r in result.recommendations]

        if existing is None:
            new_row = CreatorTrendResult(
                account_id=account_id,
                niche_json=niche_payload,
                global_trends_json=global_trends_payload,
                recommendations_json=recommendations_payload,
            )
            session.add(new_row)
        else:
            existing.niche_json = niche_payload
            existing.global_trends_json = global_trends_payload
            existing.recommendations_json = recommendations_payload
            session.add(existing)
        session.commit()


async def compute_for_account(account_id: str) -> None:
    try:
        # Load history context (sync) in thread
        history = await asyncio.to_thread(load_draft_history_context, account_id)
        service = CreatorTrendService()
        creator_intel = CreatorIntelligence()
        result = await service.get_trends_and_recommendations(
            account_id=account_id,
            posts=history.historical_posts,
            bio=history.account_data.get("bio"),
            username=history.account_data.get("username"),
            creator_intelligence=creator_intel,
        )
        await asyncio.to_thread(upsert_trend_result_sync, account_id, result)
        logger.info("Backfilled trends for %s", account_id)
    except Exception as exc:
        logger.exception("Failed to compute/upsert trends for %s: %s", account_id, exc)


def main() -> None:
    Session = get_sync_sessionmaker()
    account_ids: list[str] = []
    with Session() as session:
        rows = session.query(CreatorDiscoveryMeta.account_id).all()
        account_ids = [r[0] for r in rows]

    logger.info("Found %d accounts to backfill", len(account_ids))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tasks = [compute_for_account(a) for a in account_ids]
    # run sequentially to avoid hitting rate limits or LLM quotas; adjust concurrency if desired
    for t in tasks:
        loop.run_until_complete(t)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
