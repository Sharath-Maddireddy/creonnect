"""Async AI analysis service for single-post insights."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from backend.app.ai.llm_client import LLMClient, LLMClientError
from backend.app.analytics.content_score import compute_content_score
from backend.app.domain.post_models import SinglePostInsights
from backend.app.utils.logger import logger


CACHE_TTL_SECONDS = 86400
MIN_REGEN_SECONDS = 7200


class AIAnalysisResult(TypedDict):
    """Structured response returned by AI single-post analysis."""

    summary: str
    drivers: list["AIDriver"]
    recommendations: list["AIRecommendation"]
    ai_content_score: int
    ai_content_band: str


class AIDriver(TypedDict):
    """Structured AI driver item."""

    id: str
    label: str
    type: Literal["POSITIVE", "LIMITING"]
    explanation: str


class AIRecommendation(TypedDict):
    """Structured AI recommendation item."""

    id: str
    text: str
    impact_level: Literal["HIGH", "MEDIUM", "LOW"]


@dataclass
class _CacheEntry:
    """Internal cache entry for AI analysis responses."""

    result: AIAnalysisResult
    cached_at: float
    last_regen_attempt_at: float


_ANALYSIS_CACHE: dict[str, _CacheEntry] = {}


def _cache_key(post: SinglePostInsights) -> str:
    """Build a stable cache key for a single post."""
    account_id = post.account_id or "unknown_account"
    media_id = post.media_id or "unknown_media"
    published_at = post.published_at.isoformat() if post.published_at is not None else "unknown_time"
    return f"{account_id}:{media_id}:{published_at}"


def _is_fresh(entry: _CacheEntry, now_ts: float) -> bool:
    """Return True when cache entry is still valid by TTL."""
    return (now_ts - entry.cached_at) <= CACHE_TTL_SECONDS


def _score_payload(post: SinglePostInsights) -> tuple[int, str]:
    """Compute deterministic content score payload from post metrics."""
    payload = compute_content_score(post.derived_metrics, post.benchmark_metrics)
    score = int(payload.get("score", 0))
    band = str(payload.get("band", "NEEDS_WORK"))
    return score, band


def build_ai_input_context(
    post: SinglePostInsights,
    ai_content_score: int,
    ai_content_band: str,
) -> dict[str, Any]:
    """Build input context for downstream AI calls.

    This is intentionally a stub and can be expanded with richer context later.
    """
    return {
        "account_id": post.account_id,
        "media_id": post.media_id,
        "media_type": post.media_type,
        "published_at": post.published_at.isoformat() if post.published_at is not None else None,
        "core_metrics": post.core_metrics.model_dump(),
        "derived_metrics": post.derived_metrics.model_dump(),
        "benchmark_metrics": post.benchmark_metrics.model_dump(),
        "ai_content_score": ai_content_score,
        "ai_content_band": ai_content_band,
    }


async def run_vision_analysis(
    post: SinglePostInsights,
) -> dict[str, Any]:
    """Run Gemini Vision analysis for a post media URL with strict JSON parsing."""
    import os
    from urllib.parse import urlparse

    instruction = (
        "Analyze this Instagram post image. Return ONLY valid JSON with fields: "
        "objects (array of strings), "
        "scene_description (string), "
        "detected_text (string or null), "
        "visual_style (string), "
        "hook_strength_score (float between 0 and 1). "
        "Do not include markdown or extra keys."
    )

    media_url = getattr(post, "media_url", None)
    if not isinstance(media_url, str) or not media_url.strip():
        return {
            "provider": "gemini",
            "status": "no_media",
            "signals": [],
        }

    media_url = media_url.strip()
    parsed_url = urlparse(media_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return {
            "provider": "gemini",
            "status": "no_media",
            "signals": [],
        }

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "provider": "gemini",
            "status": "error",
            "signals": [],
        }

    async def _generate() -> str:
        import google.generativeai as genai

        def _call() -> str:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-pro")
            response = model.generate_content([instruction, media_url])
            text = getattr(response, "text", None)
            if not isinstance(text, str):
                raise ValueError("Gemini response did not include text output.")
            return text

        return await asyncio.to_thread(_call)

    try:
        raw_text = await asyncio.wait_for(_generate(), timeout=15.0)
        payload = json.loads(raw_text)
        if not isinstance(payload, dict):
            raise ValueError("Gemini output must be a JSON object.")

        required_keys = {
            "objects",
            "scene_description",
            "detected_text",
            "visual_style",
            "hook_strength_score",
        }
        if not required_keys.issubset(payload.keys()):
            raise ValueError("Gemini JSON schema mismatch.")

        objects = payload.get("objects")
        scene_description = payload.get("scene_description")
        detected_text = payload.get("detected_text")
        visual_style = payload.get("visual_style")
        hook_strength_score = payload.get("hook_strength_score")

        if not isinstance(objects, list) or not all(isinstance(item, str) for item in objects):
            raise ValueError("Invalid objects field.")
        if not isinstance(scene_description, str):
            raise ValueError("Invalid scene_description field.")
        if detected_text is not None and not isinstance(detected_text, str):
            raise ValueError("Invalid detected_text field.")
        if not isinstance(visual_style, str):
            raise ValueError("Invalid visual_style field.")
        if not isinstance(hook_strength_score, (int, float)):
            raise ValueError("Invalid hook_strength_score field.")

        objects = [
            item.strip()
            for item in objects
            if isinstance(item, str) and item.strip()
        ]
        scene_description = scene_description.strip()
        detected_text = detected_text.strip() if detected_text else None
        visual_style = visual_style.strip()
        clamped_hook_strength_score = max(0.0, min(1.0, float(hook_strength_score)))

        signal = {
            "objects": objects,
            "scene_description": scene_description,
            "detected_text": detected_text,
            "visual_style": visual_style,
            "hook_strength_score": clamped_hook_strength_score,
        }

        return {
            "provider": "gemini",
            "status": "ok",
            "signals": [signal],
        }
    except Exception:
        return {
            "provider": "gemini",
            "status": "error",
            "signals": [],
        }


def _build_prompt(context: dict[str, Any], vision: dict[str, Any]) -> dict[str, str]:
    """Build a compact prompt requesting strictly structured JSON output."""
    return {
        "system": (
            "You are an Instagram post analyst. "
            "Return ONLY valid JSON with keys: "
            "summary (string), "
            "drivers (array of objects with id, label, type, explanation), "
            "recommendations (array of objects with id, text, impact_level). "
            "Do not include markdown, comments, or extra keys. "
            "Summary requirements: 3-5 sentences; must reference concrete values for reach and engagement_rate; "
            "must reference engagement_rate_percent_vs_avg when available; "
            "must reference percentile_engagement_rank when available; "
            "When citing metrics, reference metric keys exactly as they appear in the input JSON, including paths "
            "such as core_metrics.reach, derived_metrics.engagement_rate, "
            "benchmark_metrics.engagement_rate_percent_vs_avg, and "
            "benchmark_metrics.percentile_engagement_rank. "
            "Do not invent new metric names, aliases, or paraphrased metric keys. "
            "avoid generic statements. "
            "Driver requirements: max 5 items; each driver must include measurable reasoning tied to provided metrics "
            "and/or vision signals. "
            "Recommendation requirements: max 5 items; each must be specific, measurable, and tied to an identified "
            "gap/opportunity in the provided data; avoid generic phrases such as 'improve content quality'. "
            "Allowed driver.type values: POSITIVE or LIMITING. "
            "Allowed recommendation.impact_level values: HIGH, MEDIUM, LOW."
        ),
        "user": json.dumps(
            {
                "task": "Analyze this single post and provide concise output.",
                "context": context,
                "vision": vision,
            },
            ensure_ascii=True,
        ),
    }


async def _call_llm_async(prompt: dict[str, str], llm_client: LLMClient | None) -> str | None:
    """Call the LLM client asynchronously via a worker thread."""
    client = llm_client or LLMClient()
    try:
        return await asyncio.to_thread(client.generate, prompt)
    except (LLMClientError, Exception) as exc:
        logger.warning(f"[AIAnalysis] LLM call failed, using fallback: {exc}")
        return None


def _parse_driver_item(value: Any) -> AIDriver | None:
    """Validate and normalize one driver item."""
    if not isinstance(value, dict):
        return None
    required_keys = {"id", "label", "type", "explanation"}
    if set(value.keys()) != required_keys:
        return None

    item_id = value.get("id")
    label = value.get("label")
    driver_type = value.get("type")
    explanation = value.get("explanation")

    if not isinstance(item_id, str) or not item_id.strip():
        return None
    if not isinstance(label, str) or not label.strip():
        return None
    if driver_type not in {"POSITIVE", "LIMITING"}:
        return None
    if not isinstance(explanation, str) or not explanation.strip():
        return None

    return {
        "id": item_id.strip(),
        "label": label.strip(),
        "type": driver_type,
        "explanation": explanation.strip(),
    }


def _parse_recommendation_item(value: Any) -> AIRecommendation | None:
    """Validate and normalize one recommendation item."""
    if not isinstance(value, dict):
        return None
    required_keys = {"id", "text", "impact_level"}
    if set(value.keys()) != required_keys:
        return None

    item_id = value.get("id")
    text = value.get("text")
    impact_level = value.get("impact_level")

    if not isinstance(item_id, str) or not item_id.strip():
        return None
    if not isinstance(text, str) or not text.strip():
        return None
    if impact_level not in {"HIGH", "MEDIUM", "LOW"}:
        return None

    return {
        "id": item_id.strip(),
        "text": text.strip(),
        "impact_level": impact_level,
    }


def _parse_llm_response(
    raw_text: str | None,
) -> tuple[str | None, list[AIDriver], list[AIRecommendation]]:
    """Parse and strictly validate LLM output schema."""
    if not raw_text:
        return None, [], []

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return None, [], []

    if not isinstance(payload, dict):
        return None, [], []

    summary = payload.get("summary")
    drivers_raw = payload.get("drivers")
    recommendations_raw = payload.get("recommendations")

    if not isinstance(summary, str) or not summary.strip():
        return None, [], []
    if not isinstance(drivers_raw, list):
        return None, [], []
    if not isinstance(recommendations_raw, list):
        return None, [], []

    drivers: list[AIDriver] = []
    for item in drivers_raw:
        parsed_item = _parse_driver_item(item)
        if parsed_item is None:
            return None, [], []
        drivers.append(parsed_item)

    recommendations: list[AIRecommendation] = []
    for item in recommendations_raw:
        parsed_item = _parse_recommendation_item(item)
        if parsed_item is None:
            return None, [], []
        recommendations.append(parsed_item)

    summary = summary.strip()
    return summary, drivers, recommendations


def _fallback_summary(score: int, band: str) -> str:
    """Return deterministic fallback summary when LLM output is unavailable."""
    return f"Post scored {score}/100 ({band}) based on deterministic content signals."


async def analyze_single_post_ai(
    post: SinglePostInsights,
    llm_client: LLMClient | None = None,
) -> AIAnalysisResult:
    """Run async AI analysis for a single post with caching and regen throttling."""
    from datetime import datetime, timezone

    now_ts = time.time()
    key = _cache_key(post)
    cached = _ANALYSIS_CACHE.get(key)

    if cached is not None and _is_fresh(cached, now_ts):
        return cached.result

    if cached is not None and (now_ts - cached.last_regen_attempt_at) < MIN_REGEN_SECONDS:
        return cached.result

    score, band = _score_payload(post)

    if post.published_at is not None:
        published_at = post.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        now_utc = datetime.now(timezone.utc)
        post_age_seconds = (now_utc - published_at).total_seconds()
        if post_age_seconds < MIN_REGEN_SECONDS:
            result: AIAnalysisResult = {
                "summary": "AI analysis unavailable. Post is still accumulating data.",
                "drivers": [],
                "recommendations": [],
                "ai_content_score": score,
                "ai_content_band": band,
            }
            _ANALYSIS_CACHE[key] = _CacheEntry(
                result=result,
                cached_at=now_ts,
                last_regen_attempt_at=now_ts,
            )
            return result

    context = build_ai_input_context(post, score, band)
    vision = await run_vision_analysis(post)
    prompt = _build_prompt(context, vision)

    if cached is not None:
        cached.last_regen_attempt_at = now_ts

    llm_text = await _call_llm_async(prompt, llm_client)
    summary, drivers, recommendations = _parse_llm_response(llm_text)

    if summary is None:
        summary = _fallback_summary(score, band)
        drivers = []
        recommendations = []

    result: AIAnalysisResult = {
        "summary": summary,
        "drivers": drivers,
        "recommendations": recommendations,
        "ai_content_score": score,
        "ai_content_band": band,
    }

    _ANALYSIS_CACHE[key] = _CacheEntry(
        result=result,
        cached_at=now_ts,
        last_regen_attempt_at=now_ts,
    )
    return result
