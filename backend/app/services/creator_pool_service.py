"""Service for managing and querying the creator pool."""

from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path

from backend.app.ai.llm_client import LLMClient
from backend.app.utils.logger import logger


_CREATOR_POOL_CACHE: list[dict] | None = None
_CREATOR_EMBEDDINGS_CACHE = {}
_CREATOR_POOL_LOADED_AT: float | None = None
_CREATOR_POOL_LOCK = threading.Lock()
_CREATOR_EMBEDDINGS_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 300
_LLM_CLIENT: LLMClient | None = None


def _get_llm_client() -> LLMClient:
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        with _CREATOR_POOL_LOCK:
            if _LLM_CLIENT is None:
                _LLM_CLIENT = LLMClient()
    return _LLM_CLIENT


def _get_creator_text(creator: dict) -> str:
    """Combine creator fields into a single string for embedding."""
    dominant_category = str(creator.get("creator_dominant_category") or "").strip()
    niche_tags = creator.get("niche_tags") or []
    niche_tags_text = " ".join(str(tag).strip() for tag in niche_tags if str(tag).strip())
    bio = str(creator.get("bio") or "").strip()
    return " ".join(part for part in (dominant_category, niche_tags_text, bio) if part)


def cosine_similarity(vec1, vec2) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


def _ensure_creator_embedding(creator: dict) -> list[float] | None:
    """Lazily compute and cache a creator embedding outside the pool-load lock."""
    account_id = creator.get("account_id")
    if not account_id:
        return None

    cached_embedding = _CREATOR_EMBEDDINGS_CACHE.get(account_id)
    if cached_embedding is not None:
        creator["embedding"] = cached_embedding
        return cached_embedding

    creator_text = _get_creator_text(creator)
    if not creator_text:
        return None

    with _CREATOR_EMBEDDINGS_LOCK:
        cached_embedding = _CREATOR_EMBEDDINGS_CACHE.get(account_id)
        if cached_embedding is not None:
            creator["embedding"] = cached_embedding
            return cached_embedding

        embedding = _get_llm_client().embed(creator_text)
        if embedding is not None:
            _CREATOR_EMBEDDINGS_CACHE[account_id] = embedding
            creator["embedding"] = embedding
        return embedding


def _load_creator_pool() -> list[dict]:
    """Load the creator pool JSON file. Uses a thread-safe module cache."""
    global _CREATOR_POOL_CACHE, _CREATOR_POOL_LOADED_AT
    now = time.time()

    if (
        _CREATOR_POOL_CACHE is not None
        and _CREATOR_POOL_LOADED_AT is not None
        and now - _CREATOR_POOL_LOADED_AT <= _CACHE_TTL_SECONDS
    ):
        return _CREATOR_POOL_CACHE

    with _CREATOR_POOL_LOCK:
        # Double-check inside lock
        now = time.time()
        if (
            _CREATOR_POOL_CACHE is not None
            and _CREATOR_POOL_LOADED_AT is not None
            and now - _CREATOR_POOL_LOADED_AT <= _CACHE_TTL_SECONDS
        ):
            return _CREATOR_POOL_CACHE

        if _CREATOR_POOL_CACHE is not None:
            _CREATOR_POOL_CACHE = None
            _CREATOR_POOL_LOADED_AT = None

        try:
            pool_path = Path(__file__).parent.parent / "demo" / "creator_pool.json"
            if not pool_path.exists():
                logger.warning(f"[CreatorPoolService] Pool file not found at {pool_path}")
                _CREATOR_POOL_CACHE = []
                _CREATOR_POOL_LOADED_AT = time.time()
                return _CREATOR_POOL_CACHE

            with open(pool_path, "r", encoding="utf-8") as f:
                _CREATOR_POOL_CACHE = json.load(f)

            _CREATOR_POOL_LOADED_AT = time.time()
            logger.info(f"[CreatorPoolService] Loaded {len(_CREATOR_POOL_CACHE)} creators into pool cache.")
        except Exception as e:
            logger.exception(f"[CreatorPoolService] Error loading creator pool: {e}")
            _CREATOR_POOL_CACHE = []
            _CREATOR_POOL_LOADED_AT = time.time()

        return _CREATOR_POOL_CACHE


def reload_creator_pool() -> None:
    """Force a cache reset so the creator pool reloads on next access."""
    global _CREATOR_POOL_CACHE, _CREATOR_POOL_LOADED_AT
    with _CREATOR_POOL_LOCK:
        _CREATOR_POOL_CACHE = None
        _CREATOR_POOL_LOADED_AT = None
        _CREATOR_EMBEDDINGS_CACHE.clear()


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
        _ensure_creator_embedding(creator)
        filtered.append(creator)

    return filtered


def find_lookalikes(account_id: str, k: int = 3) -> list[dict] | None:
    """Return top-k lookalikes, or None when the target creator does not exist."""
    pool = _load_creator_pool()
    target_creator = next((creator for creator in pool if creator.get("account_id") == account_id), None)
    if target_creator is None:
        return None

    target_embedding = _ensure_creator_embedding(target_creator)
    if target_embedding is None:
        return []

    scored_matches: list[tuple[float, dict]] = []
    for creator in pool:
        other_account_id = creator.get("account_id")
        if not other_account_id or other_account_id == account_id:
            continue

        other_embedding = _ensure_creator_embedding(creator)
        if other_embedding is None:
            continue

        similarity = cosine_similarity(target_embedding, other_embedding)
        scored_matches.append((similarity, creator))

    scored_matches.sort(key=lambda item: item[0], reverse=True)
    return [creator for _, creator in scored_matches[:k]]
