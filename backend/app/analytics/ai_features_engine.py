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
You are an expert Instagram growth strategist and AI post optimizer.
The user is providing a draft caption for an upcoming post, along with their account's historical performance data.
Your goal is to optimize their draft caption (focusing on hooks and CTAs), predict its potential reach, suggest optimal posting times, and flag any safety risks.
DO NOT generate or suggest hashtags.

Return plain TOON only.
Do not return JSON.
Do not use braces.
Do not wrap keys or values in quotes unless absolutely required for spaces.

Output schema (all keys required):
optimized_caption_options
  - <str>
  - <str>
predicted_reach_band <str>
optimal_posting_times
  - <str>
  - <str>
safety_flags
  - <str>
content_format_recommendation <str>
tone_alignment_warning <str>

Constraints:
- You must analyze the 'historical_posts' provided to base your 'predicted_reach_band' and 'optimal_posting_times' on actual past performance.
- 'optimized_caption_options' should preserve the creator's core message but make it more engaging.
- 'predicted_reach_band' must be exactly one of: High, Average, Low.
- 'optimal_posting_times' should be specific, containing the exact day of the week and an hourly time range based on high-performing historical posts (e.g., 'Tuesdays 4:00 PM - 6:00 PM').
- Never output hashtags in your caption options.
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


def _safe_text(value: Any, default: str | None = None, *, limit: int = 280) -> str | None:
    if not isinstance(value, str):
        return default
    text = value.strip()
    if not text:
        return default
    return text[:limit]


def _safe_string_list(value: Any, *, limit: int = 160, max_items: int = 6) -> list[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized[:limit]] if normalized else []
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        items.append(text[:limit])
        if len(items) >= max_items:
            break
    return items


def _build_prompt_payload(posts: list[SinglePostInsights], account_data: dict[str, Any]) -> dict[str, Any]:
    follower_count = account_data.get("follower_count")
    if follower_count is None:
        follower_count = account_data.get("followers")
    if follower_count is None and posts:
        follower_count = posts[0].follower_count
    draft_caption = (
        _safe_text(account_data.get("draft_caption"), limit=600)
        or _safe_text(account_data.get("upcoming_caption"), limit=600)
        or _safe_text(account_data.get("caption_text"), limit=600)
        or ""
    )

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
        "draft_caption": draft_caption,
        "historical_posts": compact_posts,
        "historical_post_count": len(posts),
        "recent_captions": captions[:8],
    }


def _prediction_cache_key(payload: dict[str, Any], *, model_name: str) -> str:
    cache_payload = {
        "model_name": model_name,
        "prompt_payload": payload,
    }
    return hashlib.sha256(
        json.dumps(cache_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


async def generate_ai_feature_predictions(posts: list[SinglePostInsights], account_data: dict[str, Any]) -> AIFeaturePredictions:
    """LLM-backed AI feature prediction engine with safe fallback behavior."""
    payload = _build_prompt_payload(posts, account_data)
    prompt = {
        "system": _AI_FEATURES_SYSTEM_PROMPT,
        "user": json.dumps(payload, ensure_ascii=True),
    }

    fallback = AIFeaturePredictions(
        optimized_caption_options=[],
        predicted_reach_band="Average",
        optimal_posting_times=[],
        safety_flags=[],
        content_format_recommendation="Keep the current format and strengthen the opening line.",
        tone_alignment_warning="",
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

        optimized_caption_options = _safe_string_list(parsed.get("optimized_caption_options"), limit=500, max_items=2)
        optimal_posting_times = _safe_string_list(parsed.get("optimal_posting_times"), limit=120, max_items=4)
        safety_flags = _safe_string_list(parsed.get("safety_flags"), limit=200, max_items=6)
        predicted_reach_band_raw = _safe_text(parsed.get("predicted_reach_band"), default="Average", limit=20) or "Average"
        predicted_reach_band = predicted_reach_band_raw.title()
        if predicted_reach_band not in {"High", "Average", "Low"}:
            predicted_reach_band = "Average"

        content_format_recommendation = _safe_text(
            parsed.get("content_format_recommendation"),
            default="Keep the current format and strengthen the opening line.",
            limit=240,
        )
        tone_alignment_warning = _safe_text(parsed.get("tone_alignment_warning"), default="", limit=240)

        return AIFeaturePredictions(
            optimized_caption_options=optimized_caption_options,
            predicted_reach_band=predicted_reach_band,
            optimal_posting_times=optimal_posting_times,
            safety_flags=safety_flags,
            content_format_recommendation=content_format_recommendation,
            tone_alignment_warning=tone_alignment_warning,
            viral_probability=_clamp(_safe_float(parsed.get("viral_probability"), 0.05), 0.0, 1.0),
            campaign_roi_prediction=predicted_reach_band,
            best_posting_time=optimal_posting_times,
            audience_authenticity_score=_clamp(
                _safe_float(parsed.get("audience_authenticity_score"), 50.0), 0.0, 100.0
            ),
            spam_detected_count=sum(
                1 for flag in safety_flags if "spam" in flag.lower() or "bot" in flag.lower()
            ),
            sentiment_score=0.0,
            prediction_status="ok",
            degraded_reason=None,
        )
    except Exception as exc:
        logger.warning("[AIFeaturesEngine] LLM prediction failed; using fallback: %s", exc)
        return fallback


def generate_ai_feature_predictions_sync(posts: list[SinglePostInsights], account_data: dict[str, Any]) -> AIFeaturePredictions:
    """Loop-safe sync wrapper for async AI feature prediction."""
    prompt_payload = _build_prompt_payload(posts, account_data)
    cache_key = _prediction_cache_key(
        prompt_payload,
        model_name=os.getenv("LLM_MODEL_NAME") or LLMClient.DEFAULT_MODEL,
    )
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
