"""Fixture-backed account source."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.account_sources.base import AccountSource
from backend.app.account_sources.mappers import build_seed_post_from_fixture_item, safe_int_or_none
from backend.app.account_sources.models import AccountSourceRequest, AccountSourceType, NormalizedAccountPayload


class FixtureAccountSource(AccountSource):
    """Load normalized account payloads from raw fixture files."""

    async def load(self, request: AccountSourceRequest) -> NormalizedAccountPayload:
        fixture_path = request.fixture_path
        if not fixture_path:
            raise ValueError("fixture_path is required when source='fixture'.")

        payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("Fixture payload must contain a non-empty 'items' list.")

        username = request.username or payload.get("username")
        raw_account_id = request.account_id or username or "fixture_account"
        account_id = str(raw_account_id).strip()
        if not account_id:
            raise ValueError("Unable to derive account_id from fixture payload.")

        follower_count = request.follower_count
        if follower_count is None:
            follower_count = safe_int_or_none(payload.get("followers_count"))
        if follower_count is None:
            follower_count = safe_int_or_none(payload.get("followers"))

        posts = [
            build_seed_post_from_fixture_item(
                item if isinstance(item, dict) else {},
                account_id=account_id,
                creator_dominant_category=request.creator_dominant_category,
            )
            for item in items[: request.post_limit]
        ]

        return NormalizedAccountPayload(
            source_type=AccountSourceType.FIXTURE,
            source_ref=str(Path(fixture_path).resolve()),
            source_meta={"fixture_path": str(Path(fixture_path).resolve())},
            account_id=account_id,
            username=username,
            bio=request.bio or payload.get("biography") or payload.get("bio"),
            follower_count=follower_count,
            creator_dominant_category=request.creator_dominant_category,
            niche_tags=list(request.niche_tags or []),
            posts=posts,
        )
