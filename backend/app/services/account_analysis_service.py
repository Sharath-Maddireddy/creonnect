"""Service wrapper for deterministic account-level health analysis."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime

from backend.app.analytics.account_health_engine import compute_account_health_score
from backend.app.domain.account_models import AccountHealthScore
from backend.app.domain.post_models import SinglePostInsights


ACCOUNT_HEALTH_CACHE_TTL_SECONDS = 3600


@dataclass
class _AccountHealthCacheEntry:
    result: AccountHealthScore
    cached_at: float


_ACCOUNT_HEALTH_CACHE: dict[str, _AccountHealthCacheEntry] = {}


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
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        f"{account_avg_engagement_rate}:{niche_avg_engagement_rate}:{follower_band or ''}"
    )


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
        cached = _ACCOUNT_HEALTH_CACHE.get(key)
        if cached is not None and (current_ts - cached.cached_at) <= ACCOUNT_HEALTH_CACHE_TTL_SECONDS:
            return cached.result

    result = compute_account_health_score(
        posts=posts,
        account_avg_engagement_rate=account_avg_engagement_rate,
        niche_avg_engagement_rate=niche_avg_engagement_rate,
        follower_band=follower_band,
        now_ts=now_ts,
    )

    if use_cache:
        _ACCOUNT_HEALTH_CACHE[key] = _AccountHealthCacheEntry(result=result, cached_at=current_ts)

    return result
