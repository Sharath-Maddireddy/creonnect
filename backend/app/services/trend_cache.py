"""Trend analysis result caching to reduce API calls and improve latency."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from backend.app.domain.trend_models import TrendAnalysisResult
from backend.app.domain.post_models import SinglePostInsights
from backend.app.infra.redis_client import get_redis, get_async_redis
from backend.app.utils.logger import logger


class TrendAnalysisCache:
    """Cache trend analysis results to reduce OpenAI API calls.
    
    Cache Key: trend_cache:{account_id}:{post_content_hash}
    TTL: 86400 seconds (24 hours)
    
    Invalidation:
    - Time-based: 24 hour expiry
    - Content-based: Different posts = different cache entry
    """

    CACHE_TTL_SECONDS = 86400  # 24 hours
    CACHE_KEY_PREFIX = "trend_cache"

    @staticmethod
    def _get_post_content_hash(posts: list[SinglePostInsights]) -> str:
        """Generate stable hash based on post content.
        
        Uses post IDs to detect when historical posts have changed.
        Different post set = different cache entry = forces re-analysis.
        """
        if not posts:
            return "empty"

        post_ids = "|".join(sorted(p.media_id or "" for p in posts[:12]))
        content_hash = hashlib.md5(post_ids.encode()).hexdigest()
        return content_hash

    @staticmethod
    def get_cache_key(account_id: str, posts: list[SinglePostInsights]) -> str:
        """Generate cache key from account ID and post content."""
        content_hash = TrendAnalysisCache._get_post_content_hash(posts)
        return f"{TrendAnalysisCache.CACHE_KEY_PREFIX}:{account_id}:{content_hash}"

    @classmethod
    def get(
        cls,
        account_id: str,
        posts: list[SinglePostInsights]
    ) -> Optional[TrendAnalysisResult]:
        """Retrieve cached trend analysis if available and fresh.
        
        Args:
            account_id: Creator's account ID
            posts: Historical posts (used to compute cache key)
            
        Returns:
            TrendAnalysisResult if cached, None otherwise
        """
        try:
            redis_client = get_redis()
            key = cls.get_cache_key(account_id, posts)

            cached_json = redis_client.get(key)
            if not cached_json:
                return None

            cached_data = json.loads(cached_json)
            result = TrendAnalysisResult.model_validate(cached_data)

            logger.info(
                f"[TrendCache] HIT for account_id={account_id} "
                f"(key={key})"
            )
            return result

        except Exception as exc:
            logger.warning(f"[TrendCache] Retrieval failed: {exc}")
            return None

    @classmethod
    def set(
        cls,
        account_id: str,
        posts: list[SinglePostInsights],
        result: TrendAnalysisResult
    ) -> None:
        """Cache trend analysis result for future use.
        
        Args:
            account_id: Creator's account ID
            posts: Historical posts (used to compute cache key)
            result: TrendAnalysisResult to cache
        """
        try:
            redis_client = get_redis()
            key = cls.get_cache_key(account_id, posts)

            result_json = json.dumps(
                result.model_dump(mode="python"),
                ensure_ascii=True,
                separators=(",", ":")
            )

            redis_client.setex(
                key,
                cls.CACHE_TTL_SECONDS,
                result_json
            )

            logger.info(
                f"[TrendCache] SET for account_id={account_id} "
                f"(ttl={cls.CACHE_TTL_SECONDS}s, key={key})"
            )

        except Exception as exc:
            logger.warning(f"[TrendCache] Storage failed: {exc}")

    @classmethod
    async def aget(
        cls,
        account_id: str,
        posts: list[SinglePostInsights]
    ) -> Optional[TrendAnalysisResult]:
        """Async variant of get()."""
        try:
            redis_client = get_async_redis()
            key = cls.get_cache_key(account_id, posts)

            cached_json = await redis_client.get(key)
            if not cached_json:
                return None

            cached_data = json.loads(cached_json)
            result = TrendAnalysisResult.model_validate(cached_data)

            logger.info(
                f"[TrendCache] ASYNC HIT for account_id={account_id}"
            )
            return result

        except Exception as exc:
            logger.warning(f"[TrendCache] Async retrieval failed: {exc}")
            return None

    @classmethod
    async def aset(
        cls,
        account_id: str,
        posts: list[SinglePostInsights],
        result: TrendAnalysisResult
    ) -> None:
        """Async variant of set()."""
        try:
            redis_client = get_async_redis()
            key = cls.get_cache_key(account_id, posts)

            result_json = json.dumps(
                result.model_dump(mode="python"),
                ensure_ascii=True,
                separators=(",", ":")
            )

            await redis_client.setex(
                key,
                cls.CACHE_TTL_SECONDS,
                result_json
            )

            logger.info(
                f"[TrendCache] ASYNC SET for account_id={account_id}"
            )

        except Exception as exc:
            logger.warning(f"[TrendCache] Async storage failed: {exc}")

    @classmethod
    def invalidate(cls, account_id: str) -> None:
        """Manually invalidate all cached results for an account.
        
        Use this after manual corrections or if cache is corrupted.
        """
        try:
            redis_client = get_redis()
            pattern = f"{cls.CACHE_KEY_PREFIX}:{account_id}:*"
            keys = redis_client.keys(pattern)

            if keys:
                redis_client.delete(*keys)
                logger.info(f"[TrendCache] Invalidated {len(keys)} entries for {account_id}")

        except Exception as exc:
            logger.warning(f"[TrendCache] Invalidation failed: {exc}")
