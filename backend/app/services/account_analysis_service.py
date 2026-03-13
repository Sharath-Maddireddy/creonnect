"""Service wrapper for deterministic account-level health analysis."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

from backend.app.analytics.account_health_engine import compute_account_health_score
from backend.app.domain.account_models import AccountHealthScore
from backend.app.domain.post_models import SinglePostInsights


ACCOUNT_HEALTH_CACHE_TTL_SECONDS = 3600
ACCOUNT_HEALTH_CACHE_MAX_SIZE = 1000


@dataclass
class _AccountHealthCacheEntry:
    result: AccountHealthScore
    cached_at: float


_ACCOUNT_HEALTH_CACHE: OrderedDict[str, _AccountHealthCacheEntry] = OrderedDict()
_ACCOUNT_HEALTH_CACHE_LOCK = threading.Lock()


def _stable_post_fingerprint(posts: list[SinglePostInsights]) -> str:
    rows: list[dict[str, object]] = []
    for post in posts:
        rows.append(
            {
                "account_id": post.account_id,
                "media_id": post.media_id,
                "published_at": post.published_at.isoformat() if isinstance(post.published_at, datetime) else None,
                "engagement_rate": post.derived_metrics.engagement_rate,
                "s1": post.visual_quality_score.total,
                "s2": post.caption_effectiveness_score.total_0_50,
                "s3": post.content_clarity_score.total,
                "s4": post.audience_relevance_score.total_0_50,
                "s5": post.engagement_potential_score.total,
                "s6": post.brand_safety_score.total_0_50,
                "p": post.weighted_post_score.score,
            }
        )
    rows.sort(key=lambda row: (str(row.get("media_id") or ""), str(row.get("published_at") or "")))
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _format_rate(rate: float | None) -> str:
    return f"{rate:.6f}" if rate is not None else ""


def _cache_key(
    posts: list[SinglePostInsights],
    account_avg_engagement_rate: float | None,
    niche_avg_engagement_rate: float | None,
    follower_band: str | None,
) -> str:
    account_id = posts[0].account_id if posts and isinstance(posts[0].account_id, str) else "unknown_account"
    fingerprint = _stable_post_fingerprint(posts)
    return (
        f"{account_id}:{fingerprint}:"
        f"{_format_rate(account_avg_engagement_rate)}:{_format_rate(niche_avg_engagement_rate)}:{follower_band or ''}"
    )


def _purge_expired_cache_entries(current_ts: float) -> None:
    with _ACCOUNT_HEALTH_CACHE_LOCK:
        expired_keys = [
            key
            for key, entry in _ACCOUNT_HEALTH_CACHE.items()
            if (current_ts - entry.cached_at) > ACCOUNT_HEALTH_CACHE_TTL_SECONDS
        ]
        for key in expired_keys:
            _ACCOUNT_HEALTH_CACHE.pop(key, None)


def _get_cached_account_health(key: str, current_ts: float) -> AccountHealthScore | None:
    with _ACCOUNT_HEALTH_CACHE_LOCK:
        cached = _ACCOUNT_HEALTH_CACHE.get(key)
        if cached is None:
            return None
        if (current_ts - cached.cached_at) > ACCOUNT_HEALTH_CACHE_TTL_SECONDS:
            _ACCOUNT_HEALTH_CACHE.pop(key, None)
            return None
        _ACCOUNT_HEALTH_CACHE.move_to_end(key)
        return cached.result


def _set_cached_account_health(key: str, result: AccountHealthScore, current_ts: float) -> None:
    with _ACCOUNT_HEALTH_CACHE_LOCK:
        _ACCOUNT_HEALTH_CACHE[key] = _AccountHealthCacheEntry(result=result, cached_at=current_ts)
        _ACCOUNT_HEALTH_CACHE.move_to_end(key)
        while len(_ACCOUNT_HEALTH_CACHE) > ACCOUNT_HEALTH_CACHE_MAX_SIZE:
            _ACCOUNT_HEALTH_CACHE.popitem(last=False)


def analyze_account_health(
    posts: list[SinglePostInsights],
    account_avg_engagement_rate: float | None = None,
    niche_avg_engagement_rate: float | None = None,
    follower_band: str | None = None,
    now_ts: datetime | None = None,
    use_cache: bool = True,
) -> AccountHealthScore:
    """Analyze account health from precomputed SinglePostInsights posts."""

    key = _cache_key(posts, account_avg_engagement_rate, niche_avg_engagement_rate, follower_band)
    current_ts = time.time()
    if use_cache:
        _purge_expired_cache_entries(current_ts)
        cached = _get_cached_account_health(key, current_ts)
        if cached is not None:
            return cached

    result = compute_account_health_score(
        posts=posts,
        account_avg_engagement_rate=account_avg_engagement_rate,
        niche_avg_engagement_rate=niche_avg_engagement_rate,
        follower_band=follower_band,
        now_ts=now_ts,
    )

    if use_cache:
        _set_cached_account_health(key, result, current_ts)

    return result
