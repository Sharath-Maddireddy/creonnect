from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Any

from backend.app.ai import toon
from backend.app.ai.llm_client import LLMClient
from backend.app.domain.draft_models import DraftPostOptimizationResponse, DraftVisualAnalysis
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.services.ai_analysis_service import run_vision_analysis
from backend.app.utils.logger import logger


_DRAFT_OPTIMIZER_SYSTEM_PROMPT = """
You are an expert Instagram growth strategist and AI post optimizer.
The user is providing a draft caption for an upcoming post, along with their account's historical performance data.
Your goal is to optimize their draft caption focusing on hooks and CTAs, predict its potential reach, suggest optimal posting times, and flag any safety risks.
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
- You must analyze the historical_posts provided to base predicted_reach_band and optimal_posting_times on actual past performance.
- optimized_caption_options should preserve the creator's core message but make it more engaging.
- predicted_reach_band must be exactly one of: High, Average, Low.
- Never output hashtags in your caption options.
""".strip()


def _safe_text(value: Any, *, limit: int = 280) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _safe_list(value: Any, *, limit: int, max_items: int) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text[:limit]] if text else []
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


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
    return default


def _serialize_historical_post(post: SinglePostInsights) -> dict[str, Any]:
    core = post.core_metrics
    derived = post.derived_metrics
    return {
        "media_id": post.media_id,
        "media_type": post.media_type,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "caption_text": _safe_text(post.caption_text, limit=220),
        "likes": getattr(core, "likes", None) if core is not None else None,
        "comments": getattr(core, "comments", None) if core is not None else None,
        "shares": getattr(core, "shares", None) if core is not None else None,
        "saves": getattr(core, "saves", None) if core is not None else None,
        "reach": getattr(core, "reach", None) if core is not None else None,
        "engagement_rate": getattr(derived, "engagement_rate", None) if derived is not None else None,
        "save_rate": getattr(derived, "save_rate", None) if derived is not None else None,
        "share_rate": getattr(derived, "share_rate", None) if derived is not None else None,
    }


def _build_prompt_payload(
    *,
    draft_caption: str,
    post_type: str,
    media_url: str | None,
    account_data: dict[str, Any],
    historical_posts: list[SinglePostInsights],
) -> dict[str, Any]:
    return {
        "account": {
            "account_id": account_data.get("account_id"),
            "username": account_data.get("username"),
            "follower_count": account_data.get("follower_count"),
            "creator_dominant_category": account_data.get("creator_dominant_category"),
            "niche_tags": list(account_data.get("niche_tags") or []),
            "bio": account_data.get("bio"),
        },
        "draft_post": {
            "caption_text": draft_caption,
            "post_type": post_type,
            "media_url": media_url,
        },
        "historical_posts": [_serialize_historical_post(post) for post in historical_posts[:12]],
    }


def _fallback_response() -> DraftPostOptimizationResponse:
    return DraftPostOptimizationResponse(
        optimized_caption_options=[],
        predicted_reach_band="Average",
        optimal_posting_times=[],
        safety_flags=[],
        content_format_recommendation="Keep the format aligned with your strongest recent post type.",
        tone_alignment_warning="",
        visual_analysis=None,
    )


async def _analyze_visual_draft(
    *,
    account_id: str,
    draft_caption: str,
    post_type: str,
    media_url: str,
    follower_count: int | None,
) -> DraftVisualAnalysis | None:
    media_id = hashlib.sha1(f"{account_id}:{post_type}:{media_url}:{draft_caption}".encode("utf-8")).hexdigest()[:16]
    draft_post = SinglePostInsights(
        account_id=account_id,
        media_id=f"draft_{media_id}",
        media_type=post_type,
        media_url=media_url,
        caption_text=draft_caption,
        follower_count=follower_count,
        core_metrics=CoreMetrics(),
        derived_metrics=DerivedMetrics(),
        benchmark_metrics=BenchmarkMetrics(),
    )
    try:
        vision_payload = await run_vision_analysis(draft_post)
    except Exception as exc:
        logger.warning("[DraftOptimizer] Visual analysis failed for account_id=%s: %s", account_id, exc)
        return None

    signals = vision_payload.get("signals") if isinstance(vision_payload, dict) else None
    first_signal = signals[0] if isinstance(signals, list) and signals and isinstance(signals[0], dict) else {}
    visual_quality = first_signal.get("visual_quality_score")
    if isinstance(visual_quality, dict):
        visual_quality_score = int(round(sum(float(visual_quality.get(key) or 0.0) for key in visual_quality) / 4.0))
    else:
        try:
            visual_quality_score = int(round(float(visual_quality)))
        except (TypeError, ValueError):
            visual_quality_score = 0

    detected_text = first_signal.get("detected_text")
    if detected_text is None:
        detected_text = ""
    elif not isinstance(detected_text, str):
        detected_text = str(detected_text)

    return DraftVisualAnalysis(
        visual_quality_score=max(0, min(10, visual_quality_score)),
        hook_strength_score=max(0.0, min(1.0, float(first_signal.get("hook_strength_score") or 0.0))),
        primary_objects=[item for item in first_signal.get("primary_objects", []) if isinstance(item, str)][:4]
        if isinstance(first_signal.get("primary_objects"), list)
        else [],
        detected_text=detected_text.strip(),
        lighting_feedback=_safe_text(first_signal.get("lighting_feedback"), limit=160),
        composition_feedback=_safe_text(first_signal.get("composition_feedback"), limit=160),
        aesthetic_fixes=_safe_list(first_signal.get("aesthetic_fixes"), limit=160, max_items=4),
        is_cringe=_safe_bool(first_signal.get("is_cringe"), default=False),
        adult_content_detected=_safe_bool(first_signal.get("adult_content_detected"), default=False),
    )


async def optimize_draft_post(
    *,
    draft_caption: str,
    post_type: str,
    account_data: dict[str, Any],
    historical_posts: list[SinglePostInsights],
    media_url: str | None = None,
) -> DraftPostOptimizationResponse:
    fallback = _fallback_response()
    payload = _build_prompt_payload(
        draft_caption=draft_caption,
        post_type=post_type,
        media_url=media_url,
        account_data=account_data,
        historical_posts=historical_posts,
    )
    prompt = {
        "system": _DRAFT_OPTIMIZER_SYSTEM_PROMPT,
        "user": toon.dumps(payload) if hasattr(toon, "dumps") else str(payload),
    }

    visual_analysis = None
    if isinstance(media_url, str) and media_url.strip():
        follower_count = account_data.get("follower_count")
        visual_analysis = await _analyze_visual_draft(
            account_id=str(account_data.get("account_id") or "unknown_account"),
            draft_caption=draft_caption,
            post_type=post_type,
            media_url=media_url.strip(),
            follower_count=follower_count if isinstance(follower_count, int) else None,
        )

    try:
        llm = LLMClient(
            model_name=os.getenv("LLM_MODEL_NAME") or LLMClient.DEFAULT_MODEL,
            temperature=0.2,
        )
        raw_response = await asyncio.to_thread(llm.generate, prompt)
        parsed = toon.loads(raw_response or "")
        optimized_caption_options = _safe_list(parsed.get("optimized_caption_options"), limit=500, max_items=3)
        predicted_reach_band = _safe_text(parsed.get("predicted_reach_band"), limit=20).title() or "Average"
        if predicted_reach_band not in {"High", "Average", "Low"}:
            predicted_reach_band = "Average"

        response = DraftPostOptimizationResponse(
            optimized_caption_options=optimized_caption_options,
            predicted_reach_band=predicted_reach_band,
            optimal_posting_times=_safe_list(parsed.get("optimal_posting_times"), limit=120, max_items=4),
            safety_flags=_safe_list(parsed.get("safety_flags"), limit=200, max_items=6),
            content_format_recommendation=_safe_text(parsed.get("content_format_recommendation"), limit=240),
            tone_alignment_warning=_safe_text(parsed.get("tone_alignment_warning"), limit=240),
            visual_analysis=visual_analysis,
        )
        if not response.content_format_recommendation:
            response.content_format_recommendation = fallback.content_format_recommendation
        return response
    except Exception as exc:
        logger.warning("[DraftOptimizer] LLM optimization failed; using fallback: %s", exc)
        fallback.visual_analysis = visual_analysis
        return fallback


__all__ = ["optimize_draft_post"]
