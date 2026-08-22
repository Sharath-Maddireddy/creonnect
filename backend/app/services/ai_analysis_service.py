"""Async AI analysis service for single-post insights."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import tempfile
import threading
import time
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Literal, NotRequired, TypedDict
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from backend.app.ai.cringe_analysis import derive_cringe_label, enforce_cringe_floor
from backend.app.ai.gemini_constants import PRIMARY_GEMINI_MODEL
from backend.app.ai.prompts import S2_CAPTION_EVALUATION_PROMPT, S4_AUDIENCE_RELEVANCE_PROMPT, format_user_text_block
from backend.app.ai.toon import loads as toon_loads
from backend.app.ai.llm_client import LLMClient
from backend.app.analytics.caption_s2_engine import analyze_caption_via_llm
from backend.app.analytics.post_weighted_score_engine import compute_weighted_post_score
from backend.app.analytics.reel_analysis_service import compute_reel_analysis
from backend.app.analytics.reel_audio_engine import compute_reel_audio_score
from backend.app.analytics.reel_gemini_engine import run_reel_gemini_analysis
from backend.app.analytics.s4_audience_relevance_engine import analyze_audience_relevance_via_llm
from backend.app.analytics.s6_brand_safety_engine import compute_s6_brand_safety
from backend.app.analytics.vision_s1_engine import _as_float, compute_visual_quality_score
from backend.app.analytics.vision_s3_engine import analyze_content_clarity_via_llm
from backend.app.domain.post_models import (
    AudienceRelevanceScore,
    BrandSafetyScore,
    CaptionEffectivenessScore,
    ContentClarityScore,
    EngagementPotentialScore,
    ReelAnalysis,
    SinglePostInsights,
    VisionAnalysis,
    VisualQualityScore,
    WeightedPostScore,
)
from backend.app.infra.outbound_media import resolve_public_http_url
from backend.app.utils.logger import logger


CACHE_TTL_SECONDS = 86400
MIN_REGEN_SECONDS = 1
ANALYSIS_CACHE_MAX_ENTRIES = 1024
AI_ANALYSIS_CACHE_VERSION = "creative-v2r2"
CAROUSEL_VISION_CONCURRENCY = 3
# Bounds worst case (an all-video carousel) from turning into N full inline
# reel analyses; the common case of 1-3 video slides in an otherwise-image
# carousel is fully covered.
CAROUSEL_VIDEO_SLIDE_LIMIT = 3
VISION_MEDIA_DOWNLOAD_TIMEOUT_SECONDS = 30.0
MAX_VISION_MEDIA_BYTES = 15 * 1024 * 1024
VISION_MEDIA_MAX_REDIRECTS = 3
# Worst case inside run_reel_gemini_analysis: 30s download + 2 models x 2
# attempts each with a 35s sleep on HTTP 429 (~140s), now that the video is
# sent inline instead of through the File API upload/poll cycle. Unlike the
# image vision path, this call previously had no timeout at all, so a
# rate-limit storm could hang a synchronous /post-analysis request for
# several minutes.
REEL_VISION_TIMEOUT_SECONDS = 180.0
_VISION_MEDIA_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_DEFAULT_GEMINI_MODEL = PRIMARY_GEMINI_MODEL
_SIMPLIFIED_GEMINI_VISION_PROMPT = (
    "Analyze the provided Instagram media and return ONLY valid JSON. "
    "Do not include markdown fences or commentary. "
    "Return exactly one JSON object with keys: "
    "visual_quality_score (integer 0..10), hook_strength_score (number 0..1), "
    "primary_objects (array of strings), detected_text (string or null), lighting_feedback (string), "
    "composition_feedback (string), aesthetic_fixes (array of strings), is_cringe (boolean), "
    "adult_content_detected (boolean). If unsure about a field, use null or an empty array."
)


def _parse_timeout(env_key: str, default: float) -> float:
    raw = os.getenv(env_key, "")
    if not isinstance(raw, str) or not raw.strip():
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "[AI] Invalid %s value=%r; falling back to default timeout=%s",
            env_key,
            raw,
            default,
        )
        return default


LLM_TIMEOUT_SECONDS = _parse_timeout("LLM_TIMEOUT_SECONDS", 60.0)
_GEMINI_USE_BATCH = os.getenv("GEMINI_USE_BATCH", "").strip().lower() in {"1", "true", "yes"}
_ANALYSIS_CACHE_LOCK = threading.Lock()


class AIAnalysisResult(TypedDict):
    """Structured response returned by AI single-post analysis."""

    summary: str
    drivers: list["AIDriver"]
    recommendations: list["AIRecommendation"]
    # Backward-compatible aliases for the canonical AI creative score.
    ai_content_score: float | None
    ai_content_band: str
    creative_score: float | None
    creative_band: str
    score_source: str
    performance_score: None
    performance_score_status: str
    caption_effectiveness_score: dict[str, Any]
    visual_quality_score: dict[str, Any]
    content_clarity_score: dict[str, Any]
    engagement_potential_score: dict[str, Any]
    audience_relevance_score: dict[str, Any]
    brand_safety_score: dict[str, Any]
    weighted_post_score: dict[str, Any]
    vision_analysis: dict[str, Any]
    tier_avg_engagement_rate: float | None
    predicted_engagement_rate: float | None
    predicted_engagement_rate_notes: list[str]
    warnings: list["AIWarning"]
    vision_status: Literal["ok", "error", "disabled", "no_media"]
    fallback_used: bool
    fallback_reason: NotRequired[str | None]
    vision_error_reason: NotRequired[str | None]
    # Enhanced analytics fields (v2)
    caption_improvement: NotRequired[dict[str, str] | None]
    posting_intelligence: NotRequired[str | None]
    hashtag_quality_note: NotRequired[str | None]
    hashtag_analysis: NotRequired[dict[str, Any] | None]
    predicted_er_confidence: NotRequired[str]
    # Creator-facing enhancement fields (v3)
    cringe_summary: NotRequired[dict[str, Any] | None]
    score_explanation: NotRequired[dict[str, Any]]
    viral_opportunity: NotRequired[str | None]
    creator_next_step: NotRequired[str | None]


class AIWarning(TypedDict):
    """Structured warning payload bubbled to orchestration layer."""

    component: str
    code: Literal["GEMINI_API_KEY_MISSING", "VISION_ERROR"]
    message: str
    post_id: str | None


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
    category: str


@dataclass
class _CacheEntry:
    """Internal cache entry for AI analysis responses."""

    result: AIAnalysisResult
    cached_at: float
    last_regen_attempt_at: float


_ANALYSIS_CACHE: dict[str, _CacheEntry] = {}


@dataclass
class _VisionTextResponse:
    """Minimal response wrapper to mimic SDK objects that expose `.text`."""

    text: str


def _hash_cache_hint(value: Any) -> str:
    if not isinstance(value, str):
        return "none"
    text = value.strip()
    if not text:
        return "empty"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _sanitize_url_for_logging(url: str) -> str:
    """Return URL with query string and fragment removed for safe logging."""
    if not isinstance(url, str):
        return ""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _cache_key(post: SinglePostInsights) -> str | None:
    """Build a stable cache key for a single post."""
    account_id = post.account_id or None
    media_id = post.media_id or None
    published_at = post.published_at.isoformat() if post.published_at is not None else "unknown_time"

    if account_id and media_id:
        return f"{AI_ANALYSIS_CACHE_VERSION}:{account_id}:{media_id}:{published_at}"

    caption_hint = _hash_cache_hint(post.caption_text)
    media_hint = _hash_cache_hint(post.media_url)

    if not account_id and not media_id and caption_hint in {"none", "empty"} and media_hint in {"none", "empty"}:
        return None

    account_part = account_id or "unknown_account"
    media_part = media_id or "unknown_media"
    return f"{AI_ANALYSIS_CACHE_VERSION}:{account_part}:{media_part}:{published_at}:{caption_hint}:{media_hint}"


def _is_fresh(entry: _CacheEntry, now_ts: float) -> bool:
    """Return True when cache entry is still valid by TTL."""
    return (now_ts - entry.cached_at) <= CACHE_TTL_SECONDS


def _should_cache_analysis_result(result: AIAnalysisResult) -> bool:
    """Transient vision failures must be retried instead of cached for a day."""
    return result.get("vision_status") != "error"


def _prune_analysis_cache(now_ts: float) -> None:
    """Evict stale cache entries and enforce max cache size."""
    stale_keys = [key for key, entry in _ANALYSIS_CACHE.items() if not _is_fresh(entry, now_ts)]
    for key in stale_keys:
        _ANALYSIS_CACHE.pop(key, None)

    overflow = len(_ANALYSIS_CACHE) - ANALYSIS_CACHE_MAX_ENTRIES
    if overflow <= 0:
        return

    oldest_keys = sorted(
        _ANALYSIS_CACHE.keys(),
        key=lambda cache_key: _ANALYSIS_CACHE[cache_key].cached_at,
    )[:overflow]
    for key in oldest_keys:
        _ANALYSIS_CACHE.pop(key, None)


def _creative_score_payload(weighted_post_score: WeightedPostScore) -> tuple[float | None, str]:
    """Return the canonical AI-only creative score and creator-facing band."""
    raw_score = weighted_post_score.score
    if not isinstance(raw_score, (int, float)):
        return None, "UNAVAILABLE"

    score = round(max(0.0, min(100.0, float(raw_score))), 2)
    if score < 40.0:
        band = "OPPORTUNITY_TO_REFINE"
    elif score < 65.0:
        band = "BUILDING_MOMENTUM"
    elif score < 85.0:
        band = "STRONG_FOUNDATION"
    else:
        band = "EXCEPTIONAL"
    return score, band


def _resolve_score(attr_val: Any, cls: type) -> Any:
    "Return attr_val if already an instance of cls, else return cls()."
    return attr_val if isinstance(attr_val, cls) else cls()


def _available_audience_relevance_total(score: AudienceRelevanceScore) -> float | None:
    """Return S4 only when creator/post category context supports the score."""
    if score.status != "available":
        return None
    return score.total_0_50


def _fallback_engagement_potential_score() -> EngagementPotentialScore:
    return EngagementPotentialScore(
        emotional_resonance=5.0,
        shareability=5.0,
        save_worthiness=5.0,
        comment_potential=5.0,
        novelty_or_value=5.0,
        total=25.0,
        notes=["fallback: invalid AI output"],
    )


def _resolve_weighted_post_type(media_type: str | None) -> str:
    normalized = media_type.upper().strip() if isinstance(media_type, str) else ""
    return "REEL" if normalized == "REEL" else "IMAGE"


def _resolve_tier_avg_engagement_rate(post: SinglePostInsights) -> tuple[float | None, list[str]]:
    """Resolve tier-average ER source, preferring niche context when available."""
    notes: list[str] = []

    niche_context = getattr(post, "niche_benchmark_context", None)
    if isinstance(niche_context, dict):
        niche_avg = niche_context.get("avg_engagement_rate")
        if isinstance(niche_avg, (int, float)):
            notes.append("tier_avg_er source: niche benchmark context")
            return float(niche_avg), notes

    if isinstance(post.tier_avg_engagement_rate, (int, float)):
        notes.append("tier_avg_er source: preloaded tier_avg_engagement_rate")
        return float(post.tier_avg_engagement_rate), notes

    if post.benchmark_metrics is not None:
        account_avg = post.benchmark_metrics.account_avg_engagement_rate
        if isinstance(account_avg, (int, float)):
            notes.append("tier_avg_er source: account_avg_engagement_rate fallback")
            return float(account_avg), notes

    notes.append("missing tier_avg_er source")
    return None, notes


def _is_public_ip_address(value: str) -> bool:
    try:
        parsed = ip_address(value)
    except ValueError:
        return False
    return parsed.is_global


async def _is_safe_public_hostname(hostname: str) -> bool:
    """Async wrapper for hostname validation to avoid blocking the event loop."""
    normalized = hostname.strip().lower().rstrip(".")
    if not normalized:
        return False
    return await asyncio.to_thread(_is_safe_public_hostname_blocking, normalized)


def _is_safe_public_hostname_blocking(normalized: str) -> bool:
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return False

    if normalized.endswith((".local", ".localdomain", ".internal", ".lan", ".home", ".corp")):
        return False

    if _is_public_ip_address(normalized):
        return True

    # Block likely-internal single-label hostnames.
    if "." not in normalized:
        return False

    try:
        addr_infos = socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    resolved_ips = {info[4][0] for info in addr_infos if len(info) >= 5 and info[4]}
    if not resolved_ips:
        return False

    return all(_is_public_ip_address(ip) for ip in resolved_ips)


def _validate_public_vision_url(value: str) -> str:
    """Validate one outbound inline-vision URL before opening a connection."""
    parsed = urlparse(value)
    hostname = parsed.hostname
    if (
        parsed.scheme not in {"http", "https"}
        or not isinstance(hostname, str)
        or not hostname.strip()
        or parsed.username is not None
        or parsed.password is not None
        or not _is_safe_public_hostname_blocking(hostname.strip().lower().rstrip("."))
    ):
        raise ValueError("Vision media URL must resolve to a public HTTP or HTTPS host")
    return value


def build_ai_input_context(
    post: SinglePostInsights,
    visual_quality_score: VisualQualityScore,
    content_clarity_score: ContentClarityScore,
    caption_effectiveness_score: CaptionEffectivenessScore,
    audience_relevance_score: AudienceRelevanceScore,
    brand_safety_score: BrandSafetyScore,
    weighted_post_score: WeightedPostScore,
) -> dict[str, Any]:
    """Build AI-only creative context without observed performance metrics."""
    import re

    # --- Temporal signals ---
    posting_weekday: str | None = None
    posting_hour_utc: int | None = None
    if post.published_at is not None:
        try:
            posting_weekday = post.published_at.strftime("%A")
            posting_hour_utc = post.published_at.hour
        except Exception:
            pass

    # --- Hashtag signals ---
    caption = post.caption_text or ""
    hashtag_list = re.findall(r"#\w+", caption)
    hashtag_count = len(hashtag_list)

    # --- Score gap analysis (deterministic) ---
    score_components: dict[str, float | None] = {
        "S1_visual_quality": visual_quality_score.total,
        "S2_caption_effectiveness": caption_effectiveness_score.total_0_50,
        "S3_content_clarity": content_clarity_score.total,
        "S4_audience_relevance": _available_audience_relevance_total(audience_relevance_score),
        "S6_brand_safety": brand_safety_score.total_0_50,
    }
    available_scores = {k: v for k, v in score_components.items() if isinstance(v, (int, float))}
    weakest_dimension: str | None = min(available_scores, key=available_scores.__getitem__) if available_scores else None
    strongest_dimension: str | None = max(available_scores, key=available_scores.__getitem__) if available_scores else None

    # --- Niche context ---
    niche_benchmark_context = getattr(post, "niche_benchmark_context", None) or {}
    creator_dominant_category = getattr(post, "creator_dominant_category", None)
    post_category = getattr(post, "post_category", None)

    creative_score, creative_band = _creative_score_payload(weighted_post_score)

    return {
        "account_id": post.account_id,
        "media_id": post.media_id,
        "media_type": post.media_type,
        "caption_text": post.caption_text,
        "published_at": post.published_at.isoformat() if post.published_at is not None else None,
        "posting_weekday": posting_weekday,
        "posting_hour_utc": posting_hour_utc,
        "hashtag_count": hashtag_count,
        "hashtag_sample": hashtag_list[:10],
        "creator_dominant_category": creator_dominant_category,
        "post_category": post_category,
        "niche_benchmark_context": niche_benchmark_context,
        "preliminary_creative_score": creative_score,
        "preliminary_creative_band": creative_band,
        "preliminary_score_source": "ai_creative_weighted_score_without_s5",
        "performance_metrics_used": False,
        "s1_visual_quality": visual_quality_score.model_dump(),
        "s2_caption_effectiveness": caption_effectiveness_score.model_dump(),
        "s3_content_clarity": content_clarity_score.model_dump(),
        "s4_audience_relevance": (
            audience_relevance_score.model_dump()
            if audience_relevance_score.status == "available"
            else {
                "status": "unavailable",
                "unavailable_reason": audience_relevance_score.unavailable_reason,
                "post_category": audience_relevance_score.post_category,
                "creator_dominant_category": audience_relevance_score.creator_dominant_category,
            }
        ),
        "s6_brand_safety": brand_safety_score.model_dump(),
        "weighted_post_score": weighted_post_score.model_dump(),
        "score_gap_analysis": {
            "weakest_dimension": weakest_dimension,
            "strongest_dimension": strongest_dimension,
            "all_scores_0_50": available_scores,
        },
    }


def _clamp_int_0_100(value: Any) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(max(0.0, min(100.0, round(numeric))))


def _normalize_short_text_list(value: Any, limit: int = 3) -> list[str]:
    values = value if isinstance(value, list) else [value]
    sanitized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        sanitized.append(text[:160])
        if len(sanitized) >= limit:
            break
    return sanitized


def _normalize_optional_text(value: Any, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:limit]


def _normalize_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
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
    return None


def _normalize_production_level(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized not in {"low", "medium", "high"}:
        return None
    return normalized


_VQ_KEYS = ("composition", "lighting", "subject_clarity", "aesthetic_quality")


def _clamp_vq(raw: Any) -> dict[str, float] | None:
    numeric = _as_float(raw)
    if numeric is not None:
        v = max(0.0, min(10.0, float(numeric)))
        return {k: v for k in _VQ_KEYS}
    if isinstance(raw, dict):
        vals = [_as_float(raw.get(k)) for k in _VQ_KEYS]
        if any(v is None for v in vals):
            return None
        return {k: max(0.0, min(10.0, float(v))) for k, v in zip(_VQ_KEYS, vals)}
    return None


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) > 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_object_response(raw_text: str) -> dict[str, Any]:
    stripped_raw_text = _strip_markdown_fences(raw_text)
    if not stripped_raw_text:
        raise ValueError("LLM response was empty.")
    try:
        if "{" in stripped_raw_text and "}" in stripped_raw_text:
            start = stripped_raw_text.find("{")
            end = stripped_raw_text.rfind("}") + 1
            return json.loads(stripped_raw_text[start:end])
    except Exception:
        pass
    payload = toon_loads(stripped_raw_text)
    if not isinstance(payload, dict):
        raise ValueError("LLM output must be an object.")
    return payload


def _parse_gemini_payload(raw_text: str) -> dict[str, Any]:
    payload = _parse_object_response(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("Gemini output must be an object.")
    return payload


def _extract_cringe_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "score": _clamp_int_0_100(payload.get("cringe_score")),
        "signals": _normalize_short_text_list(payload.get("cringe_signals"), limit=3),
        "fixes": _normalize_short_text_list(payload.get("cringe_fixes"), limit=3),
    }


def _build_vision_signal(payload: dict[str, Any], *, media_url: str) -> dict[str, Any]:
    primary_objects_raw = payload.get("primary_objects")
    objects = primary_objects_raw if isinstance(primary_objects_raw, list) and primary_objects_raw else payload.get("objects") or []
    dominant_focus = payload.get("dominant_focus")
    scene_description = payload.get("scene_description") or ""
    detected_text = payload.get("detected_text")
    visual_style = payload.get("visual_style") or "Unknown"
    scene_type = payload.get("scene_type")
    visual_quality_score = payload.get("visual_quality_score") or {}
    lighting_feedback = _normalize_optional_text(payload.get("lighting_feedback"))
    composition_feedback = _normalize_optional_text(payload.get("composition_feedback"))
    aesthetic_fixes = _normalize_short_text_list(payload.get("aesthetic_fixes"), limit=3)
    technical_flaws = _normalize_short_text_list(payload.get("technical_flaws"), limit=3)
    if lighting_feedback:
        technical_flaws.append(lighting_feedback)
    if composition_feedback:
        technical_flaws.append(composition_feedback)
    technical_flaws = technical_flaws[:3]
    hook_strength_score = payload.get("hook_strength_score")
    virality_potential = payload.get("virality_potential")

    if not isinstance(objects, list):
        objects = []
    if dominant_focus is not None and not isinstance(dominant_focus, str):
        raise ValueError("Invalid dominant_focus field.")
    if detected_text is not None and not isinstance(detected_text, str):
        if isinstance(detected_text, list):
            detected_text = ", ".join(str(x) for x in detected_text)
        else:
            detected_text = str(detected_text)
    if scene_type is not None and not isinstance(scene_type, str):
        raise ValueError("Invalid scene_type field.")
    if not isinstance(hook_strength_score, (int, float)):
        hook_strength_score = 0.5
    if not isinstance(virality_potential, (int, float)):
        virality_potential = 5.0

    objects = [item.strip() for item in objects if isinstance(item, str) and item.strip()]
    dominant_focus = dominant_focus.strip() if isinstance(dominant_focus, str) else None
    scene_description = scene_description.strip() if isinstance(scene_description, str) else ""
    detected_text = detected_text.strip() if detected_text else None
    visual_style = visual_style.strip() if isinstance(visual_style, str) else "Unknown"
    scene_type = scene_type.strip() if isinstance(scene_type, str) else None

    normalized_visual_quality = _clamp_vq(visual_quality_score)
    clamped_hook_strength_score = max(0.0, min(1.0, float(hook_strength_score)))
    clamped_virality = max(0.0, min(10.0, float(virality_potential)))
    dominant_object = payload.get("dominant_object")
    lighting_quality = normalized_visual_quality.get("lighting") if isinstance(normalized_visual_quality, dict) else None
    subject_clarity = (
        normalized_visual_quality.get("subject_clarity") if isinstance(normalized_visual_quality, dict) else None
    )
    aesthetic_quality = (
        normalized_visual_quality.get("aesthetic_quality") if isinstance(normalized_visual_quality, dict) else None
    )
    cringe_score = _clamp_int_0_100(payload.get("cringe_score"))
    cringe_signals = _normalize_short_text_list(payload.get("cringe_signals"), limit=3)
    cringe_fixes = _normalize_short_text_list(payload.get("cringe_fixes"), limit=3)
    if not cringe_fixes:
        cringe_fixes = _normalize_short_text_list(payload.get("fixes_to_reduce_cringe"), limit=3)
    if not cringe_fixes and aesthetic_fixes:
        cringe_fixes = aesthetic_fixes[:]
    production_level = _normalize_production_level(payload.get("production_level"))
    adult_content_detected = _normalize_optional_bool(payload.get("adult_content_detected"))
    is_cringe_raw = _normalize_optional_bool(payload.get("is_cringe"))

    if cringe_score is not None:
        floored_score = enforce_cringe_floor(cringe_score, cringe_signals)
        cringe_score = floored_score
    elif is_cringe_raw is True:
        cringe_score = 60
    elif is_cringe_raw is False:
        cringe_score = 20
    cringe_label = derive_cringe_label(cringe_score)
    is_cringe = bool(cringe_score is not None and cringe_score >= 45) if is_cringe_raw is None else is_cringe_raw

    return {
        "objects": objects,
        "primary_objects": objects,
        "scene_description": scene_description,
        "detected_text": detected_text,
        "visual_style": visual_style,
        "hook_strength_score": clamped_hook_strength_score,
        "virality_potential": clamped_virality,
        "dominant_focus": dominant_focus,
        "dominant_object": dominant_object,
        "scene_type": scene_type,
        "lighting_quality": lighting_quality,
        "subject_clarity": subject_clarity,
        "aesthetic_quality": aesthetic_quality,
        "lighting_feedback": lighting_feedback,
        "composition_feedback": composition_feedback,
        "aesthetic_fixes": aesthetic_fixes,
        "visual_quality_score": normalized_visual_quality,
        "technical_flaws": technical_flaws,
        "cringe_score": cringe_score,
        "cringe_signals": cringe_signals,
        "cringe_fixes": cringe_fixes,
        "production_level": production_level,
        "is_cringe": is_cringe if cringe_score is not None else None,
        "cringe_label": cringe_label,
        "adult_content_detected": adult_content_detected,
    }


async def _retry_parse_with_retry_only(
    *,
    generate_fn: Any,
    api_key: str,
    instruction: str,
    media_url: str,
    provider_label: str,
    post_id: str | None,
) -> dict[str, Any]:
    parse_errors: list[str] = []
    raw_text = await generate_fn(api_key=api_key, instruction=instruction, media_url=media_url)
    try:
        return _build_vision_signal(_parse_gemini_payload(raw_text), media_url=media_url)
    except Exception as primary_exc:
        parse_errors.append(f"primary={primary_exc}")

    retry_raw_text = await generate_fn(
        api_key=api_key,
        instruction=_SIMPLIFIED_GEMINI_VISION_PROMPT,
        media_url=media_url,
    )
    try:
        signal = _build_vision_signal(_parse_gemini_payload(retry_raw_text), media_url=media_url)
        logger.info("[Vision] Simplified prompt recovered %s output for media_id=%s", provider_label, post_id)
        return signal
    except Exception as retry_exc:
        parse_errors.append(f"simplified={retry_exc}")

    raise ValueError("; ".join(parse_errors) or f"{provider_label} output could not be parsed.")


async def run_vision_analysis(
    post: SinglePostInsights,
) -> dict[str, Any]:
    """Run vision analysis for a post media URL with JSON-first parsing."""
    post_id = post.media_id if isinstance(post.media_id, str) else None
    media_type_upper = str(getattr(post, "media_type", "IMAGE") or "IMAGE").upper()
    _is_reel = media_type_upper == "REEL"
    media_type_context = (
        "This is a REEL (short-form video). "
        "Pay special attention to: the hook frame (first 1-3 seconds), pacing and cut rhythm, "
        "audio-visual sync, loop-ability, and whether the opening frame would stop a scroll. "
        "Watch the entire video before scoring."
        if _is_reel else
        "This is a static IMAGE or carousel post. "
        "Pay special attention to: scroll-stop power of the thumbnail, color palette harmony, "
        "whether a single subject dominates the frame, and save-worthiness of the visual information."
    )
    instruction = (
        "You are a world-class Instagram visual strategist and content director. "
        f"{media_type_context} "
        "Your analysis must be specific, honest, and immediately actionable — "
        "as if you are giving feedback to a creator who wants to maximize reach and engagement.\n\n"
        "Return ONLY one valid JSON object. Do not include markdown fences or commentary.\n\n"
        "Required JSON keys:\n"
        "{\n"
        '  "visual_quality_score": {"composition": number, "lighting": number, "subject_clarity": number, "aesthetic_quality": number} | number,\n'
        '  "hook_strength_score": number,\n'
        '  "virality_potential": number,\n'
        '  "primary_objects": string[],\n'
        '  "dominant_focus": string | null,\n'
        '  "scene_type": string | null,\n'
        '  "visual_style": string | null,\n'
        '  "scene_description": string | null,\n'
        '  "detected_text": string | null,\n'
        '  "lighting_feedback": string | null,\n'
        '  "composition_feedback": string | null,\n'
        '  "aesthetic_fixes": string[],\n'
        '  "technical_flaws": string[],\n'
        '  "cringe_score": number | null,\n'
        '  "cringe_signals": string[],\n'
        '  "cringe_fixes": string[],\n'
        '  "production_level": "low" | "medium" | "high" | null,\n'
        '  "is_cringe": boolean | null,\n'
        '  "adult_content_detected": boolean | null\n'
        "}\n"
    )

    media_url = post.media_url
    if not isinstance(media_url, str) or not media_url.strip():
        return VisionAnalysis(provider="gemini", status="no_media", signals=[]).model_dump(mode="python")

    carousel_urls = post.carousel_media_urls if isinstance(post.carousel_media_urls, list) else []
    if media_type_upper == "CAROUSEL" and carousel_urls:
        semaphore = asyncio.Semaphore(CAROUSEL_VISION_CONCURRENCY)

        # Video slides were previously forced through the image downloader
        # (media_type hardcoded to IMAGE for every slide), which rejects
        # video/mp4 outright. That failure was silent to the caller: a
        # carousel with e.g. 3 of 8 slides being video returned status="ok"
        # with no indication a third of the post was never analyzed. Video
        # slides are now routed through the same inline reel-vision path as
        # single-post reels, capped so one video-heavy carousel can't turn
        # into CAROUSEL_VIDEO_SLIDE_LIMIT full video analyses.
        errors: list[str] = []
        slide_media_types: dict[int, str] = {}
        video_slide_count = 0
        for index, url in enumerate(carousel_urls, start=1):
            if _infer_mime_type(url) == "video/mp4":
                video_slide_count += 1
                if video_slide_count > CAROUSEL_VIDEO_SLIDE_LIMIT:
                    errors.append(
                        f"slide {index}: skipped -- carousel video slide limit "
                        f"({CAROUSEL_VIDEO_SLIDE_LIMIT}) reached"
                    )
                    continue
                slide_media_types[index] = "REEL"
            else:
                slide_media_types[index] = "IMAGE"

        analyzed_indices = list(slide_media_types.keys())

        async def _analyse_slide(index: int, url: str) -> dict[str, Any]:
            async with semaphore:
                slide_post = post.model_copy(
                    update={"media_url": url, "media_type": slide_media_types[index], "carousel_media_urls": []}
                )
                return await run_vision_analysis(slide_post)

        slide_results = await asyncio.gather(
            *[_analyse_slide(index, carousel_urls[index - 1]) for index in analyzed_indices],
            return_exceptions=True,
        )
        slide_signals: list[dict[str, Any]] = []
        providers: list[str] = []
        for index, result in zip(analyzed_indices, slide_results):
            if isinstance(result, Exception):
                errors.append(f"slide {index}: {result}")
                continue
            if not isinstance(result, dict):
                errors.append(f"slide {index}: invalid vision response")
                continue
            provider = result.get("provider")
            if isinstance(provider, str):
                providers.append(provider)
            signals = result.get("signals")
            if isinstance(signals, list) and signals and isinstance(signals[0], dict):
                signal = dict(signals[0])
                signal["slide_index"] = index
                signal["is_carousel_aggregate"] = False
                slide_signals.append(signal)
            else:
                errors.append(f"slide {index}: {result.get('error_reason') or result.get('status') or 'no signal'}")

        if not slide_signals:
            failure_payload = VisionAnalysis(provider="gemini", status="error", signals=[]).model_dump(mode="python")
            failure_payload["error_reason"] = "; ".join(errors)[:300]
            failure_payload["slide_coverage"] = {"analyzed": 0, "submitted": len(carousel_urls)}
            return failure_payload

        numeric_keys = ("hook_strength_score", "virality_potential", "subject_clarity", "aesthetic_quality")
        aggregate: dict[str, Any] = {
            "slide_index": 0,
            "is_carousel_aggregate": True,
            "objects": list(dict.fromkeys(obj for signal in slide_signals for obj in signal.get("objects", []) if isinstance(obj, str)))[:20],
            "primary_objects": list(dict.fromkeys(obj for signal in slide_signals for obj in signal.get("primary_objects", []) if isinstance(obj, str)))[:20],
            "scene_description": f"Carousel summary across {len(slide_signals)} of {len(carousel_urls)} submitted slides.",
            "technical_flaws": list(dict.fromkeys(item for signal in slide_signals for item in signal.get("technical_flaws", []) if isinstance(item, str)))[:12],
            "aesthetic_fixes": list(dict.fromkeys(item for signal in slide_signals for item in signal.get("aesthetic_fixes", []) if isinstance(item, str)))[:12],
            "cringe_signals": list(dict.fromkeys(item for signal in slide_signals for item in signal.get("cringe_signals", []) if isinstance(item, str)))[:12],
            "cringe_fixes": list(dict.fromkeys(item for signal in slide_signals for item in signal.get("cringe_fixes", []) if isinstance(item, str)))[:12],
        }
        for key in numeric_keys:
            values = [float(signal[key]) for signal in slide_signals if isinstance(signal.get(key), (int, float))]
            if values:
                aggregate[key] = round(sum(values) / len(values), 2)
        visual_scores = [signal.get("visual_quality_score") for signal in slide_signals if isinstance(signal.get("visual_quality_score"), dict)]
        if visual_scores:
            score_keys = set().union(*(score.keys() for score in visual_scores))
            aggregate["visual_quality_score"] = {
                key: round(sum(float(score[key]) for score in visual_scores if isinstance(score.get(key), (int, float))) / sum(1 for score in visual_scores if isinstance(score.get(key), (int, float))), 2)
                for key in score_keys
                if any(isinstance(score.get(key), (int, float)) for score in visual_scores)
            }
        cringe_values = [float(signal["cringe_score"]) for signal in slide_signals if isinstance(signal.get("cringe_score"), (int, float))]
        if cringe_values:
            aggregate["cringe_score"] = round(sum(cringe_values) / len(cringe_values))
        aggregate["is_cringe"] = any(signal.get("is_cringe") is True for signal in slide_signals)
        aggregate["adult_content_detected"] = any(signal.get("adult_content_detected") is True for signal in slide_signals)
        payload = VisionAnalysis(
            provider=providers[0] if providers else "gemini",
            status="ok",
            signals=[aggregate, *slide_signals],
            error_reason="; ".join(errors)[:300] if errors else None,
        ).model_dump(mode="python")
        if len(slide_signals) < len(carousel_urls):
            payload["slide_coverage"] = {"analyzed": len(slide_signals), "submitted": len(carousel_urls)}
        return payload

    parsed_url = urlparse(media_url)
    hostname = parsed_url.hostname
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or not isinstance(hostname, str)
        or not await _is_safe_public_hostname(hostname)
    ):
        return VisionAnalysis(provider="gemini", status="no_media", signals=[]).model_dump(mode="python")

    api_key = os.getenv("GEMINI_API_KEY")

    # Video URLs cannot be passed to the inline image adapter below.  Route
    # Reels through Gemini's File API, then adapt its video signals to the
    # canonical vision shape used by the rest of this report.
    if _is_reel:
        if not isinstance(api_key, str) or not api_key.strip():
            failure_payload = VisionAnalysis(provider="gemini", status="error", signals=[]).model_dump(mode="python")
            failure_payload["error_reason"] = "GEMINI_API_KEY missing"
            return failure_payload
        try:
            reel_result = await asyncio.wait_for(
                asyncio.to_thread(run_reel_gemini_analysis, media_url),
                timeout=REEL_VISION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            failure_payload = VisionAnalysis(provider="gemini", status="error", signals=[]).model_dump(mode="python")
            failure_payload["error_reason"] = f"Reel vision timed out after {REEL_VISION_TIMEOUT_SECONDS:.0f}s"
            failure_payload["raw_reel_signals"] = {}
            return failure_payload
        reel_status = str(reel_result.get("status") or "error")
        reel_signals = reel_result.get("signals")
        if reel_status == "ok" and isinstance(reel_signals, dict):
            normalized_reel_signals = dict(reel_signals)
            normalized_reel_signals["hook_strength_score"] = reel_signals.get("hook_frame_score")
            # retention_signal is 0..1; virality_potential expects a 0..10 scale.
            raw_retention = reel_signals.get("retention_signal")
            normalized_reel_signals["virality_potential"] = (
                float(raw_retention) * 10.0 if isinstance(raw_retention, (int, float)) else 5.0
            )
            signal = _build_vision_signal(normalized_reel_signals, media_url=media_url)
            payload = VisionAnalysis(provider="gemini", status="ok", signals=[signal]).model_dump(mode="python")
            # Preserve the raw reel-specific fields (pacing_label, hook_frame_score,
            # retention_signal, ...) that _build_vision_signal's generic image shape
            # discards, so the dedicated reel scoring engine can use them.
            payload["raw_reel_signals"] = reel_signals
            return payload
        failure_payload = VisionAnalysis(provider="gemini", status="error", signals=[]).model_dump(mode="python")
        error = reel_result.get("error")
        failure_payload["error_reason"] = str(error or f"Reel Gemini status={reel_status}")[:300]
        failure_payload["raw_reel_signals"] = reel_signals if isinstance(reel_signals, dict) else {}
        return failure_payload

    try:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("GEMINI_API_KEY missing")
        signal = await _retry_parse_with_retry_only(
            generate_fn=_generate_gemini_vision_json,
            api_key=api_key,
            instruction=instruction,
            media_url=media_url,
            provider_label="Gemini",
            post_id=post_id,
        )
        return VisionAnalysis(provider="gemini", status="ok", signals=[signal]).model_dump(mode="python")
    except Exception as gemini_exc:
        gemini_error_reason = str(gemini_exc).strip() or gemini_exc.__class__.__name__

        if "SAFETY_BLOCK" in gemini_error_reason:
            synthetic_signal = {
                "objects": [],
                "primary_objects": [],
                "scene_description": "Content blocked by AI safety filters.",
                "detected_text": None,
                "visual_style": None,
                "hook_strength_score": 0.0,
                "virality_potential": 0,
                "dominant_focus": None,
                "dominant_object": None,
                "scene_type": None,
                "lighting_quality": None,
                "subject_clarity": None,
                "aesthetic_quality": None,
                "visual_quality_score": None,
                "technical_flaws": [],
                "cringe_score": 100,
                "cringe_signals": ["safety_filter_blocked", "unsafe_content"],
                "cringe_fixes": [],
                "production_level": "low",
                "is_cringe": True,
                "cringe_label": "unsafe",
                "adult_content_detected": True,
            }
            return VisionAnalysis(provider="gemini", status="ok", signals=[synthetic_signal]).model_dump(mode="python")

        # LLMClient supports both direct OpenAI and Azure OpenAI.  The product
        # commonly runs with Azure credentials only, so requiring a direct
        # OPENAI_API_KEY here left the image fallback permanently unreachable.
        # A non-empty sentinel is sufficient on the Azure path because
        # _OpenAIVisionAdapter delegates authentication to LLMClient.
        direct_openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        openai_api_key = direct_openai_api_key or (
            azure_openai_api_key if azure_openai_endpoint and azure_openai_api_key else ""
        )
        mime_type = _infer_mime_type(media_url)
        if openai_api_key and mime_type.startswith("image/"):
            try:
                openai_signal = await _retry_parse_with_retry_only(
                    generate_fn=_generate_openai_vision_json,
                    api_key=openai_api_key,
                    instruction=instruction,
                    media_url=media_url,
                    provider_label="OpenAI",
                    post_id=post_id,
                )
                return VisionAnalysis(provider="openai", status="ok", signals=[openai_signal]).model_dump(mode="python")
            except Exception as openai_exc:
                # Preserve both provider failures; this is shown in job
                # diagnostics and makes a bad media URL distinguishable from
                # a provider/configuration problem.
                gemini_error_reason = (
                    f"Gemini: {gemini_error_reason}; "
                    f"Azure/OpenAI fallback: {str(openai_exc).strip() or openai_exc.__class__.__name__}"
                )

        failure_payload = VisionAnalysis(provider="openai", status="error", signals=[]).model_dump(mode="python")
        failure_payload["error_reason"] = gemini_error_reason[:300]
        return failure_payload


def _infer_mime_type(url: str) -> str:
    from urllib.parse import urlparse, parse_qs
    
    url_lower = url.lower()
    parsed = urlparse(url_lower)
    qs = parse_qs(parsed.query)
    filename = qs["filename"][0] if "filename" in qs and qs["filename"] else ""
    path = parsed.path
    if filename.endswith(".mp4") or path.endswith(".mp4") or ".mp4" in url_lower:
        return "video/mp4"
    return "image/jpeg"


def _download_vision_media(media_url: str) -> tuple[bytes, str]:
    """Download public image media with validated, bounded redirects."""
    current_url = media_url
    remaining_redirects = VISION_MEDIA_MAX_REDIRECTS
    with httpx.Client(
        timeout=VISION_MEDIA_DOWNLOAD_TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
        limits=httpx.Limits(max_keepalive_connections=0),
    ) as client:
        while True:
            # Preserve this service's established validation error contract;
            # the shared resolver below additionally produces the pinned IP.
            _validate_public_vision_url(current_url)
            target = resolve_public_http_url(current_url, field_name="Vision media URL")
            current_url = target.public_url
            with client.stream(
                "GET",
                target.connect_url,
                headers=target.request_headers,
                extensions=target.request_extensions,
            ) as response:
                if response.status_code in _VISION_MEDIA_REDIRECT_STATUSES:
                    if remaining_redirects <= 0:
                        raise ValueError(
                            f"Vision media exceeded {VISION_MEDIA_MAX_REDIRECTS} redirects"
                        )
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Vision media redirect is missing a Location header")
                    current_url = urljoin(current_url, location)
                    remaining_redirects -= 1
                    continue

                response.raise_for_status()
                mime_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                    raise ValueError(f"Unsupported vision media type: {mime_type or 'unknown'}")

                chunks: list[bytes] = []
                total_bytes = 0
                for chunk in response.iter_bytes(65536):
                    chunks.append(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > MAX_VISION_MEDIA_BYTES:
                        raise ValueError("Vision media exceeds the 15 MB limit")
                break

    media_bytes = b"".join(chunks)
    if not media_bytes:
        raise ValueError("Vision media download returned no bytes")
    return media_bytes, mime_type


def _build_gemini_vision_adapter():
    try:
        from google import genai
        from google.genai import types as genai_types
        if not hasattr(genai, "Client") or not hasattr(genai_types, "Part"):
            raise ImportError("google-genai client is unavailable")
        class _GoogleGenaiVisionAdapter:
            def __init__(self, api_key: str) -> None:
                self._client = genai.Client(api_key=api_key)
            def generate_content(self, *, model_name: str, instruction: str, media_bytes: bytes, mime_type: str):
                image_part = genai_types.Part.from_bytes(data=media_bytes, mime_type=mime_type)
                return self._client.models.generate_content(
                    model=model_name,
                    contents=[instruction, image_part],
                    # Deterministic scoring: default temperature (1.0) causes
                    # large run-to-run score swings for identical images.
                    config=genai_types.GenerateContentConfig(temperature=0),
                )
            def generate_text(self, *, model_name: str, prompt: str):
                return self._client.models.generate_content(model=model_name, contents=prompt)
        return _GoogleGenaiVisionAdapter
    except ImportError:
        import google.generativeai as legacy_genai
        class _LegacyGenaiVisionAdapter:
            def __init__(self, api_key: str) -> None:
                legacy_genai.configure(api_key=api_key)
            def generate_content(self, *, model_name: str, instruction: str, media_bytes: bytes, mime_type: str):
                generation_config = legacy_genai.types.GenerationConfig(temperature=0)
                return legacy_genai.GenerativeModel(model_name).generate_content(
                    [instruction, {"mime_type": mime_type, "data": media_bytes}],
                    generation_config=generation_config,
                )
            def generate_text(self, *, model_name: str, prompt: str):
                return legacy_genai.GenerativeModel(model_name).generate_content(prompt)
        return _LegacyGenaiVisionAdapter


class _OpenAIVisionAdapter:
    def __init__(self, api_key: str) -> None:
        from backend.app.ai.llm_client import LLMClient
        self._client = LLMClient().client
    def generate_content(self, *, model_name: str, instruction: str, media_url: str, mime_type: str) -> _VisionTextResponse:
        request_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": [{"type": "text", "text": instruction}, {"type": "image_url", "image_url": {"url": media_url}}]}],
            "response_format": {"type": "json_object"},
        }
        # Reasoning models (o1/gpt-5.6 family) reject an explicit temperature.
        if "5.6" not in model_name and "o1" not in model_name:
            request_kwargs["temperature"] = 0
        response = self._client.chat.completions.create(**request_kwargs)
        return _VisionTextResponse(text=(response.choices[0].message.content or "").strip())


def _call_gemini_vision_api(*, api_key: str, instruction: str, media_url: str) -> str:
    model_name = os.getenv("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)
    media_bytes, mime_type = _download_vision_media(media_url)
    client = _build_gemini_vision_adapter()(api_key=api_key)
    response = client.generate_content(
        model_name=model_name,
        instruction=instruction,
        media_bytes=media_bytes,
        mime_type=mime_type,
    )
    text = getattr(response, "text", None)
    if not isinstance(text, str):
        raise ValueError("Gemini response missing text.")
    return text


def _call_openai_vision_api(*, api_key: str, instruction: str, media_url: str) -> str:
    client = _OpenAIVisionAdapter(api_key=api_key)
    model_name = os.getenv("LLM_MODEL_NAME", "gpt-4o")
    response = client.generate_content(model_name=model_name, instruction=instruction, media_url=media_url, mime_type="image/jpeg")
    return response.text


def _call_openai_text_api(*, api_key: str, prompt: str) -> str:
    from backend.app.ai.llm_client import LLMClient
    client = LLMClient().client
    model = os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")
    response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
    return (response.choices[0].message.content or "").strip()


def _call_gemini_text_api(*, api_key: str, prompt: str) -> str:
    client = _build_gemini_vision_adapter()(api_key=api_key)
    response = client.generate_text(model_name=os.getenv("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL), prompt=prompt)
    return getattr(response, "text", "")


async def _generate_gemini_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
    return await asyncio.wait_for(asyncio.to_thread(_call_gemini_vision_api, api_key=api_key, instruction=instruction, media_url=media_url), timeout=120.0)


async def _generate_openai_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
    return await asyncio.wait_for(asyncio.to_thread(_call_openai_vision_api, api_key=api_key, instruction=instruction, media_url=media_url), timeout=120.0)


def _build_prompt(context: dict[str, Any], vision: dict[str, Any]) -> dict[str, Any]:
    """Build a richer prompt requesting structured TOON output with v3 analytics fields."""
    media_type = str(context.get("media_type") or "IMAGE").upper()
    content_type_note = (
        "This is a REEL (video). Evaluate creative proxies such as the opening hook, pacing, "
        "audio alignment, visual progression, and loop-ability. Do not claim observed watch time or retention."
        if media_type == "REEL" else
        "This is an IMAGE post. Consider carousel potential, caption depth, save-worthiness, "
        "color pop, and scroll-stop visual power when evaluating engagement potential and giving recommendations."
    )
    weakest = context.get("score_gap_analysis", {}).get("weakest_dimension") or "unknown"
    strongest = context.get("score_gap_analysis", {}).get("strongest_dimension") or "unknown"
    return {
        "system": (
            "You are a world-class Instagram growth strategist and content analyst. "
            f"{content_type_note} "
            "Your output must feel like premium, personalized coaching — specific, grounded in the data, "
            "and immediately actionable. Never use vague advice like 'improve content quality'. "
            "Return ONLY one valid JSON object and no markdown. "
            "Return exactly these top-level keys: "
            "summary, drivers, recommendations, engagement_potential_score, "
            "caption_improvement, posting_intelligence, hashtag_quality_note, "
            "hashtag_analysis, viral_opportunity, creator_next_step. "
            "The exact field names below are a strict machine-readable contract — "
            "any other field names for drivers/recommendations/caption_improvement "
            "will cause your entire response to be discarded and replaced with a generic fallback, "
            "so match them exactly, do not rename, add, or omit fields. "
            "Summary: FIRST sentence must cite at least two available S1-S6 creative-signal values. "
            "Do not state an overall score; the backend calculates the final score after your S5 output. "
            "Do not mention or infer likes, comments, views, reach, saves, shares, watch time, retention rate, "
            "engagement rate, follower growth, audience demographics, or predicted post performance; none of those "
            "are inputs to this AI-only creative report. "
            f"Identify the highest-leverage opportunity ({weakest}) and explain how strengthening it can lift the result. "
            f"Mention strongest dimension ({strongest}). 3-5 sentences total. "
            "drivers: a list of up to 5 objects, each with EXACTLY these keys: "
            '"id" (short slug string), "label" (short title string), '
            '"type" (must be exactly "POSITIVE" or "LIMITING"), '
            '"explanation" (1 sentence referencing a specific metric value or vision signal). '
            "recommendations: a list of 5 to 7 objects, each with EXACTLY these keys: "
            '"id" (short slug string), "text" (specific, non-generic action), '
            '"impact_level" (must be exactly "HIGH", "MEDIUM", or "LOW"), '
            '"category" (must be exactly one of "CAPTION", "VISUAL", "TIMING", "HASHTAGS", "ENGAGEMENT"). '
            "engagement_potential_score: an object (not a single number) with EXACTLY these keys, "
            "each a number from 0 to 10 based on this post's specific content: "
            '"emotional_resonance", "shareability", "save_worthiness", "comment_potential", "novelty_or_value", '
            'plus "total" (the sum of those 5 values, 0 to 50) and "notes" (a list of up to 3 short strings). '
            "This score is an AI-estimated creative-potential signal, not observed or predicted performance. "
            "caption_improvement: an object with EXACTLY these keys: "
            '"hook_rewrite" (1-sentence rewritten hook string) and "cta_rewrite" (1-sentence improved CTA string). '
            "posting_intelligence: 1-sentence comment on optimal timing. "
            "hashtag_analysis: quality_band (Excellent|Good|Building Momentum|Opportunity to Refine), suggested_count (int), strategy_tip (str). "
            "viral_opportunity: 2 sentences on viral potential and amplification mechanics. "
            "creator_next_step: single sentence on highest-priority action based on "
            f"highest-leverage opportunity ({weakest}). Use constructive, specific language; never say 'needs work', 'weak', 'poor', or 'underperforming'."
        ),
        "user": json.dumps(
            {
                "task": "Analyze this single post and provide premium, creator-specific output.",
                "context": context,
                "vision": vision,
            },
            ensure_ascii=True,
        ),
        "response_format": {"type": "json_object"},
    }


async def _call_llm_async(prompt: dict[str, Any], llm_client: LLMClient | None) -> str | None:
    """Call the LLM client asynchronously via a worker thread."""
    client = llm_client or LLMClient()
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(client.generate, prompt),
            timeout=LLM_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("[AIAnalysis] LLM call timed out, using fallback")
        return None
    except Exception as exc:
        logger.warning(f"[AIAnalysis] LLM call failed, using fallback: {exc}")
        return None


async def run_caption_analysis_llm(caption_text: str, llm_client: LLMClient | None = None) -> dict[str, Any] | None:
    """Run LLM-based S2 caption evaluation and return normalized payload."""
    if not isinstance(caption_text, str) or not caption_text.strip():
        return None
    logger.debug("[AIAnalysis] Caption LLM start length=%d", len(caption_text.strip()))

    prompt = {
        "system": (
            "Return only one valid JSON object and no markdown."
        ),
        "user": S2_CAPTION_EVALUATION_PROMPT.replace("{caption_text}", format_user_text_block(caption_text)),
        "response_format": {"type": "json_object"},
    }
    raw_text = await _call_llm_async(prompt, llm_client)
    if not isinstance(raw_text, str) or not raw_text.strip():
        logger.debug("[AIAnalysis] Caption LLM returned empty response")
        return None

    try:
        payload = _parse_object_response(raw_text)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    hook = _clamp_int_0_100(payload.get("hook_score_0_100"))
    length = _clamp_int_0_100(payload.get("length_score_0_100"))
    hashtag = _clamp_int_0_100(payload.get("hashtag_score_0_100"))
    cta = _clamp_int_0_100(payload.get("cta_score_0_100"))
    if None in {hook, length, hashtag, cta}:
        return None

    s2_raw = _clamp_int_0_100(payload.get("s2_raw_0_100"))
    if s2_raw is None:
        s2_raw = int(round(hook * 0.30 + length * 0.20 + hashtag * 0.25 + cta * 0.25))

    total_0_50 = round(max(0.0, min(50.0, s2_raw / 2.0)), 1)

    notes: list[str] = []
    technical_flaws = payload.get("technical_flaws")
    if isinstance(technical_flaws, list):
        for item in technical_flaws:
            if isinstance(item, str) and item.strip():
                notes.append(item.strip()[:160])
                if len(notes) >= 3:
                    break

    improved_hook = payload.get("improved_hook_suggestion")
    if isinstance(improved_hook, str) and improved_hook.strip():
        notes.append(f"improved_hook_suggestion: {improved_hook.strip()[:160]}")

    result = {
        "hook_score_0_100": hook,
        "length_score_0_100": length,
        "hashtag_score_0_100": hashtag,
        "cta_score_0_100": cta,
        "s2_raw_0_100": s2_raw,
        "total_0_50": total_0_50,
        "notes": notes,
    }
    logger.debug("[AIAnalysis] Caption LLM completed total_0_50=%s", total_0_50)
    return result


async def run_audience_relevance_llm(
    creator_category: str | None,
    post_category: str | None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any] | None:
    """Run LLM-based S4 audience relevance evaluation."""
    creator_text = creator_category or ""
    post_text = post_category or ""
    logger.debug(
        "[AIAnalysis] Audience LLM start creator_category=%s post_category=%s",
        creator_text or None,
        post_text or None,
    )

    user_prompt = S4_AUDIENCE_RELEVANCE_PROMPT.replace("{creator_category}", format_user_text_block(creator_text)).replace("{post_category}", format_user_text_block(post_text))
    prompt = {
        "system": (
            "Return only one valid JSON object and no markdown."
        ),
        "user": user_prompt,
        "response_format": {"type": "json_object"},
    }
    raw_text = await _call_llm_async(prompt, llm_client)
    if not isinstance(raw_text, str) or not raw_text.strip():
        logger.debug("[AIAnalysis] Audience LLM returned empty response")
        return None

    try:
        payload = _parse_object_response(raw_text)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    affinity = payload.get("affinity_band")
    if not isinstance(affinity, str):
        affinity = "UNKNOWN"
    affinity = affinity.strip().upper()
    allowed_bands = {"EXACT", "HIGH_OVERLAP", "ADJACENT", "UNRELATED", "UNKNOWN"}
    if affinity not in allowed_bands:
        affinity = "UNKNOWN"

    s4_raw = _clamp_int_0_100(payload.get("s4_raw_0_100"))
    if s4_raw is None:
        s4_raw_map = {
            "EXACT": 100,
            "HIGH_OVERLAP": 85,
            "ADJACENT": 65,
            "UNRELATED": 15,
            "UNKNOWN": 50,
        }
        s4_raw = s4_raw_map.get(affinity, 50)

    explanation = payload.get("audience_overlap_explanation")
    explanation_text = explanation.strip() if isinstance(explanation, str) else ""

    result = {
        "s4_raw_0_100": s4_raw,
        "affinity_band": affinity,
        "audience_overlap_explanation": explanation_text,
    }
    logger.debug(
        "[AIAnalysis] Audience LLM completed affinity_band=%s s4_raw_0_100=%s",
        affinity,
        s4_raw,
    )
    return result


def _parse_driver_item(value: Any) -> AIDriver | None:
    """Validate and normalize one driver item."""
    if not isinstance(value, dict):
        return None
    required_keys = {"id", "label", "type", "explanation"}
    if not required_keys.issubset(value.keys()):
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
    if not required_keys.issubset(value.keys()):
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

    result: AIRecommendation = {
        "id": item_id.strip(),
        "text": text.strip(),
        "impact_level": impact_level,
    }
    # Optional category field (new in v2)
    raw_category = value.get("category")
    if isinstance(raw_category, str) and raw_category.strip().upper() in {
        "CAPTION", "VISUAL", "TIMING", "HASHTAGS", "ENGAGEMENT"
    }:
        result["category"] = raw_category.strip().upper()
    else:
        result["category"] = "ENGAGEMENT"
    return result


def _parse_llm_response(
    raw_text: str | None,
) -> tuple[
    str | None,
    list[AIDriver],
    list[AIRecommendation],
    dict[str, Any] | None,
    dict[str, str] | None,
    str | None,
    str | None,
    dict[str, Any] | None,
    str | None,
    str | None,
]:
    """Parse and strictly validate LLM output schema."""
    _empty = (None, [], [], None, None, None, None, None, None, None)

    if not raw_text:
        return _empty

    try:
        payload = _parse_object_response(raw_text)
    except Exception:
        return _empty

    if not isinstance(payload, dict):
        return _empty

    summary = payload.get("summary")
    drivers_raw = payload.get("drivers")
    recommendations_raw = payload.get("recommendations")
    engagement_potential_raw = payload.get("engagement_potential_score")

    if not isinstance(summary, str) or not summary.strip():
        return _empty
    if not isinstance(drivers_raw, list):
        return _empty
    if not isinstance(recommendations_raw, list):
        return _empty
    if not isinstance(engagement_potential_raw, dict):
        return _empty

    drivers: list[AIDriver] = []
    for item in drivers_raw:
        parsed_item = _parse_driver_item(item)
        if parsed_item is None:
            return _empty
        drivers.append(parsed_item)

    recommendations: list[AIRecommendation] = []
    for item in recommendations_raw:
        parsed_item = _parse_recommendation_item(item)
        if parsed_item is None:
            return _empty
        recommendations.append(parsed_item)

    # --- New v2 optional fields ---
    caption_improvement: dict[str, str] | None = None
    raw_ci = payload.get("caption_improvement")
    if isinstance(raw_ci, dict):
        hook_rw = raw_ci.get("hook_rewrite")
        cta_rw = raw_ci.get("cta_rewrite")
        if isinstance(hook_rw, str) and hook_rw.strip():
            caption_improvement = {
                "hook_rewrite": hook_rw.strip()[:300],
                "cta_rewrite": cta_rw.strip()[:300] if isinstance(cta_rw, str) else "",
            }

    posting_intelligence: str | None = None
    raw_pi = payload.get("posting_intelligence")
    if isinstance(raw_pi, str) and raw_pi.strip():
        posting_intelligence = raw_pi.strip()[:400]

    hashtag_quality_note: str | None = None
    raw_hq = payload.get("hashtag_quality_note")
    if isinstance(raw_hq, str) and raw_hq.strip():
        hashtag_quality_note = raw_hq.strip()[:300]

    # --- New v3 optional fields ---
    hashtag_analysis: dict[str, Any] | None = None
    raw_ha = payload.get("hashtag_analysis")
    if isinstance(raw_ha, dict):
        quality_band = raw_ha.get("quality_band")
        suggested_count = raw_ha.get("suggested_count")
        if isinstance(quality_band, str) and quality_band.strip():
            hashtag_analysis = {
                "quality_band": quality_band.strip()[:50],
                "issue": str(raw_ha.get("issue") or "").strip()[:200] or None,
                "suggested_count": int(suggested_count) if isinstance(suggested_count, (int, float)) else None,
                "strategy_tip": str(raw_ha.get("strategy_tip") or "").strip()[:300] or None,
            }

    viral_opportunity: str | None = None
    raw_vo = payload.get("viral_opportunity")
    if isinstance(raw_vo, str) and raw_vo.strip():
        viral_opportunity = raw_vo.strip()[:500]

    creator_next_step: str | None = None
    raw_cns = payload.get("creator_next_step")
    if isinstance(raw_cns, str) and raw_cns.strip():
        creator_next_step = raw_cns.strip()[:300]

    summary = summary.strip()
    return (summary, drivers, recommendations, engagement_potential_raw,
            caption_improvement, posting_intelligence, hashtag_quality_note,
            hashtag_analysis, viral_opportunity, creator_next_step)


async def _parse_llm_response_with_repair(
    raw_text: str | None,
    llm_client: LLMClient | None,
) -> tuple[
    str | None,
    list[AIDriver],
    list[AIRecommendation],
    dict[str, Any] | None,
    dict[str, str] | None,
    str | None,
    str | None,
    dict[str, Any] | None,
    str | None,
    str | None,
]:
    parsed = _parse_llm_response(raw_text)
    summary, drivers, recommendations, engagement_potential_raw, caption_improvement, posting_intelligence, hashtag_quality_note, hashtag_analysis, viral_opportunity, creator_next_step = parsed
    if summary is not None:
        primary_payload = sanitize_s5_payload(engagement_potential_raw)
        if primary_payload is not None and _sanitize_engagement_potential_score(primary_payload) is not None:
            return summary, drivers, recommendations, primary_payload, caption_improvement, posting_intelligence, hashtag_quality_note, hashtag_analysis, viral_opportunity, creator_next_step

    return parsed


def sanitize_s5_payload(raw: Any) -> dict[str, Any] | None:
    """Sanitize common harmless schema deviations for S5 payloads."""
    if not isinstance(raw, dict):
        return None

    allowed_keys = (
        "emotional_resonance",
        "shareability",
        "save_worthiness",
        "comment_potential",
        "novelty_or_value",
        "total",
        "notes",
    )
    required_keys = {
        "emotional_resonance",
        "shareability",
        "save_worthiness",
        "comment_potential",
        "novelty_or_value",
        "notes",
    }
    score_keys = {
        "emotional_resonance",
        "shareability",
        "save_worthiness",
        "comment_potential",
        "novelty_or_value",
        "total",
    }

    sanitized: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in raw:
            continue
        value = raw.get(key)
        if key in score_keys and isinstance(value, str):
            text = value.strip()
            if text:
                try:
                    value = float(text)
                except ValueError:
                    pass
        if key == "notes":
            if isinstance(value, str):
                value = [value]
            elif isinstance(value, list):
                normalized_notes: list[str] = []
                for item in value:
                    if isinstance(item, str):
                        normalized_notes.append(item)
                    elif isinstance(item, (dict, list)):
                        normalized_notes.append(json.dumps(item, sort_keys=True, ensure_ascii=True, default=str))
                    else:
                        normalized_notes.append(str(item))
                value = normalized_notes
        sanitized[key] = value

    if not required_keys.issubset(sanitized.keys()):
        return None
    return sanitized


def _sanitize_engagement_potential_score(raw_score: dict[str, Any] | None) -> EngagementPotentialScore | None:
    sanitized_payload = sanitize_s5_payload(raw_score)
    if not isinstance(sanitized_payload, dict):
        return None

    try:
        parsed = EngagementPotentialScore.model_validate(sanitized_payload)
    except Exception:
        return None

    derived_total = (
        parsed.emotional_resonance
        + parsed.shareability
        + parsed.save_worthiness
        + parsed.comment_potential
        + parsed.novelty_or_value
    )
    clamped_total = max(0.0, min(50.0, round(derived_total, 2)))
    return parsed.model_copy(update={"total": clamped_total})


def _apply_s5_consistency_cap(
    engagement_score: EngagementPotentialScore,
    visual_quality_score: VisualQualityScore,
    content_clarity_score: ContentClarityScore,
    percentile_rank: float | None = None,
) -> EngagementPotentialScore:
    """Cap S5 only when creative evidence (S1 and S3) contradicts it.

    ``percentile_rank`` is retained temporarily for call compatibility but is
    deliberately ignored: observed performance cannot affect the AI-only score.
    """
    del percentile_rank
    current_total = engagement_score.total
    notes = list(engagement_score.notes)
    updated_total = current_total

    # Rule 1: S1 + S3 consistency cap
    if visual_quality_score.total < 15.0 and content_clarity_score.total < 15.0 and current_total > 30.0:
        updated_total = min(updated_total, 30.0)
        notes.append("consistency cap applied: low S1 and S3 limited S5 total")

    if updated_total != current_total:
        return engagement_score.model_copy(update={"total": round(updated_total, 2), "notes": notes})
    return engagement_score


def _compute_score_analysis(
    visual_quality_score: VisualQualityScore,
    content_clarity_score: ContentClarityScore,
    caption_effectiveness_score: CaptionEffectivenessScore,
    audience_relevance_score: AudienceRelevanceScore,
    brand_safety_score: BrandSafetyScore,
    weighted_post_score: WeightedPostScore,
) -> dict[str, Any]:
    """Identify the weakest and strongest scoring dimensions.

    Returns a dict with weakest_dimension, strongest_dimension, and gap_to_average.
    All S-scores are normalized to the 0..50 scale for comparison.
    """
    scores: dict[str, float | None] = {
        "S1_visual_quality": visual_quality_score.total,
        "S2_caption_effectiveness": caption_effectiveness_score.total_0_50,
        "S3_content_clarity": content_clarity_score.total,
        "S4_audience_relevance": _available_audience_relevance_total(audience_relevance_score),
        "S6_brand_safety": brand_safety_score.total_0_50,
    }
    available = {k: float(v) for k, v in scores.items() if isinstance(v, (int, float))}
    if not available:
        return {
            "weakest_dimension": None,
            "strongest_dimension": None,
            "gap_to_average": None,
        }
    avg = sum(available.values()) / len(available)
    weakest = min(available, key=available.__getitem__)
    strongest = max(available, key=available.__getitem__)
    gap = round(available[weakest] - avg, 2)
    return {
        "weakest_dimension": weakest,
        "strongest_dimension": strongest,
        "gap_to_average": gap,
        "all_scores_0_50": available,
    }


def _compute_predicted_er_blended(
    tier_avg_er: float | None,
    s5_total: float | None,
    account_avg_er: float | None,
    weighted_score_0_100: float | None,
) -> tuple[float | None, str, list[str]]:
    """Blend LLM-derived (S5) and deterministic (weighted score) signals for predicted ER.

    Returns (predicted_er, confidence, notes).
    """
    notes: list[str] = []

    signal_a: float | None = None
    if isinstance(tier_avg_er, (int, float)) and isinstance(s5_total, (int, float)) and tier_avg_er >= 0:
        s5_clamped = max(0.0, min(50.0, float(s5_total)))
        signal_a = float(tier_avg_er) * (s5_clamped / 50.0)
        notes.append("signal_a: tier_avg_er * (S5/50)")

    signal_b: float | None = None
    if isinstance(account_avg_er, (int, float)) and isinstance(weighted_score_0_100, (int, float)) and account_avg_er >= 0:
        signal_b = float(account_avg_er) * (max(0.0, min(100.0, float(weighted_score_0_100))) / 100.0)
        notes.append("signal_b: account_avg_er * (weighted_score/100)")

    if signal_a is not None and signal_b is not None:
        predicted = 0.5 * signal_a + 0.5 * signal_b
        confidence = "high"
        notes.append("blended: 0.5*signal_a + 0.5*signal_b")
    elif signal_a is not None:
        predicted = signal_a
        confidence = "medium"
    elif signal_b is not None:
        predicted = signal_b
        confidence = "medium"
    else:
        notes.append("missing all er signals")
        return None, "low", notes

    # Clamp to fraction (<=1) or percent (<=100) depending on tier_avg_er unit
    ref_er = tier_avg_er if isinstance(tier_avg_er, (int, float)) else account_avg_er
    predicted = max(0.0, predicted)
    if isinstance(ref_er, (int, float)) and ref_er <= 1.0:
        if predicted > 1.0:
            notes.append("predicted_er capped at 1.0 (fraction unit)")
        predicted = min(predicted, 1.0)
    else:
        if predicted > 100.0:
            notes.append("predicted_er capped at 100.0 (percent unit)")
        predicted = min(predicted, 100.0)

    return round(predicted, 6), confidence, notes




def _fallback_summary(score: float | None, band: str) -> str:
    """Return deterministic fallback summary when LLM output is unavailable."""
    if score is None:
        return "AI creative analysis is unavailable because the creative signals could not be scored."
    return f"AI creative score: {score:.1f}/100 ({band}), based only on the post's creative signals."


def _fallback_recommendations(
    visual_quality_score: VisualQualityScore,
    caption_effectiveness_score: CaptionEffectivenessScore,
    content_clarity_score: ContentClarityScore,
) -> list[AIRecommendation]:
    """Return useful score-grounded moves when the coaching LLM is unavailable."""
    recommendations: list[AIRecommendation] = []
    if visual_quality_score.total < 35.0:
        recommendations.append({
            "id": "fallback_visual_focus",
            "text": "Use one clear focal subject in the opening frame and remove competing background elements.",
            "impact_level": "HIGH",
            "category": "VISUAL",
        })
    if caption_effectiveness_score.total_0_50 < 35.0:
        recommendations.append({
            "id": "fallback_caption_hook",
            "text": "Open the caption with the main takeaway, then add one specific reason to save or share the post.",
            "impact_level": "HIGH",
            "category": "CAPTION",
        })
    if content_clarity_score.total < 35.0:
        recommendations.append({
            "id": "fallback_content_clarity",
            "text": "Make the post's single message explicit in the first frame and support it with a matching caption.",
            "impact_level": "MEDIUM",
            "category": "VISUAL",
        })
    if not recommendations:
        recommendations.append({
            "id": "fallback_engagement",
            "text": "Repeat this format with one concrete audience question to encourage useful comments.",
            "impact_level": "MEDIUM",
            "category": "ENGAGEMENT",
        })
    return recommendations[:3]


def _build_ai_warning(
    *,
    code: Literal["GEMINI_API_KEY_MISSING", "VISION_ERROR"],
    message: str,
    post_id: str | None,
) -> AIWarning:
    return {
        "component": "vision",
        "code": code,
        "message": message,
        "post_id": post_id,
    }


def _build_deterministic_visual_drivers(vision: dict[str, Any]) -> list[AIDriver]:
    """Build deterministic LIMITING drivers from low-level vision signals."""
    signals = vision.get("signals")
    if not isinstance(signals, list) or not signals or not isinstance(signals[0], dict):
        return []

    signal = signals[0]
    hook_strength_raw = signal.get("hook_strength_score")
    hook_strength = None
    if isinstance(hook_strength_raw, (int, float)):
        hook_strength = max(0.0, min(1.0, float(hook_strength_raw)))

    dominant_focus = signal.get("dominant_focus") or signal.get("dominant_object")
    has_focus = isinstance(dominant_focus, str) and dominant_focus.strip()

    drivers: list[AIDriver] = []

    if hook_strength is not None and hook_strength < 0.4:
        drivers.append(
            {
                "id": "deterministic_weak_visual_hook",
                "label": "Visual hook opportunity",
                "type": "LIMITING",
                "explanation": f"Vision hook_strength_score is {hook_strength:.2f}; a clearer opening visual can create a stronger first impression.",
            }
        )

    if not has_focus:
        drivers.append(
            {
                "id": "deterministic_no_dominant_focus",
                "label": "No clear dominant visual focus",
                "type": "LIMITING",
                "explanation": "Vision signals do not include a dominant_focus or dominant_object.",
            }
        )

    return drivers


def _build_deterministic_clarity_drivers(content_clarity_score: ContentClarityScore) -> list[AIDriver]:
    """Build deterministic LIMITING drivers from S3 content clarity signals."""
    drivers: list[AIDriver] = []

    if content_clarity_score.total < 20.0:
        drivers.append(
            {
                "id": "deterministic_unclear_main_message",
                "label": "Message focus opportunity",
                "type": "LIMITING",
                "explanation": (
                    f"S3 content clarity total is {content_clarity_score.total:.2f}, "
                    "showing an opportunity to make the main message more focused and memorable."
                ),
            }
        )

    if content_clarity_score.cognitive_load < 5.0:
        drivers.append(
            {
                "id": "deterministic_high_cognitive_load",
                "label": "Simplify message delivery",
                "type": "LIMITING",
                "explanation": (
                    f"S3 cognitive_load is {content_clarity_score.cognitive_load:.2f}, "
                    "so simplifying the visual hierarchy or text density can make the message easier to absorb."
                ),
            }
        )

    if content_clarity_score.caption_alignment < 4.0:
        drivers.append(
            {
                "id": "deterministic_align_caption_with_visual_message",
                "label": "Align caption with visual message",
                "type": "LIMITING",
                "explanation": (
                    f"S3 caption_alignment is {content_clarity_score.caption_alignment:.2f}; "
                    "caption and visual message are not well aligned."
                ),
            }
        )

    return drivers


async def analyze_single_post_ai(
    post: SinglePostInsights,
    llm_client: LLMClient | None = None,
) -> AIAnalysisResult:
    """Run async AI analysis for a single post with caching and regen throttling.

    This function mutates ``post`` in-place by populating computed score fields
    and intermediate analysis fields (for example: ``visual_quality_score``,
    ``caption_effectiveness_score``, ``content_clarity_score``,
    ``audience_relevance_score``, ``brand_safety_score``,
    ``engagement_potential_score``, ``weighted_post_score``,
    ``vision_analysis``, and predicted engagement fields).
    Callers should treat ``post`` as updated after this call returns.
    If immutability is required, pass a copy before calling (for example
    ``post.model_copy(deep=True)``, ``copy.copy(...)``, or
    ``dataclasses.replace(...)`` for dataclass inputs).
    """
    from datetime import datetime, timezone

    now_ts = time.time()
    key = _cache_key(post)
    logger.info(
        "[AIAnalysis] Start media_id=%s account_id=%s media_type=%s",
        post.media_id,
        post.account_id,
        post.media_type,
    )
    with _ANALYSIS_CACHE_LOCK:
        _prune_analysis_cache(now_ts)
        cached = _ANALYSIS_CACHE.get(key) if key is not None else None
        if cached is not None and _is_fresh(cached, now_ts):
            logger.debug("[AIAnalysis] Cache hit media_id=%s", post.media_id)
            return cached.result
        if cached is not None and (now_ts - cached.last_regen_attempt_at) < MIN_REGEN_SECONDS:
            logger.debug("[AIAnalysis] Returning throttled cached result media_id=%s", post.media_id)
            return cached.result
        if cached is not None:
            cached.last_regen_attempt_at = now_ts
            logger.debug("[AIAnalysis] Cache stale; regenerating media_id=%s", post.media_id)
    visual_quality_score = _resolve_score(post.visual_quality_score, VisualQualityScore)
    content_clarity_score = _resolve_score(post.content_clarity_score, ContentClarityScore)
    caption_effectiveness_score = _resolve_score(post.caption_effectiveness_score, CaptionEffectivenessScore)
    engagement_potential_score = _resolve_score(post.engagement_potential_score, EngagementPotentialScore)
    weighted_post_score = _resolve_score(post.weighted_post_score, WeightedPostScore)
    audience_relevance_score = _resolve_score(post.audience_relevance_score, AudienceRelevanceScore)
    brand_safety_score = _resolve_score(post.brand_safety_score, BrandSafetyScore)
    tier_avg_engagement_rate = post.tier_avg_engagement_rate
    predicted_engagement_rate = post.predicted_engagement_rate
    predicted_engagement_rate_notes = list(post.predicted_engagement_rate_notes)

    post_id = post.media_id if isinstance(post.media_id, str) else None
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    gemini_enabled = bool(isinstance(gemini_api_key, str) and gemini_api_key.strip())
    openai_enabled = bool(
        (isinstance(openai_api_key, str) and openai_api_key.strip())
        or (
            isinstance(azure_openai_endpoint, str)
            and azure_openai_endpoint.strip()
            and isinstance(azure_openai_api_key, str)
            and azure_openai_api_key.strip()
        )
    )
    external_ai_calls_enabled = os.getenv("AI_EXTERNAL_CALLS_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    vision_enabled = external_ai_calls_enabled and (gemini_enabled or openai_enabled)
    warnings: list[AIWarning] = []
    vision_error_reason: str | None = None
    if not external_ai_calls_enabled:
        warnings.append(
            _build_ai_warning(
                code="EXTERNAL_AI_DISABLED",
                message="External AI calls are disabled by AI_EXTERNAL_CALLS_ENABLED.",
                post_id=post_id,
            )
        )
    if not gemini_enabled:
        warnings.append(
            _build_ai_warning(
                code="GEMINI_API_KEY_MISSING",
                message="Gemini vision is disabled because GEMINI_API_KEY is not set. OpenAI fallback may be used if configured.",
                post_id=post_id,
            )
        )
    vision_status: Literal["ok", "error", "disabled", "no_media"] = "disabled" if not vision_enabled else "ok"
    fallback_used = False
    fallback_reasons: list[str] = []
    logger.debug(
        "[AIAnalysis] Vision config media_id=%s vision_enabled=%s published_at=%s",
        post.media_id,
        vision_enabled,
        post.published_at,
    )

    if post.published_at is not None:
        published_at = post.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        now_utc = datetime.now(timezone.utc)
        post_age_seconds = (now_utc - published_at).total_seconds()
        if post_age_seconds < MIN_REGEN_SECONDS:
            fallback_used = True
            fallback_reasons.append("post_too_new")
            logger.info(
                "[AIAnalysis] Skipping AI analysis for very recent post media_id=%s age_seconds=%.2f",
                post.media_id,
                post_age_seconds,
            )
            result: AIAnalysisResult = {
                "summary": "AI analysis unavailable. Post is still accumulating data.",
                "drivers": [],
                "recommendations": [],
                "ai_content_score": None,
                "ai_content_band": "UNAVAILABLE",
                "creative_score": None,
                "creative_band": "UNAVAILABLE",
                "score_source": "ai_creative_weighted_score",
                "performance_score": None,
                "performance_score_status": "unavailable_not_part_of_ai_creative_analysis",
                "caption_effectiveness_score": caption_effectiveness_score.model_dump(),
                "visual_quality_score": visual_quality_score.model_dump(),
                "content_clarity_score": content_clarity_score.model_dump(),
                "engagement_potential_score": engagement_potential_score.model_dump(),
                "audience_relevance_score": audience_relevance_score.model_dump(),
                "brand_safety_score": brand_safety_score.model_dump(),
                "weighted_post_score": weighted_post_score.model_dump(),
                "vision_analysis": VisionAnalysis(
                    provider="gemini",
                    status=str(vision_status),
                    signals=[],
                ).model_dump(mode="python"),
                "tier_avg_engagement_rate": None,
                "predicted_engagement_rate": None,
                "predicted_engagement_rate_notes": ["Not part of the AI-only creative analysis contract."],
                "warnings": warnings,
                "vision_status": vision_status,
                "fallback_used": fallback_used,
                "fallback_reason": ",".join(fallback_reasons) or None,
                "predicted_er_confidence": "unavailable",
            }
            return result

    if not vision_enabled:
        vision = VisionAnalysis(provider="gemini", status="error", signals=[]).model_dump(mode="python")
    else:
        logger.debug("[AIAnalysis] Running Gemini vision media_id=%s", post.media_id)
        vision = await run_vision_analysis(post)
        if vision.get("status") == "error":
            vision_status = "error"
            raw_error_reason = vision.get("error_reason")
            if isinstance(raw_error_reason, str) and raw_error_reason.strip():
                vision_error_reason = raw_error_reason.strip()[:300]
            warning_message = "Gemini vision request failed; deterministic fallback scoring applied."
            if vision_error_reason:
                warning_message = f"{warning_message} reason={vision_error_reason}"
            warnings.append(
                _build_ai_warning(
                    code="VISION_ERROR",
                    message=warning_message,
                    post_id=post_id,
                )
            )
        elif vision.get("status") == "ok":
            vision_status = "ok"
        elif vision.get("status") == "no_media":
            vision_status = "no_media"
    logger.debug("[AIAnalysis] Vision finished media_id=%s status=%s", post.media_id, vision_status)

    if str(post.media_type or "").upper() == "REEL":
        raw_reel_signals = vision.get("raw_reel_signals")
        raw_reel_signals = raw_reel_signals if isinstance(raw_reel_signals, dict) else {}
        audio_score = compute_reel_audio_score(
            audio_name=post.audio_name,
            caption_text=post.caption_text or "",
            reel_vision_signals=raw_reel_signals,
        )
        post.reel_analysis = compute_reel_analysis(
            reel_vision_signals=raw_reel_signals,
            audio_score=audio_score,
            watch_time_pct=None,
            reel_vision_status=str(vision.get("status") or vision_status),
        )
        logger.debug(
            "[AIAnalysis] Reel analysis media_id=%s total=%s reel_vision_status=%s",
            post.media_id,
            post.reel_analysis.total,
            post.reel_analysis.reel_vision_status,
        )
    vision.pop("raw_reel_signals", None)

    visual_quality_score = compute_visual_quality_score(vision)
    if external_ai_calls_enabled:
        caption_effectiveness_score = (
            post.caption_effectiveness_score
            if isinstance(post.caption_effectiveness_score, CaptionEffectivenessScore)
            else await analyze_caption_via_llm(post.caption_text)
        )
        content_clarity_score = await analyze_content_clarity_via_llm(vision, post.caption_text)
        audience_relevance_score = await analyze_audience_relevance_via_llm(
            post.post_category,
            post.creator_dominant_category,
        )
    else:
        caption_effectiveness_score = _resolve_score(post.caption_effectiveness_score, CaptionEffectivenessScore)
        content_clarity_score = _resolve_score(post.content_clarity_score, ContentClarityScore)
        audience_relevance_score = _resolve_score(post.audience_relevance_score, AudienceRelevanceScore)
    brand_safety_score = compute_s6_brand_safety(
        caption_text=post.caption_text,
        vision=vision,
        s1_total_0_50=visual_quality_score.total,
        extracted_brand_mentions=post.extracted_brand_mentions,
        extra_flags=post.safety_extra_flags,
    )
    # Mutates `post` in-place to attach computed metrics for downstream use.
    post.visual_quality_score = visual_quality_score
    post.caption_effectiveness_score = caption_effectiveness_score
    post.content_clarity_score = content_clarity_score
    post.audience_relevance_score = audience_relevance_score
    post.brand_safety_score = brand_safety_score
    weighted_post_type = _resolve_weighted_post_type(post.media_type)
    weighted_post_score = compute_weighted_post_score(
        post_type=weighted_post_type,
        s1=visual_quality_score.total,
        s2=caption_effectiveness_score.total_0_50,
        s3=content_clarity_score.total,
        s4=_available_audience_relevance_total(audience_relevance_score),
        s5=None,
        s6=brand_safety_score.total_0_50,
        s7=None,
    )
    post.weighted_post_score = weighted_post_score
    preliminary_creative_score, preliminary_creative_band = _creative_score_payload(weighted_post_score)
    logger.debug(
        "[AIAnalysis] Deterministic scores media_id=%s s1=%s s2=%s s3=%s s4=%s s6=%s weighted=%s",
        post.media_id,
        visual_quality_score.total,
        caption_effectiveness_score.total_0_50,
        content_clarity_score.total,
        _available_audience_relevance_total(audience_relevance_score),
        brand_safety_score.total_0_50,
        weighted_post_score.score,
    )
    try:
        post.vision_analysis = VisionAnalysis.model_validate(vision)
    except Exception:
        post.vision_analysis = VisionAnalysis(provider="gemini", status="error", signals=[])
    deterministic_drivers = _build_deterministic_visual_drivers(vision) + _build_deterministic_clarity_drivers(
        content_clarity_score
    )

    context = build_ai_input_context(
        post,
        visual_quality_score,
        content_clarity_score,
        caption_effectiveness_score,
        audience_relevance_score,
        brand_safety_score,
        weighted_post_score,
    )
    if post.reel_analysis is not None:
        context["reel_analysis"] = post.reel_analysis.model_dump()
    prompt = _build_prompt(context, vision)

    external_ai_enabled = bool((gemini_enabled or openai_enabled) and external_ai_calls_enabled)
    if external_ai_enabled:
        llm_text = await _call_llm_async(prompt, llm_client)
        (
            summary,
            drivers,
            recommendations,
            engagement_potential_raw,
            caption_improvement,
            posting_intelligence,
            hashtag_quality_note,
            hashtag_analysis,
            viral_opportunity,
            creator_next_step,
        ) = await _parse_llm_response_with_repair(llm_text, llm_client)
    else:
        llm_text = None
        summary = None
        drivers = []
        recommendations = []
        engagement_potential_raw = None
        caption_improvement = None
        posting_intelligence = None
        hashtag_quality_note = None
        hashtag_analysis = None
        viral_opportunity = None
        creator_next_step = None
    logger.debug(
        "[AIAnalysis] LLM parsed media_id=%s summary_present=%s drivers=%d recommendations=%d",
        post.media_id,
        summary is not None,
        len(drivers or []),
        len(recommendations or []),
    )

    summary_was_fallback = summary is None
    if summary_was_fallback:
        summary = _fallback_summary(preliminary_creative_score, preliminary_creative_band)
        drivers = deterministic_drivers
        recommendations = _fallback_recommendations(
            visual_quality_score,
            caption_effectiveness_score,
            content_clarity_score,
        )
        engagement_potential_score = _fallback_engagement_potential_score()
        caption_improvement = None
        posting_intelligence = None
        hashtag_quality_note = None
        hashtag_analysis = None
        viral_opportunity = None
        creator_next_step = None
        fallback_used = True
        if not external_ai_enabled:
            fallback_reasons.append("coaching_disabled")
        elif llm_text is None:
            # Covers timeout, provider/network errors, and empty-content
            # responses (e.g. a reasoning model exhausting its token budget
            # on hidden reasoning) -- _call_llm_async collapses all of these
            # to None since LLMClient raises on each.
            fallback_reasons.append("coaching_llm_unavailable")
        else:
            fallback_reasons.append("coaching_llm_malformed")
        logger.info("[AIAnalysis] Using fallback summary media_id=%s", post.media_id)
    else:
        drivers = deterministic_drivers + drivers
        engagement_potential_score = _sanitize_engagement_potential_score(engagement_potential_raw)
        if engagement_potential_score is None:
            engagement_potential_score = _fallback_engagement_potential_score()
            fallback_used = True
            fallback_reasons.append("s5_sanitization_failed")
            logger.info("[AIAnalysis] Using fallback S5 score media_id=%s", post.media_id)

    if vision_status in {"disabled", "error"}:
        fallback_used = True
        fallback_reasons.append("vision_disabled" if vision_status == "disabled" else "vision_error")

    engagement_potential_score = _apply_s5_consistency_cap(
        engagement_potential_score,
        visual_quality_score,
        content_clarity_score,
    )
    post.engagement_potential_score = engagement_potential_score
    weighted_post_score = compute_weighted_post_score(
        post_type=weighted_post_type,
        s1=visual_quality_score.total,
        s2=caption_effectiveness_score.total_0_50,
        s3=content_clarity_score.total,
        s4=_available_audience_relevance_total(audience_relevance_score),
        s5=engagement_potential_score.total,
        s6=brand_safety_score.total_0_50,
        s7=None,
    )
    post.weighted_post_score = weighted_post_score
    creative_score, creative_band = _creative_score_payload(weighted_post_score)
    if summary_was_fallback:
        summary = _fallback_summary(creative_score, creative_band)
    logger.debug(
        "[AIAnalysis] Final scores media_id=%s s5=%s weighted=%s fallback_used=%s",
        post.media_id,
        engagement_potential_score.total,
        weighted_post_score.score,
        fallback_used,
    )
    tier_avg_engagement_rate, tier_notes = _resolve_tier_avg_engagement_rate(post)
    account_avg_er = None
    if post.benchmark_metrics is not None:
        raw_acct = getattr(post.benchmark_metrics, "account_avg_engagement_rate", None)
        if isinstance(raw_acct, (int, float)):
            account_avg_er = float(raw_acct)

    predicted_engagement_rate, predicted_er_confidence, prediction_notes = _compute_predicted_er_blended(
        tier_avg_er=tier_avg_engagement_rate,
        s5_total=engagement_potential_score.total,
        account_avg_er=account_avg_er,
        weighted_score_0_100=weighted_post_score.score,
    )
    predicted_engagement_rate_notes = tier_notes + prediction_notes
    post.tier_avg_engagement_rate = tier_avg_engagement_rate
    post.predicted_engagement_rate = predicted_engagement_rate
    post.predicted_engagement_rate_notes = predicted_engagement_rate_notes

    # Deterministic score gap analysis
    score_analysis = _compute_score_analysis(
        visual_quality_score,
        content_clarity_score,
        caption_effectiveness_score,
        audience_relevance_score,
        brand_safety_score,
        weighted_post_score,
    )

    # Build creator-friendly score explanation
    _score_label_map = {
        "S1_visual_quality": "Visual Quality",
        "S2_caption_effectiveness": "Caption Effectiveness",
        "S3_content_clarity": "Content Clarity",
        "S4_audience_relevance": "Audience Relevance",
        "S6_brand_safety": "Brand Safety",
    }
    _all_scores = score_analysis.get("all_scores_0_50") or {}
    score_explanation: dict[str, Any] = {
        key: {
            "label": _score_label_map.get(key, key),
            "score": round(float(v), 1),
            "max": 50,
            "pct": round(float(v) / 50.0 * 100),
        }
        for key, v in _all_scores.items()
        if isinstance(v, (int, float))
    }

    # Extract cringe signals from vision for creator-facing card
    cringe_summary: dict[str, Any] | None = None
    if isinstance(vision.get("signals"), list) and vision["signals"]:
        _sig = vision["signals"][0]
        if isinstance(_sig, dict):
            cringe_summary = _extract_cringe_summary(_sig)

    result: AIAnalysisResult = {
        "summary": summary,
        "drivers": drivers,
        "recommendations": recommendations,
        "ai_content_score": creative_score,
        "ai_content_band": creative_band,
        "creative_score": creative_score,
        "creative_band": creative_band,
        "score_source": "ai_creative_weighted_score",
        "performance_score": None,
        "performance_score_status": "unavailable_not_part_of_ai_creative_analysis",
        "caption_effectiveness_score": caption_effectiveness_score.model_dump(),
        "visual_quality_score": visual_quality_score.model_dump(),
        "content_clarity_score": content_clarity_score.model_dump(),
        "engagement_potential_score": engagement_potential_score.model_dump(),
        "audience_relevance_score": audience_relevance_score.model_dump(),
        "brand_safety_score": brand_safety_score.model_dump(),
        "weighted_post_score": weighted_post_score.model_dump(),
        "vision_analysis": vision,
        "tier_avg_engagement_rate": None,
        "predicted_engagement_rate": None,
        "predicted_engagement_rate_notes": ["Not part of the AI-only creative analysis contract."],
        "warnings": warnings,
        "vision_status": vision_status,
        "fallback_used": fallback_used,
        "fallback_reason": ",".join(dict.fromkeys(fallback_reasons)) or None,
        # v2 enhanced analytics fields
        "caption_improvement": caption_improvement,
        "posting_intelligence": posting_intelligence,
        "hashtag_quality_note": hashtag_quality_note,
        "predicted_er_confidence": "unavailable",
        # v3 creator-facing enhancement fields
        "hashtag_analysis": hashtag_analysis,
        "viral_opportunity": viral_opportunity,
        "creator_next_step": creator_next_step,
        "cringe_summary": cringe_summary,
        "score_explanation": score_explanation,
    }
    if vision_error_reason:
        result["vision_error_reason"] = vision_error_reason

    # Attach score_analysis as a top-level key on the result dict
    result["score_analysis"] = score_analysis  # type: ignore[typeddict-unknown-key]

    if key is not None and _should_cache_analysis_result(result):
        with _ANALYSIS_CACHE_LOCK:
            _ANALYSIS_CACHE[key] = _CacheEntry(
                result=result,
                cached_at=now_ts,
                last_regen_attempt_at=now_ts,
            )
            _prune_analysis_cache(now_ts)
    elif key is not None:
        logger.info("[AIAnalysis] Skipping cache for failed vision media_id=%s", post.media_id)
    logger.info(
        "[AIAnalysis] Completed media_id=%s vision_status=%s warnings=%d fallback_used=%s predicted_er_confidence=%s",
        post.media_id,
        vision_status,
        len(warnings),
        fallback_used,
        predicted_er_confidence,
    )
    return result
