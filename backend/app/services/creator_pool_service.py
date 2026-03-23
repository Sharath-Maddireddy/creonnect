"""Service for managing and querying the creator pool."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from backend.app.utils.logger import logger


_CREATOR_POOL_CACHE: list[dict] | None = None
_CREATOR_POOL_LOCK = threading.Lock()


def _load_creator_pool() -> list[dict]:
    """Load the creator pool JSON file. Uses a thread-safe module cache."""
    global _CREATOR_POOL_CACHE
    if _CREATOR_POOL_CACHE is not None:
        return _CREATOR_POOL_CACHE

    with _CREATOR_POOL_LOCK:
        # Double-check inside lock
        if _CREATOR_POOL_CACHE is not None:
            return _CREATOR_POOL_CACHE

        try:
            pool_path = Path(__file__).parent.parent / "demo" / "creator_pool.json"
            if not pool_path.exists():
                logger.warning(f"[CreatorPoolService] Pool file not found at {pool_path}")
                _CREATOR_POOL_CACHE = []
                return _CREATOR_POOL_CACHE

            with open(pool_path, "r", encoding="utf-8") as f:
                _CREATOR_POOL_CACHE = json.load(f)
            logger.info(f"[CreatorPoolService] Loaded {len(_CREATOR_POOL_CACHE)} creators into pool cache.")
        except Exception as e:
            logger.exception(f"[CreatorPoolService] Error loading creator pool: {e}")
            _CREATOR_POOL_CACHE = []

        return _CREATOR_POOL_CACHE


def get_all_creators() -> list[dict]:
    """Return the full unfiltered creator pool."""
    return _load_creator_pool()


def query_creator_pool(
    niche: str | None = None,
    min_followers: int | None = None,
    max_followers: int | None = None,
) -> list[dict]:
    """
    Filter the creator pool based on brand requirements.
    
    Args:
        niche: The target niche (e.g., 'fitness', 'tech'). Checked against dominant category and tags.
        min_followers: Minimum required follower count.
        max_followers: Maximum allowed follower count.
        
    Returns:
        List of creator dicts that pass all applied filters.
    """
    pool = _load_creator_pool()
    filtered: list[dict] = []
    
    niche_lower = niche.lower().strip() if niche else None

    for creator in pool:
        # 1. Check Follower Size
        followers = creator.get("follower_count", 0)
        
        if min_followers is not None and followers < min_followers:
            continue
            
        if max_followers is not None and followers > max_followers:
            continue
            
        # 2. Check Niche Fit
        if niche_lower:
            dominant = (creator.get("creator_dominant_category") or "").lower()
            tags = [t.lower() for t in creator.get("niche_tags", [])]
            
            # Simple keyword matching
            if niche_lower not in dominant and not any(niche_lower in t for t in tags):
                continue
                
        # If we made it here, the creator passes all filters
        filtered.append(creator)

    return filtered
