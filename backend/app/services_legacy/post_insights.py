"""
Post insights orchestration service.

This module only orchestrates deterministic signal generation and AI narrative
analysis. It does not implement scoring formulas or AI generation logic.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.ai_post_analysis import generate_post_ai_analysis
from services.post_ai_cache_repository import PostAICacheRepository
from services.signal_engine import compute_post_signals

# Singleton in-memory cache repository keeps entries across function calls.
_cache_repo = PostAICacheRepository()


def generate_post_insights(
    post_metadata: dict,
    metrics: dict,
    benchmarks: dict,
    reach_breakdown: dict | None,
    tier_name: str,
) -> dict:
    """
    Build unified post insights by orchestrating deterministic and AI layers.

    Flow:
    1) Compute deterministic signals with `compute_post_signals`.
    2) Generate AI narrative with `generate_post_ai_analysis`.
    3) Return a unified response containing source inputs, signals, and AI output.
    """
    normalized_post_metadata: Dict[str, Any] = post_metadata or {}
    normalized_metrics: Dict[str, Any] = metrics or {}
    normalized_benchmarks: Dict[str, Any] = benchmarks or {}
    normalized_reach_breakdown: Optional[Dict[str, Any]] = (
        reach_breakdown if reach_breakdown is not None else None
    )
    normalized_tier_name: str = tier_name or ""
    account_id: str = str(normalized_post_metadata.get("account_id") or "")
    media_id: str = str(normalized_post_metadata.get("media_id") or "")
    has_cache_key = bool(account_id and media_id)
    cache_repo = _cache_repo

    # Deterministic layer must always run, regardless of cache/AI state.
    signals = compute_post_signals(
        metrics=normalized_metrics,
        benchmarks=normalized_benchmarks,
        reach_breakdown=normalized_reach_breakdown,
    )

    if has_cache_key:
        cached = cache_repo.get_cached_analysis(account_id, media_id)
        if cached:
            return {
                "post_metadata": normalized_post_metadata,
                "metrics": normalized_metrics,
                "signals": signals,
                "ai_analysis": {
                    "status": cached.get("status", "ERROR"),
                    "summary": cached.get("summary", ""),
                    "drivers": cached.get("drivers", []),
                    "recommendations": cached.get("recommendations", []),
                },
            }

        allowed = cache_repo.acquire_regen_lock(account_id, media_id)
        if not allowed:
            return {
                "post_metadata": normalized_post_metadata,
                "metrics": normalized_metrics,
                "signals": signals,
                "ai_analysis": {
                    "status": "SKIPPED_LOCK",
                    "summary": "",
                    "drivers": [],
                    "recommendations": [],
                },
            }

        try:
            ai_result = generate_post_ai_analysis(
                post_metadata=normalized_post_metadata,
                metrics=normalized_metrics,
                signals=signals,
                benchmarks=normalized_benchmarks,
                tier_name=normalized_tier_name,
            )

            if ai_result.get("status") == "READY":
                cache_repo.set_cached_analysis(account_id, media_id, ai_result)

            return {
                "post_metadata": normalized_post_metadata,
                "metrics": normalized_metrics,
                "signals": signals,
                "ai_analysis": {
                    "status": ai_result.get("status", "ERROR"),
                    "summary": ai_result.get("summary", ""),
                    "drivers": ai_result.get("drivers", []),
                    "recommendations": ai_result.get("recommendations", []),
                },
            }
        finally:
            cache_repo.release_regen_lock(account_id, media_id)
    # Without stable account/media IDs, cache and lock are intentionally skipped.

    ai_result = generate_post_ai_analysis(
        post_metadata=normalized_post_metadata,
        metrics=normalized_metrics,
        signals=signals,
        benchmarks=normalized_benchmarks,
        tier_name=normalized_tier_name,
    )

    return {
        "post_metadata": normalized_post_metadata,
        "metrics": normalized_metrics,
        "signals": signals,
        "ai_analysis": {
            "status": ai_result.get("status", "ERROR"),
            "summary": ai_result.get("summary", ""),
            "drivers": ai_result.get("drivers", []),
            "recommendations": ai_result.get("recommendations", []),
        },
    }
