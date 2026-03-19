"""
Creator Pool Service

Loads and queries the demo creator pool used for brand matching flows.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from backend.app.utils.logger import logger


_CREATOR_POOL_PATH = Path(__file__).resolve().parents[1] / "demo" / "creator_pool.json"
_creator_pool_cache: list[dict] | None = None
_creator_pool_lock = Lock()


def _load_creator_pool() -> list[dict]:
    """
    Load the creator pool from disk using a singleton-style module cache.

    Returns:
        List of creator records loaded from ``creator_pool.json``.
    """

    global _creator_pool_cache
    if _creator_pool_cache is None:
        with _creator_pool_lock:
            if _creator_pool_cache is None:
                logger.info("[CreatorPool] Loading creator pool from %s", _CREATOR_POOL_PATH)
                with _CREATOR_POOL_PATH.open("r", encoding="utf-8") as fp:
                    payload = json.load(fp)
                if not isinstance(payload, list):
                    raise ValueError("creator_pool.json must contain a top-level array")
                _creator_pool_cache = [item for item in payload if isinstance(item, dict)]
                logger.info("[CreatorPool] Loaded %d creators", len(_creator_pool_cache))
    return list(_creator_pool_cache or [])


def get_all_creators() -> list[dict]:
    """
    Return the full unfiltered creator pool.

    Returns:
        List of all creator records.
    """

    return _load_creator_pool()


def query_creator_pool(
    niche: str | None = None,
    min_followers: int | None = None,
    max_followers: int | None = None,
) -> list[dict]:
    """
    Query the creator pool by niche and follower range.

    Niche matching checks the creator's dominant category first, then falls back
    to matching against ``niche_tags``. All string matches are case-insensitive.
    If the filtered result is empty, the full pool is returned as a fallback.

    Args:
        niche: Optional niche/category filter.
        min_followers: Optional minimum follower threshold.
        max_followers: Optional maximum follower threshold.

    Returns:
        Matching creators, or the full creator pool if nothing matched.
    """

    creators = _load_creator_pool()
    normalized_niche = (niche or "").strip().lower()
    filtered: list[dict] = []

    for creator in creators:
        follower_count = creator.get("follower_count")
        if not isinstance(follower_count, int):
            follower_count = None

        if min_followers is not None and (follower_count is None or follower_count < min_followers):
            continue
        if max_followers is not None and (follower_count is None or follower_count > max_followers):
            continue

        if normalized_niche:
            category = str(creator.get("creator_dominant_category") or "").strip().lower()
            niche_tags = creator.get("niche_tags")
            tag_matches = False
            if isinstance(niche_tags, list):
                tag_matches = any(normalized_niche in str(tag).strip().lower() for tag in niche_tags)

            category_matches = normalized_niche in category if category else False
            if not category_matches and not tag_matches:
                continue

        filtered.append(creator)

    if not filtered:
        logger.info(
            "[CreatorPool] No matches for niche=%s min_followers=%s max_followers=%s; returning full pool",
            niche,
            min_followers,
            max_followers,
        )
        return creators

    logger.info(
        "[CreatorPool] Returning %d matched creators for niche=%s min_followers=%s max_followers=%s",
        len(filtered),
        niche,
        min_followers,
        max_followers,
    )
    return filtered
