from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from concurrent.futures import Future
from threading import Lock, Thread
from typing import Any

from backend.app.ai import toon
from backend.app.ai.llm_client import LLMClient
from backend.app.domain.account_models import AIFeaturePredictions
from backend.app.domain.post_models import SinglePostInsights
from backend.app.utils.logger import logger


_AI_FEATURES_SYSTEM_PROMPT = """
You are an analytics prediction engine.
Return plain TOON only.
Do not return JSON.
Do not use braces.
Do not wrap keys or values in quotes unless absolutely required for spaces.

Output schema (all keys required):
viral_probability <float>
campaign_roi_prediction <str>
best_posting_time
  - <str>
  - <str>
audience_authenticity_score <float>
spam_detected_count <int>
sentiment_score <float>

Constraints:
- viral_probability must be in range 0.0 to 1.0
- audience_authenticity_score must be in range 0 to 100
- sentiment_score must be in range -1.0 to 1.0
- spam_detected_count must be a non-negative integer
- best_posting_time should be specific, containing the exact day of the week and an hourly time range, based on analyzing the provided published_at timestamps correlated with high engagement (e.g., 'Tuesdays 4:00 PM - 6:00 PM', 'Sundays 9:00 AM - 11:00 AM'). Avoid vague terms like 'Weekday' or 'Afternoon'.
""".strip()

_CACHE_TTL_SECONDS = 900
_PREDICTION_CACHE: dict[str, tuple[float, AIFeaturePredictions]] = {}
_PREDICTION_CACHE_LOCK = Lock()


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _build_prompt_payload(posts: list[SinglePostInsights], account_data: dict[str, Any]) -> dict[str, Any]:
    follower_count = account_data.get("follower_count")
    if follower_count is None:
        follower_count = account_data.get("followers")
    if follower_count is None and posts:
        follower_count = posts[0].follower_count

    compact_posts: list[dict[str, Any]] = []
    captions: list[str] = []
    for post in posts[:12]:
        core = getattr(post, "core_metrics", None)
        derived = getattr(post, "derived_metrics", None)
        caption = (post.caption_text or "").strip()
        if caption:
            captions.append(caption[:220])

        compact_posts.append(
            {
                "media_type": post.media_type,
                "published_at": post.published_at.isoformat() if post.published_at else None,
                "likes": getattr(core, "likes", None) if core is not None else None,
                "comments": getattr(core, "comments", None) if core is not None else None,
                "shares": getattr(core, "shares", None) if core is not None else None,
                "saves": getattr(core, "saves", None) if core is not None else None,
                "reach": getattr(core, "reach", None) if core is not None else None,
                "engagement_rate": getattr(derived, "engagement_rate", None) if derived is not None else None,
                "save_rate": getattr(derived, "save_rate", None) if derived is not None else None,
                "share_rate": getattr(derived, "share_rate", None) if derived is not None else None,
                "watch_through_rate": getattr(derived, "watch_through_rate", None) if derived is not None else None,
            }
        )

    return {
        "account": {
            "follower_count": _safe_int(follower_count, 0),
            "username": account_data.get("username"),
            "creator_dominant_category": account_data.get("creator_dominant_category"),
            "niche_tags": account_data.get("niche_tags") or [],
        },
        "post_count": len(posts),
        "recent_posts": compact_posts,
        "recent_captions": captions[:8],
    }


async def generate_ai_feature_predictions(posts: list[SinglePostInsights], account_data: dict[str, Any]) -> AIFeaturePredictions:
    """LLM-backed AI feature prediction engine with safe fallback behavior."""
    payload = _build_prompt_payload(posts, account_data)
    prompt = {
        "system": _AI_FEATURES_SYSTEM_PROMPT,
        "user": json.dumps(payload, ensure_ascii=True),
    }

    fallback = AIFeaturePredictions(
        viral_probability=0.05,
        campaign_roi_prediction="Unknown",
        best_posting_time=[],
        audience_authenticity_score=50.0,
        spam_detected_count=0,
        sentiment_score=0.0,
        prediction_status="degraded",
        degraded_reason="llm_prediction_failed",
    )

    try:
        llm = LLMClient(
            model_name=os.getenv("LLM_MODEL_NAME") or LLMClient.DEFAULT_MODEL,
            temperature=0.2,
        )
        raw_response = await asyncio.to_thread(llm.generate, prompt)
        parsed = toon.loads(raw_response or "")

        best_posting_time_raw = parsed.get("best_posting_time")
        best_posting_time: list[str] = []
        if isinstance(best_posting_time_raw, list):
            for item in best_posting_time_raw:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        best_posting_time.append(text[:120])
        elif isinstance(best_posting_time_raw, str):
            text = best_posting_time_raw.strip()
            if text:
                best_posting_time.append(text[:120])

        campaign_roi_raw = parsed.get("campaign_roi_prediction")
        campaign_roi_prediction = campaign_roi_raw.strip() if isinstance(campaign_roi_raw, str) else None

        return AIFeaturePredictions(
            viral_probability=_clamp(_safe_float(parsed.get("viral_probability"), 0.05), 0.0, 1.0),
            campaign_roi_prediction=campaign_roi_prediction,
            best_posting_time=best_posting_time,
            audience_authenticity_score=_clamp(
                _safe_float(parsed.get("audience_authenticity_score"), 50.0), 0.0, 100.0
            ),
            spam_detected_count=max(0, _safe_int(parsed.get("spam_detected_count"), 0)),
            sentiment_score=_clamp(_safe_float(parsed.get("sentiment_score"), 0.0), -1.0, 1.0),
            prediction_status="ok",
            degraded_reason=None,
        )
    except Exception as exc:
        logger.warning("[AIFeaturesEngine] LLM prediction failed; using fallback: %s", exc)
        return fallback


def generate_ai_feature_predictions_sync(posts: list[SinglePostInsights], account_data: dict[str, Any]) -> AIFeaturePredictions:
    """Loop-safe sync wrapper for async AI feature prediction."""
    cache_payload = {
        "account_id": account_data.get("account_id"),
        "follower_count": account_data.get("follower_count"),
        "post_count": len(posts),
        "recent_media_ids": [post.media_id for post in posts[:12]],
        "recent_published_at": [
            post.published_at.isoformat() if post.published_at else None for post in posts[:12]
        ],
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()
    now = time.time()
    with _PREDICTION_CACHE_LOCK:
        cached = _PREDICTION_CACHE.get(cache_key)
        if cached is not None and cached[0] > now:
            return cached[1]

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        result = asyncio.run(generate_ai_feature_predictions(posts, account_data))
        with _PREDICTION_CACHE_LOCK:
            _PREDICTION_CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, result)
        return result

    future: Future[AIFeaturePredictions] = Future()

    def _runner() -> None:
        try:
            result = asyncio.run(generate_ai_feature_predictions(posts, account_data))
            future.set_result(result)
        except Exception as exc:  # pragma: no cover
            future.set_exception(exc)

    worker = Thread(target=_runner, name="ai-features-sync-wrapper", daemon=True)
    worker.start()
    result = future.result()
    with _PREDICTION_CACHE_LOCK:
        _PREDICTION_CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, result)
    return result


__all__ = ["generate_ai_feature_predictions", "generate_ai_feature_predictions_sync"]
