"""Async AI analysis service for single-post insights."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import threading
import time
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Literal, TypedDict
from urllib.parse import urlparse, urlunparse

from backend.app.ai.cringe_analysis import derive_cringe_label, enforce_cringe_floor
from backend.app.ai.prompts import S2_CAPTION_EVALUATION_PROMPT, S4_AUDIENCE_RELEVANCE_PROMPT
from backend.app.ai.llm_client import LLMClient
from backend.app.analytics.caption_s2_engine import compute_s2_caption_effectiveness
from backend.app.analytics.content_score import compute_content_score
from backend.app.analytics.post_weighted_score_engine import compute_weighted_post_score
from backend.app.analytics.predicted_er_engine import compute_predicted_engagement_rate
from backend.app.analytics.s4_audience_relevance_engine import compute_s4_audience_relevance
from backend.app.analytics.s6_brand_safety_engine import compute_s6_brand_safety
from backend.app.analytics.vision_s1_engine import compute_visual_quality_score
from backend.app.analytics.vision_s3_engine import compute_s3_content_clarity
from backend.app.domain.post_models import (
    AudienceRelevanceScore,
    BrandSafetyScore,
    CaptionEffectivenessScore,
    ContentClarityScore,
    EngagementPotentialScore,
    SinglePostInsights,
    VisionAnalysis,
    VisualQualityScore,
    WeightedPostScore,
)
from backend.app.utils.logger import logger


CACHE_TTL_SECONDS = 86400
MIN_REGEN_SECONDS = 7200
ANALYSIS_CACHE_MAX_ENTRIES = 1024


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
_GENAI_LOCK = threading.Lock()
_ANALYSIS_CACHE_LOCK = threading.Lock()

S5_JSON_SCHEMA: dict[str, Any] = {
    "name": "post_analysis_response",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "drivers", "recommendations", "engagement_potential_score"],
        "properties": {
            "summary": {"type": "string"},
            "drivers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "label", "type", "explanation"],
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "type": {"type": "string", "enum": ["POSITIVE", "LIMITING"]},
                        "explanation": {"type": "string"},
                    },
                },
            },
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "text", "impact_level"],
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "impact_level": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    },
                },
            },
            "engagement_potential_score": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "emotional_resonance",
                    "shareability",
                    "save_worthiness",
                    "comment_potential",
                    "novelty_or_value",
                    "total",
                    "notes",
                ],
                "properties": {
                    "emotional_resonance": {"type": "number", "minimum": 0, "maximum": 10},
                    "shareability": {"type": "number", "minimum": 0, "maximum": 10},
                    "save_worthiness": {"type": "number", "minimum": 0, "maximum": 10},
                    "comment_potential": {"type": "number", "minimum": 0, "maximum": 10},
                    "novelty_or_value": {"type": "number", "minimum": 0, "maximum": 10},
                    "total": {"type": "number", "minimum": 0, "maximum": 50},
                    "notes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
    "strict": True,
}


class AIAnalysisResult(TypedDict):
    """Structured response returned by AI single-post analysis."""

    summary: str
    drivers: list["AIDriver"]
    recommendations: list["AIRecommendation"]
    ai_content_score: int
    ai_content_band: str
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


@dataclass
class _CacheEntry:
    """Internal cache entry for AI analysis responses."""

    result: AIAnalysisResult
    cached_at: float
    last_regen_attempt_at: float


_ANALYSIS_CACHE: dict[str, _CacheEntry] = {}


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
        return f"{account_id}:{media_id}:{published_at}"

    caption_hint = _hash_cache_hint(post.caption_text)
    media_hint = _hash_cache_hint(post.media_url)

    if not account_id and not media_id and caption_hint in {"none", "empty"} and media_hint in {"none", "empty"}:
        return None

    account_part = account_id or "unknown_account"
    media_part = media_id or "unknown_media"
    return f"{account_part}:{media_part}:{published_at}:{caption_hint}:{media_hint}"


def _is_fresh(entry: _CacheEntry, now_ts: float) -> bool:
    """Return True when cache entry is still valid by TTL."""
    return (now_ts - entry.cached_at) <= CACHE_TTL_SECONDS


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


def _score_payload(post: SinglePostInsights) -> tuple[int, str]:
    """Compute deterministic content score payload from post metrics."""
    payload = compute_content_score(post.derived_metrics, post.benchmark_metrics)
    score = int(payload.get("score", 0))
    band = str(payload.get("band", "NEEDS_WORK"))
    return score, band


def _default_visual_quality_score() -> VisualQualityScore:
    return VisualQualityScore()


def _default_content_clarity_score() -> ContentClarityScore:
    return ContentClarityScore()


def _default_caption_effectiveness_score() -> CaptionEffectivenessScore:
    return CaptionEffectivenessScore()


def _default_engagement_potential_score() -> EngagementPotentialScore:
    return EngagementPotentialScore()


def _default_audience_relevance_score() -> AudienceRelevanceScore:
    return AudienceRelevanceScore()


def _default_brand_safety_score() -> BrandSafetyScore:
    return BrandSafetyScore()


def _default_weighted_post_score() -> WeightedPostScore:
    return WeightedPostScore()


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

    return not (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


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


def build_ai_input_context(
    post: SinglePostInsights,
    ai_content_score: int,
    ai_content_band: str,
    visual_quality_score: VisualQualityScore,
    content_clarity_score: ContentClarityScore,
    caption_effectiveness_score: CaptionEffectivenessScore,
    audience_relevance_score: AudienceRelevanceScore,
    brand_safety_score: BrandSafetyScore,
    weighted_post_score: WeightedPostScore,
) -> dict[str, Any]:
    """Build input context for downstream AI calls.

    This is intentionally a stub and can be expanded with richer context later.
    """
    return {
        "account_id": post.account_id,
        "media_id": post.media_id,
        "media_type": post.media_type,
        "caption_text": post.caption_text,
        "published_at": post.published_at.isoformat() if post.published_at is not None else None,
        "core_metrics": post.core_metrics.model_dump(),
        "derived_metrics": post.derived_metrics.model_dump(),
        "benchmark_metrics": post.benchmark_metrics.model_dump(),
        "ai_content_score": ai_content_score,
        "ai_content_band": ai_content_band,
        "s1_visual_quality": visual_quality_score.model_dump(),
        "s2_caption_effectiveness": caption_effectiveness_score.model_dump(),
        "s3_content_clarity": content_clarity_score.model_dump(),
        "s4_audience_relevance": audience_relevance_score.model_dump(),
        "s6_brand_safety": brand_safety_score.model_dump(),
        "weighted_post_score": weighted_post_score.model_dump(),
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


def _coerce_int_0_100(value: Any) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(max(0.0, min(100.0, round(numeric))))


def _apply_cringe_prompt_floor(cringe_score: int, cringe_signals: list[str]) -> int:
    score = int(max(0, min(100, cringe_score)))
    text = " ".join(cringe_signals).lower()
    confusing_concept = any(keyword in text for keyword in ("confus", "nonsens"))
    awkward_posing = any(keyword in text for keyword in ("awkward", "forced", "pose"))

    if confusing_concept and awkward_posing:
        score = max(score, 75)
    elif confusing_concept:
        score = max(score, 65)
    elif awkward_posing:
        score = max(score, 55)

    return int(max(0, min(100, score)))


async def run_vision_analysis(
    post: SinglePostInsights,
) -> dict[str, Any]:
    """Run Gemini Vision analysis for a post media URL with strict JSON parsing."""
    from urllib.parse import urlparse

    instruction = (
        "You are an expert Social Media Art Director and Computer Vision analysis engine. "
        "Analyze the provided Instagram media (image/frame) strictly through the lens of technical visual quality "
        "and compositional structure. Return ONLY valid JSON. Do not include markdown or extra keys.\n\n"
        "You must evaluate the image objectively on the following deterministic rules to calculate S1 sub-scores:\n"
        "1) COMPOSITION (0-10): Rule of Thirds/symmetry (+3), dominant_focus present (+4), >4 primary objects (-3), "
        "awkward crops (-3), remaining points (0-3) for depth-of-field/subject isolation.\n"
        "2) LIGHTING_QUALITY (0-10): subject illumination/contrast (+4), blown highlights or crushed blacks (-3), "
        "intentional depth (rim/softbox/golden hour +3) vs flat lighting (+1), poor white balance (-2), "
        "remaining points for cinematic/aesthetic lighting.\n"
        "3) SUBJECT_CLARITY (0-10): subject in focus (+5), clear separation (+3), visible expressive face if human (+2).\n"
        "4) AESTHETIC_QUALITY (0-10): pro color grade (+3), harmonious palette (+2), "
        "heavy text overlays (-3) or very heavy (-5), remaining points for premium visual feel.\n\n"
        "Output JSON must match this schema:\n"
        "{"
        "\"objects\": [\"...\"] ,"
        "\"dominant_focus\": \"string|null\","
        "\"scene_description\": \"string\","
        "\"visual_style\": \"string\","
        "\"scene_type\": \"string|null\","
        "\"visual_quality_score\": {"
        "\"composition\": 0.0-10.0,"
        "\"lighting\": 0.0-10.0,"
        "\"subject_clarity\": 0.0-10.0,"
        "\"aesthetic_quality\": 0.0-10.0"
        "},"
        "\"technical_flaws\": [\"string\", \"string\"],"
        "\"detected_text\": \"string|null\","
        "\"hook_strength_score\": 0.0-1.0,"
        "\"cringe_score\": 0-100,"
        "\"cringe_signals\": [\"string\"],"
        "\"cringe_fixes\": [\"string\"],"
        "\"production_level\": \"low|medium|high\","
        "\"adult_content_detected\": true|false,"
        "\"adult_content_confidence\": 0-100"
        "}\n\n"
        "Cringe rubric: 0-20 polished/natural; 21-40 minor awkwardness; 41-60 noticeable awkwardness or weak concept; "
        "61-80 strong cringe (forced, confusing, low coherence); 81-100 extreme cringe. "
        "Floor rules: if concept is confusing or nonsensical score must be >=65; "
        "if repeated awkward posing score must be >=55; if both are present score must be >=75."
    )

    media_url = post.media_url
    if not isinstance(media_url, str) or not media_url.strip():
        return VisionAnalysis(provider="gemini", status="no_media", signals=[]).model_dump(mode="python")

    media_url = media_url.strip()
    parsed_url = urlparse(media_url)
    hostname = parsed_url.hostname
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or not isinstance(hostname, str)
        or not await _is_safe_public_hostname(hostname)
    ):
        logger.warning(
            "[Vision] Rejected media_url for SSRF protection: %s",
            _sanitize_url_for_logging(media_url),
        )
        return VisionAnalysis(provider="gemini", status="no_media", signals=[]).model_dump(mode="python")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return VisionAnalysis(provider="gemini", status="error", signals=[]).model_dump(mode="python")

    try:
        raw_text = await _generate_gemini_vision_json(
            api_key=api_key,
            instruction=instruction,
            media_url=media_url,
        )
        payload = json.loads(raw_text)
        if not isinstance(payload, dict):
            raise ValueError("Gemini output must be a JSON object.")

        required_keys = {
            "objects",
            "dominant_focus",
            "scene_description",
            "visual_style",
            "scene_type",
            "visual_quality_score",
            "technical_flaws",
            "detected_text",
            "hook_strength_score",
            "cringe_score",
            "cringe_signals",
            "cringe_fixes",
            "production_level",
            "adult_content_detected",
            "adult_content_confidence",
        }
        if not required_keys.issubset(payload.keys()):
            raise ValueError("Gemini JSON schema mismatch.")

        objects = payload.get("objects")
        dominant_focus = payload.get("dominant_focus")
        scene_description = payload.get("scene_description")
        detected_text = payload.get("detected_text")
        visual_style = payload.get("visual_style")
        scene_type = payload.get("scene_type")
        visual_quality_score = payload.get("visual_quality_score")
        technical_flaws = payload.get("technical_flaws")
        hook_strength_score = payload.get("hook_strength_score")

        if not isinstance(objects, list) or not all(isinstance(item, str) for item in objects):
            raise ValueError("Invalid objects field.")
        if dominant_focus is not None and not isinstance(dominant_focus, str):
            raise ValueError("Invalid dominant_focus field.")
        if not isinstance(scene_description, str):
            raise ValueError("Invalid scene_description field.")
        if detected_text is not None and not isinstance(detected_text, str):
            raise ValueError("Invalid detected_text field.")
        if not isinstance(visual_style, str):
            raise ValueError("Invalid visual_style field.")
        if scene_type is not None and not isinstance(scene_type, str):
            raise ValueError("Invalid scene_type field.")
        if not isinstance(visual_quality_score, dict):
            raise ValueError("Invalid visual_quality_score field.")
        if not isinstance(technical_flaws, list) or not all(isinstance(item, str) for item in technical_flaws):
            raise ValueError("Invalid technical_flaws field.")
        if not isinstance(hook_strength_score, (int, float)):
            raise ValueError("Invalid hook_strength_score field.")

        objects = [
            item.strip()
            for item in objects
            if isinstance(item, str) and item.strip()
        ]
        dominant_focus = dominant_focus.strip() if isinstance(dominant_focus, str) else None
        scene_description = scene_description.strip()
        detected_text = detected_text.strip() if detected_text else None
        visual_style = visual_style.strip()
        scene_type = scene_type.strip() if isinstance(scene_type, str) else None
        technical_flaws = [item.strip() for item in technical_flaws if isinstance(item, str) and item.strip()][:3]
        composition_raw = _as_float(visual_quality_score.get("composition"))
        lighting_raw = _as_float(visual_quality_score.get("lighting"))
        subject_clarity_raw = _as_float(visual_quality_score.get("subject_clarity"))
        aesthetic_quality_raw = _as_float(visual_quality_score.get("aesthetic_quality"))
        if None in {composition_raw, lighting_raw, subject_clarity_raw, aesthetic_quality_raw}:
            raise ValueError("Invalid visual_quality_score fields.")
        normalized_visual_quality = {
            "composition": max(0.0, min(10.0, float(composition_raw))),
            "lighting": max(0.0, min(10.0, float(lighting_raw))),
            "subject_clarity": max(0.0, min(10.0, float(subject_clarity_raw))),
            "aesthetic_quality": max(0.0, min(10.0, float(aesthetic_quality_raw))),
        }
        clamped_hook_strength_score = max(0.0, min(1.0, float(hook_strength_score)))
        dominant_object = payload.get("dominant_object")
        lighting_quality = normalized_visual_quality.get("lighting")
        subject_clarity = normalized_visual_quality.get("subject_clarity")
        aesthetic_quality = normalized_visual_quality.get("aesthetic_quality")
        cringe_score = _clamp_int_0_100(payload.get("cringe_score"))
        cringe_signals = _normalize_short_text_list(payload.get("cringe_signals"), limit=3)
        cringe_fixes = _normalize_short_text_list(payload.get("cringe_fixes"), limit=3)
        if not cringe_fixes:
            cringe_fixes = _normalize_short_text_list(payload.get("fixes_to_reduce_cringe"), limit=3)
        production_level = _normalize_production_level(payload.get("production_level"))
        adult_content_detected = _normalize_optional_bool(payload.get("adult_content_detected"))
        adult_content_confidence = _clamp_int_0_100(payload.get("adult_content_confidence"))

        if cringe_score is not None:
            floored_score = enforce_cringe_floor(cringe_score, cringe_signals)
            floored_score = _apply_cringe_prompt_floor(floored_score, cringe_signals)
            if floored_score != cringe_score:
                logger.info(
                    "[Cringe] Applied cringe floor for media_url=%s score=%s->%s",
                    _sanitize_url_for_logging(media_url),
                    cringe_score,
                    floored_score,
                )
            cringe_score = floored_score
        cringe_label = derive_cringe_label(cringe_score)
        is_cringe = bool(cringe_score is not None and cringe_score >= 45)

        signal = {
            "objects": objects,
            "primary_objects": objects,
            "scene_description": scene_description,
            "detected_text": detected_text,
            "visual_style": visual_style,
            "hook_strength_score": clamped_hook_strength_score,
            "dominant_focus": dominant_focus if isinstance(dominant_focus, str) else None,
            "dominant_object": dominant_object if isinstance(dominant_object, str) else None,
            "scene_type": scene_type if isinstance(scene_type, str) else None,
            "lighting_quality": lighting_quality if isinstance(lighting_quality, (str, int, float)) else None,
            "subject_clarity": subject_clarity if isinstance(subject_clarity, (str, int, float)) else None,
            "aesthetic_quality": aesthetic_quality if isinstance(aesthetic_quality, (str, int, float)) else None,
            "visual_quality_score": normalized_visual_quality,
            "technical_flaws": technical_flaws,
            "cringe_score": cringe_score,
            "cringe_signals": cringe_signals,
            "cringe_fixes": cringe_fixes,
            "production_level": production_level,
            "is_cringe": is_cringe if cringe_score is not None else None,
            "cringe_label": cringe_label,
            "adult_content_detected": adult_content_detected,
            "adult_content_confidence": adult_content_confidence,
        }

        return VisionAnalysis(provider="gemini", status="ok", signals=[signal]).model_dump(mode="python")
    except Exception as e:
        logger.error(
            "[Vision] Gemini vision analysis failed for media_url=%s: %s",
            _sanitize_url_for_logging(media_url),
            e,
        )
        return VisionAnalysis(provider="gemini", status="error", signals=[]).model_dump(mode="python")


def _call_gemini_vision_api(*, api_key: str, instruction: str, media_url: str) -> str:
    import google.generativeai as genai

    # Use gemini-flash-latest for better compatibility with this SDK and free-tier quota.
    model_name = "gemini-flash-latest"
    try:
        # google.generativeai.configure() mutates global state, so guard configure+request.
        with _GENAI_LOCK:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([instruction, media_url])
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            logger.warning(
                "[Vision] Gemini %s returned no text for media_url=%s",
                model_name,
                _sanitize_url_for_logging(media_url),
            )
            raise ValueError("Gemini response did not include text output.")
        return text
    except Exception as e:
        logger.error(
            "[Vision] Gemini %s failed for media_url=%s: %s",
            model_name,
            _sanitize_url_for_logging(media_url),
            e,
        )
        raise


async def _generate_gemini_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
    try:
        # Wrap the threaded call in asyncio.wait_for to prevent infinite hang.
        # Shortened to 10s for smoke test to avoid long hangs.
        return await asyncio.wait_for(
            asyncio.to_thread(_call_gemini_vision_api, api_key=api_key, instruction=instruction, media_url=media_url),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        logger.error(
            "[Vision] Gemini vision analysis timed out for media_url=%s",
            _sanitize_url_for_logging(media_url),
        )
        raise


def _build_prompt(context: dict[str, Any], vision: dict[str, Any]) -> dict[str, Any]:
    """Build a compact prompt requesting strictly structured JSON output."""
    return {
        "system": (
            "You are an Instagram post analyst. "
            "Return ONLY valid JSON with keys: "
            "summary (string), "
            "drivers (array of objects with id, label, type, explanation), "
            "recommendations (array of objects with id, text, impact_level), "
            "engagement_potential_score (object with emotional_resonance, shareability, save_worthiness, "
            "comment_potential, novelty_or_value, total, notes). "
            "Do not include markdown, comments, or extra keys. "
            "Summary requirements: 3-5 sentences; must reference concrete values for reach and engagement_rate; "
            "must reference engagement_rate_percent_vs_avg when available; "
            "must reference percentile_engagement_rank when available; "
            "When citing metrics, reference metric keys exactly as they appear in the input JSON, including paths "
            "such as core_metrics.reach, derived_metrics.engagement_rate, "
            "benchmark_metrics.engagement_rate_percent_vs_avg, and "
            "benchmark_metrics.percentile_engagement_rank. "
            "The input includes deterministic S1 visual quality metrics under context.s1_visual_quality. "
            "Treat context.s1_visual_quality as fixed and authoritative. "
            "Do not recompute, alter, or replace S1 values. "
            "The input includes deterministic S2 caption effectiveness metrics under context.s2_caption_effectiveness. "
            "Treat context.s2_caption_effectiveness as fixed and authoritative. "
            "Do not recompute, alter, or replace S2 values. "
            "The input includes deterministic S3 content clarity metrics under context.s3_content_clarity. "
            "Treat context.s3_content_clarity as fixed and authoritative. "
            "Do not recompute, alter, or replace S3 values. "
            "The input includes deterministic S4 audience relevance metrics under context.s4_audience_relevance. "
            "Treat context.s4_audience_relevance as fixed and authoritative. "
            "Do not recompute, alter, or replace S4 values. "
            "The input includes deterministic S6 brand safety metrics under context.s6_brand_safety. "
            "Treat context.s6_brand_safety as fixed and authoritative. "
            "Do not recompute, alter, or replace S6 values. "
            "The input includes deterministic weighted post score under context.weighted_post_score. "
            "Treat context.weighted_post_score as fixed and authoritative. "
            "Do not recompute or alter weighted_post_score. "
            "Engagement potential rubric (0..10 each): "
            "emotional_resonance = relatability/emotional pull; "
            "shareability = likelihood users send to a friend; "
            "save_worthiness = likelihood users bookmark/save; "
            "comment_potential = likelihood content invites responses/questions; "
            "novelty_or_value = actionable value/insight/entertainment uniqueness. "
            "Set engagement_potential_score.total as the sum of these five sub-scores (0..50). "
            "engagement_potential_score schema is strict with keys exactly: "
            "emotional_resonance, shareability, save_worthiness, comment_potential, novelty_or_value, total, notes. "
            "All five sub-scores must be numeric values in range 0..10. "
            "total must be numeric 0..50. "
            "notes must be an array of strings (can be empty). "
            "Forbid extra keys at every level of the JSON output. "
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
        "response_format": {
            "type": "json_schema",
            "json_schema": S5_JSON_SCHEMA,
        },
    }


def _build_repair_prompt(raw_output: str) -> dict[str, Any]:
    return {
        "system": (
            "Repair the assistant output into valid JSON only. "
            "Return ONLY JSON matching this schema exactly and with no extra keys: "
            "{summary:string, drivers:[{id,label,type,explanation}], "
            "recommendations:[{id,text,impact_level}], "
            "engagement_potential_score:{emotional_resonance,shareability,save_worthiness,"
            "comment_potential,novelty_or_value,total,notes}}. "
            "Rules: driver.type in {POSITIVE,LIMITING}; recommendation.impact_level in {HIGH,MEDIUM,LOW}; "
            "all five engagement sub-scores numeric 0..10; total numeric 0..50; notes array of strings. "
            "If information is missing, fill safe defaults."
        ),
        "user": json.dumps({"raw_output": raw_output}, ensure_ascii=True),
        "response_format": {
            "type": "json_schema",
            "json_schema": S5_JSON_SCHEMA,
        },
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


async def _repair_llm_json_output(raw_text: str | None, llm_client: LLMClient | None) -> str | None:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None
    repair_prompt = _build_repair_prompt(raw_text)
    return await _call_llm_async(repair_prompt, llm_client)


async def run_caption_analysis_llm(caption_text: str, llm_client: LLMClient | None = None) -> dict[str, Any] | None:
    """Run LLM-based S2 caption evaluation and return normalized payload."""
    if not isinstance(caption_text, str) or not caption_text.strip():
        return None

    prompt = {
        "system": "Return only valid JSON matching the schema requested.",
        "user": S2_CAPTION_EVALUATION_PROMPT.replace("{caption_text}", caption_text),
    }
    raw_text = await _call_llm_async(prompt, llm_client)
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        repaired = await _repair_llm_json_output(raw_text, llm_client)
        if not isinstance(repaired, str):
            return None
        try:
            payload = json.loads(repaired)
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, dict):
        return None

    hook = _coerce_int_0_100(payload.get("hook_score_0_100"))
    length = _coerce_int_0_100(payload.get("length_score_0_100"))
    hashtag = _coerce_int_0_100(payload.get("hashtag_score_0_100"))
    cta = _coerce_int_0_100(payload.get("cta_score_0_100"))
    if None in {hook, length, hashtag, cta}:
        return None

    s2_raw = _coerce_int_0_100(payload.get("s2_raw_0_100"))
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

    return {
        "hook_score_0_100": hook,
        "length_score_0_100": length,
        "hashtag_score_0_100": hashtag,
        "cta_score_0_100": cta,
        "s2_raw_0_100": s2_raw,
        "total_0_50": total_0_50,
        "notes": notes,
    }


async def run_audience_relevance_llm(
    creator_category: str | None,
    post_category: str | None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any] | None:
    """Run LLM-based S4 audience relevance evaluation."""
    creator_text = creator_category or ""
    post_text = post_category or ""

    user_prompt = S4_AUDIENCE_RELEVANCE_PROMPT.replace("{creator_category}", creator_text).replace("{post_category}", post_text)
    prompt = {
        "system": "Return only valid JSON matching the schema requested.",
        "user": user_prompt,
    }
    raw_text = await _call_llm_async(prompt, llm_client)
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        repaired = await _repair_llm_json_output(raw_text, llm_client)
        if not isinstance(repaired, str):
            return None
        try:
            payload = json.loads(repaired)
        except json.JSONDecodeError:
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

    s4_raw = _coerce_int_0_100(payload.get("s4_raw_0_100"))
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

    return {
        "s4_raw_0_100": s4_raw,
        "affinity_band": affinity,
        "audience_overlap_explanation": explanation_text,
    }


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
) -> tuple[str | None, list[AIDriver], list[AIRecommendation], dict[str, Any] | None]:
    """Parse and strictly validate LLM output schema."""
    if not raw_text:
        return None, [], [], None

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return None, [], [], None

    if not isinstance(payload, dict):
        return None, [], [], None

    summary = payload.get("summary")
    drivers_raw = payload.get("drivers")
    recommendations_raw = payload.get("recommendations")
    engagement_potential_raw = payload.get("engagement_potential_score")

    if not isinstance(summary, str) or not summary.strip():
        return None, [], [], None
    if not isinstance(drivers_raw, list):
        return None, [], [], None
    if not isinstance(recommendations_raw, list):
        return None, [], [], None
    if not isinstance(engagement_potential_raw, dict):
        return None, [], [], None

    drivers: list[AIDriver] = []
    for item in drivers_raw:
        parsed_item = _parse_driver_item(item)
        if parsed_item is None:
            return None, [], [], None
        drivers.append(parsed_item)

    recommendations: list[AIRecommendation] = []
    for item in recommendations_raw:
        parsed_item = _parse_recommendation_item(item)
        if parsed_item is None:
            return None, [], [], None
        recommendations.append(parsed_item)

    summary = summary.strip()
    return summary, drivers, recommendations, engagement_potential_raw


async def _parse_llm_response_with_repair(
    raw_text: str | None,
    llm_client: LLMClient | None,
) -> tuple[str | None, list[AIDriver], list[AIRecommendation], dict[str, Any] | None]:
    parsed = _parse_llm_response(raw_text)
    summary, drivers, recommendations, engagement_potential_raw = parsed
    if summary is not None:
        primary_payload = sanitize_s5_payload(engagement_potential_raw)
        if primary_payload is not None and _sanitize_engagement_potential_score(primary_payload) is not None:
            return summary, drivers, recommendations, primary_payload

    repaired_text = await _repair_llm_json_output(raw_text, llm_client)
    repaired = _parse_llm_response(repaired_text)
    repaired_summary, repaired_drivers, repaired_recommendations, repaired_engagement = repaired
    if repaired_summary is None:
        return parsed

    repaired_payload = sanitize_s5_payload(repaired_engagement)
    if repaired_payload is None:
        return parsed
    if _sanitize_engagement_potential_score(repaired_payload) is None:
        return parsed
    return repaired_summary, repaired_drivers, repaired_recommendations, repaired_payload


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
) -> EngagementPotentialScore:
    if visual_quality_score.total < 15.0 and content_clarity_score.total < 15.0 and engagement_score.total > 30.0:
        notes = list(engagement_score.notes)
        notes.append("consistency cap applied: low S1 and S3 limited S5 total")
        return engagement_score.model_copy(update={"total": 30.0, "notes": notes})
    return engagement_score


def _fallback_summary(score: int, band: str) -> str:
    """Return deterministic fallback summary when LLM output is unavailable."""
    return f"Post scored {score}/100 ({band}) based on deterministic content signals."


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
                "label": "Weak visual hook",
                "type": "LIMITING",
                "explanation": f"Vision hook_strength_score is {hook_strength:.2f}, below the 0.40 threshold.",
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
                "label": "Unclear main message",
                "type": "LIMITING",
                "explanation": (
                    f"S3 content clarity total is {content_clarity_score.total:.2f}, "
                    "indicating weak message singularity and reinforcement."
                ),
            }
        )

    if content_clarity_score.cognitive_load < 5.0:
        drivers.append(
            {
                "id": "deterministic_high_cognitive_load",
                "label": "High cognitive load / clutter",
                "type": "LIMITING",
                "explanation": (
                    f"S3 cognitive_load is {content_clarity_score.cognitive_load:.2f}, "
                    "which indicates overload from clutter and/or text density."
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
    with _ANALYSIS_CACHE_LOCK:
        _prune_analysis_cache(now_ts)
        cached = _ANALYSIS_CACHE.get(key) if key is not None else None
        if cached is not None and _is_fresh(cached, now_ts):
            return cached.result
        if cached is not None and (now_ts - cached.last_regen_attempt_at) < MIN_REGEN_SECONDS:
            return cached.result
        if cached is not None:
            cached.last_regen_attempt_at = now_ts
    visual_quality_score = (
        post.visual_quality_score
        if isinstance(post.visual_quality_score, VisualQualityScore)
        else _default_visual_quality_score()
    )
    content_clarity_score = (
        post.content_clarity_score
        if isinstance(post.content_clarity_score, ContentClarityScore)
        else _default_content_clarity_score()
    )
    caption_effectiveness_score = (
        post.caption_effectiveness_score
        if isinstance(post.caption_effectiveness_score, CaptionEffectivenessScore)
        else _default_caption_effectiveness_score()
    )
    engagement_potential_score = (
        post.engagement_potential_score
        if isinstance(post.engagement_potential_score, EngagementPotentialScore)
        else _default_engagement_potential_score()
    )
    weighted_post_score = (
        post.weighted_post_score
        if isinstance(post.weighted_post_score, WeightedPostScore)
        else _default_weighted_post_score()
    )
    audience_relevance_score = (
        post.audience_relevance_score
        if isinstance(post.audience_relevance_score, AudienceRelevanceScore)
        else _default_audience_relevance_score()
    )
    brand_safety_score = (
        post.brand_safety_score
        if isinstance(post.brand_safety_score, BrandSafetyScore)
        else _default_brand_safety_score()
    )
    tier_avg_engagement_rate = post.tier_avg_engagement_rate
    predicted_engagement_rate = post.predicted_engagement_rate
    predicted_engagement_rate_notes = list(post.predicted_engagement_rate_notes)

    score, band = _score_payload(post)
    post_id = post.media_id if isinstance(post.media_id, str) else None
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    vision_enabled = bool(isinstance(gemini_api_key, str) and gemini_api_key.strip())
    warnings: list[AIWarning] = []
    if not vision_enabled:
        warnings.append(
            _build_ai_warning(
                code="GEMINI_API_KEY_MISSING",
                message="Gemini vision is disabled because GEMINI_API_KEY is not set.",
                post_id=post_id,
            )
        )
    vision_status: Literal["ok", "error", "disabled", "no_media"] = "disabled" if not vision_enabled else "ok"
    fallback_used = False

    if post.published_at is not None:
        published_at = post.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        now_utc = datetime.now(timezone.utc)
        post_age_seconds = (now_utc - published_at).total_seconds()
        if post_age_seconds < MIN_REGEN_SECONDS:
            fallback_used = True
            result: AIAnalysisResult = {
                "summary": "AI analysis unavailable. Post is still accumulating data.",
                "drivers": [],
                "recommendations": [],
                "ai_content_score": score,
                "ai_content_band": band,
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
                "tier_avg_engagement_rate": tier_avg_engagement_rate,
                "predicted_engagement_rate": predicted_engagement_rate,
                "predicted_engagement_rate_notes": predicted_engagement_rate_notes,
                "warnings": warnings,
                "vision_status": vision_status,
                "fallback_used": fallback_used,
            }
            if key is not None:
                with _ANALYSIS_CACHE_LOCK:
                    _ANALYSIS_CACHE[key] = _CacheEntry(
                        result=result,
                        cached_at=now_ts,
                        last_regen_attempt_at=now_ts,
                    )
                    _prune_analysis_cache(now_ts)
            return result

    if not vision_enabled:
        vision = VisionAnalysis(provider="gemini", status="error", signals=[]).model_dump(mode="python")
    else:
        vision = await run_vision_analysis(post)
        if vision.get("status") == "error":
            vision_status = "error"
            warnings.append(
                _build_ai_warning(
                    code="VISION_ERROR",
                    message="Gemini vision request failed; deterministic fallback scoring applied.",
                    post_id=post_id,
                )
            )
        elif vision.get("status") == "ok":
            vision_status = "ok"
        elif vision.get("status") == "no_media":
            vision_status = "no_media"

    visual_quality_score = compute_visual_quality_score(vision)
    caption_effectiveness_score = (
        post.caption_effectiveness_score
        if isinstance(post.caption_effectiveness_score, CaptionEffectivenessScore)
        else compute_s2_caption_effectiveness(post.caption_text)
    )
    content_clarity_score = compute_s3_content_clarity(vision, post.caption_text)
    audience_relevance_score = compute_s4_audience_relevance(
        post.post_category,
        post.creator_dominant_category,
    )
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
        s4=audience_relevance_score.total_0_50,
        s5=None,
        s6=brand_safety_score.total_0_50,
        s7=None,
    )
    post.weighted_post_score = weighted_post_score
    try:
        post.vision_analysis = VisionAnalysis.model_validate(vision)
    except Exception:
        post.vision_analysis = VisionAnalysis(provider="gemini", status="error", signals=[])
    deterministic_drivers = _build_deterministic_visual_drivers(vision) + _build_deterministic_clarity_drivers(
        content_clarity_score
    )

    context = build_ai_input_context(
        post,
        score,
        band,
        visual_quality_score,
        content_clarity_score,
        caption_effectiveness_score,
        audience_relevance_score,
        brand_safety_score,
        weighted_post_score,
    )
    prompt = _build_prompt(context, vision)

    llm_text = await _call_llm_async(prompt, llm_client)
    summary, drivers, recommendations, engagement_potential_raw = await _parse_llm_response_with_repair(
        llm_text,
        llm_client,
    )

    if summary is None:
        summary = _fallback_summary(score, band)
        drivers = deterministic_drivers
        recommendations = []
        engagement_potential_score = _fallback_engagement_potential_score()
        fallback_used = True
    else:
        drivers = deterministic_drivers + drivers
        engagement_potential_score = _sanitize_engagement_potential_score(engagement_potential_raw)
        if engagement_potential_score is None:
            engagement_potential_score = _fallback_engagement_potential_score()
            fallback_used = True

    if vision_status in {"disabled", "error"}:
        fallback_used = True

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
        s4=audience_relevance_score.total_0_50,
        s5=engagement_potential_score.total,
        s6=brand_safety_score.total_0_50,
        s7=None,
    )
    post.weighted_post_score = weighted_post_score
    tier_avg_engagement_rate, tier_notes = _resolve_tier_avg_engagement_rate(post)
    predicted_engagement_rate, prediction_notes = compute_predicted_engagement_rate(
        tier_avg_engagement_rate,
        engagement_potential_score.total,
    )
    predicted_engagement_rate_notes = tier_notes + prediction_notes
    post.tier_avg_engagement_rate = tier_avg_engagement_rate
    post.predicted_engagement_rate = predicted_engagement_rate
    post.predicted_engagement_rate_notes = predicted_engagement_rate_notes

    result: AIAnalysisResult = {
        "summary": summary,
        "drivers": drivers,
        "recommendations": recommendations,
        "ai_content_score": score,
        "ai_content_band": band,
        "caption_effectiveness_score": caption_effectiveness_score.model_dump(),
        "visual_quality_score": visual_quality_score.model_dump(),
        "content_clarity_score": content_clarity_score.model_dump(),
        "engagement_potential_score": engagement_potential_score.model_dump(),
        "audience_relevance_score": audience_relevance_score.model_dump(),
        "brand_safety_score": brand_safety_score.model_dump(),
        "weighted_post_score": weighted_post_score.model_dump(),
        "vision_analysis": vision,
        "tier_avg_engagement_rate": tier_avg_engagement_rate,
        "predicted_engagement_rate": predicted_engagement_rate,
        "predicted_engagement_rate_notes": predicted_engagement_rate_notes,
        "warnings": warnings,
        "vision_status": vision_status,
        "fallback_used": fallback_used,
    }

    if key is not None:
        with _ANALYSIS_CACHE_LOCK:
            _ANALYSIS_CACHE[key] = _CacheEntry(
                result=result,
                cached_at=now_ts,
                last_regen_attempt_at=now_ts,
            )
            _prune_analysis_cache(now_ts)
    return result
