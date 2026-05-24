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
from urllib.parse import urlparse, urlunparse

import httpx

from backend.app.ai.cringe_analysis import derive_cringe_label, enforce_cringe_floor
from backend.app.ai.prompts import S2_CAPTION_EVALUATION_PROMPT, S4_AUDIENCE_RELEVANCE_PROMPT, format_user_text_block
from backend.app.ai.toon import loads as toon_loads
from backend.app.ai.llm_client import LLMClient
from backend.app.analytics.caption_s2_engine import analyze_caption_via_llm
from backend.app.analytics.content_score import compute_content_score
from backend.app.analytics.post_weighted_score_engine import compute_weighted_post_score
from backend.app.analytics.predicted_er_engine import compute_predicted_engagement_rate
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
    SinglePostInsights,
    VisionAnalysis,
    VisualQualityScore,
    WeightedPostScore,
)
from backend.app.utils.logger import logger


CACHE_TTL_SECONDS = 86400
MIN_REGEN_SECONDS = 1
ANALYSIS_CACHE_MAX_ENTRIES = 1024
_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


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
    vision_error_reason: NotRequired[str | None]


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


async def run_vision_analysis(
    post: SinglePostInsights,
) -> dict[str, Any]:
    """Run Gemini Vision analysis for a post media URL with strict TOON parsing."""
    from urllib.parse import urlparse

    post_id = post.media_id if isinstance(post.media_id, str) else None

    instruction = (
        "You are an expert Social Media Art Director and Computer Vision analysis engine. "
        "Analyze the provided Instagram media (image or video) strictly through the lens of technical visual quality "
        "and compositional structure. If the media is a video, you MUST watch it from beginning to end. "
        "Your analysis and scene_description must account for the entire duration, including any scene changes, "
        "unexpected twists, or different content in the second half. "
        "Keep the scene_description VERY CONCISE (maximum 2 sentences). Focus only on the core actions and twists. "
        "Return ONLY valid TOON format (Token-Oriented Object Notation). "
        "Use 2-space indentation for nesting. Do not use braces, brackets, or quotes.\n\n"
        "You must evaluate the image objectively on the following deterministic rules to calculate S1 sub-scores:\n"
        "1) COMPOSITION (0-10): Rule of Thirds/symmetry (+3), dominant_focus present (+4), >4 primary objects (-3), "
        "awkward crops (-3), remaining points (0-3) for depth-of-field/subject isolation.\n"
        "2) LIGHTING_QUALITY (0-10): subject illumination/contrast (+4), blown highlights or crushed blacks (-3), "
        "intentional depth (rim/softbox/golden hour +3) vs flat lighting (+1), poor white balance (-2), "
        "remaining points for cinematic/aesthetic lighting.\n"
        "3) SUBJECT_CLARITY (0-10): subject in focus (+5), clear separation (+3), visible expressive face if human (+2).\n"
        "4) AESTHETIC_QUALITY (0-10): pro color grade (+3), harmonious palette (+2), "
        "heavy text overlays (-3) or very heavy (-5), remaining points for premium visual feel.\n\n"
        "Output TOON must include exactly these keys:\n"
        "objects\n"
        "  - string\n"
        "dominant_focus value_or_null\n"
        "scene_description value\n"
        "visual_style value\n"
        "scene_type value_or_null\n"
        "visual_quality_score\n"
        "  composition 0.0-10.0\n"
        "  lighting 0.0-10.0\n"
        "  subject_clarity 0.0-10.0\n"
        "  aesthetic_quality 0.0-10.0\n"
        "technical_flaws\n"
        "  - string\n"
        "detected_text value_or_null\n"
        "hook_strength_score 0.0-1.0\n"
        "cringe_score 0-100\n"
        "cringe_signals\n"
        "  - string\n"
        "cringe_fixes\n"
        "  - string\n"
        "production_level low|medium|high\n"
        "adult_content_detected true|false\n"
        "adult_content_confidence 0-100\n\n"
        "Cringe rubric (EXTREMELY FORGIVING): "
        "0-40: Normal social media behavior. Includes gym selfies, mirror selfies, typical flexing, slightly awkward posing, filters, and standard candids. DO NOT penalize these. "
        "41-60: Very awkward, but still borderline acceptable. "
        "61-80: Undeniable cringe. Deeply uncomfortable, bizarrely out of touch, or severely forced interactions. "
        "81-100: Extreme cringe. Nonsensical, absolutely horrible execution, socially oblivious. "
        "Floor rules: ONLY apply cringe scores > 50 to the absolute worst, most egregiously awful content."
    )

    media_url = post.media_url
    if not isinstance(media_url, str) or not media_url.strip():
        return VisionAnalysis(provider="gemini", status="no_media", signals=[]).model_dump(mode="python")
    logger.debug("[Vision] Start media_id=%s", post_id)

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
            "[Vision] Rejected media_url for SSRF protection media_id=%s url=%s",
            post_id,
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
        stripped_raw_text = raw_text.strip()
        if stripped_raw_text.startswith("```"):
            lines = stripped_raw_text.splitlines()
            if len(lines) > 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
                stripped_raw_text = "\n".join(lines[1:-1]).strip()

        try:
            if "{" in stripped_raw_text and "}" in stripped_raw_text:
                start = stripped_raw_text.find("{")
                end = stripped_raw_text.rfind("}") + 1
                payload = json.loads(stripped_raw_text[start:end])
            else:
                payload = toon_loads(stripped_raw_text)
        except Exception:
            payload = toon_loads(stripped_raw_text)
        if not isinstance(payload, dict):
            raise ValueError("Gemini output must be a TOON object.")

        objects = payload.get("objects") or []
        dominant_focus = payload.get("dominant_focus")
        scene_description = payload.get("scene_description") or ""
        detected_text = payload.get("detected_text")
        visual_style = payload.get("visual_style") or "Unknown"
        scene_type = payload.get("scene_type")
        visual_quality_score = payload.get("visual_quality_score") or {}
        technical_flaws = _normalize_short_text_list(payload.get("technical_flaws"), limit=3)
        hook_strength_score = payload.get("hook_strength_score")

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
        if not isinstance(visual_quality_score, dict):
            visual_quality_score = {}
        if not isinstance(hook_strength_score, (int, float)):
            hook_strength_score = 0.5

        objects = [
            item.strip()
            for item in objects
            if isinstance(item, str) and item.strip()
        ]
        dominant_focus = dominant_focus.strip() if isinstance(dominant_focus, str) else None
        scene_description = scene_description.strip() if isinstance(scene_description, str) else ""
        detected_text = detected_text.strip() if detected_text else None
        visual_style = visual_style.strip() if isinstance(visual_style, str) else "Unknown"
        scene_type = scene_type.strip() if isinstance(scene_type, str) else None
        composition_raw = _as_float(visual_quality_score.get("composition"))
        lighting_raw = _as_float(visual_quality_score.get("lighting"))
        subject_clarity_raw = _as_float(visual_quality_score.get("subject_clarity"))
        aesthetic_quality_raw = _as_float(visual_quality_score.get("aesthetic_quality"))
        if None in {composition_raw, lighting_raw, subject_clarity_raw, aesthetic_quality_raw}:
            normalized_visual_quality = None
        else:
            normalized_visual_quality = {
                "composition": max(0.0, min(10.0, float(composition_raw))),
                "lighting": max(0.0, min(10.0, float(lighting_raw))),
                "subject_clarity": max(0.0, min(10.0, float(subject_clarity_raw))),
                "aesthetic_quality": max(0.0, min(10.0, float(aesthetic_quality_raw))),
            }
        clamped_hook_strength_score = max(0.0, min(1.0, float(hook_strength_score)))
        dominant_object = payload.get("dominant_object")
        lighting_quality = normalized_visual_quality.get("lighting") if isinstance(normalized_visual_quality, dict) else None
        subject_clarity = normalized_visual_quality.get("subject_clarity") if isinstance(normalized_visual_quality, dict) else None
        aesthetic_quality = normalized_visual_quality.get("aesthetic_quality") if isinstance(normalized_visual_quality, dict) else None
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
        error_reason = str(e).strip() or e.__class__.__name__
        
        if "SAFETY_BLOCK" in error_reason:
            logger.warning("[Vision] Caught safety block for %s: %s", post_id, error_reason)
            synthetic_signal = {
                "objects": [],
                "primary_objects": [],
                "scene_description": "Content blocked by AI safety filters.",
                "detected_text": None,
                "visual_style": None,
                "hook_strength_score": 0.0,
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
                "adult_content_confidence": 100,
            }
            return VisionAnalysis(provider="gemini", status="ok", signals=[synthetic_signal]).model_dump(mode="python")
            
        logger.error(
            "[Vision] Gemini vision analysis failed for media_id=%s media_url=%s: %s",
            post_id,
            _sanitize_url_for_logging(media_url),
            error_reason,
        )
        failure_payload = VisionAnalysis(provider="gemini", status="error", signals=[]).model_dump(mode="python")
        # Keep a compact reason so post summaries can explain exactly why fallback happened.
        failure_payload["error_reason"] = error_reason[:300]
        return failure_payload


def _infer_mime_type(url: str) -> str:
    from urllib.parse import urlparse, parse_qs
    
    url_lower = url.lower()
    parsed = urlparse(url_lower)
    qs = parse_qs(parsed.query)
    
    filename = ""
    if "filename" in qs and qs["filename"]:
        filename = qs["filename"][0]
        
    path = parsed.path
    
    if filename.endswith(".mp4") or path.endswith(".mp4") or ".mp4" in url_lower:
        return "video/mp4"
    if filename.endswith(".png") or path.endswith(".png"):
        return "image/png"
    if filename.endswith(".gif") or path.endswith(".gif"):
        return "image/gif"
    if filename.endswith(".webp") or path.endswith(".webp"):
        return "image/webp"
        
    return "image/jpeg"


def _build_gemini_vision_adapter():
    """Return a small adapter over whichever Gemini SDK is installed."""
    try:
        from google import genai
        from google.genai import types as genai_types

        if not hasattr(genai, "Client"):
            raise ImportError("google.genai.Client is unavailable")

        class _GoogleGenaiVisionAdapter:
            def __init__(self, api_key: str) -> None:
                self._client = genai.Client(api_key=api_key)

            def generate_content(self, *, model_name: str, instruction: str, media_url: str, mime_type: str):
                image_part = genai_types.Part.from_uri(file_uri=media_url, mime_type=mime_type)
                return self._client.models.generate_content(
                    model=model_name,
                    contents=[instruction, image_part],
                )

        return _GoogleGenaiVisionAdapter
    except ImportError:
        import google.generativeai as legacy_genai

        class _LegacyGenaiVisionAdapter:
            def __init__(self, api_key: str) -> None:
                legacy_genai.configure(api_key=api_key)

            def _generate_with_uploaded_file(
                self,
                *,
                model_name: str,
                instruction: str,
                media_url: str,
                mime_type: str,
            ):
                uploaded = None
                temp_path = None
                try:
                    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                        response = client.get(media_url)
                        response.raise_for_status()
                    suffix = ".mp4" if mime_type == "video/mp4" else ".jpg"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(response.content)
                        temp_path = tmp.name
                    uploaded = legacy_genai.upload_file(temp_path, mime_type=mime_type)
                    return legacy_genai.GenerativeModel(model_name).generate_content([instruction, uploaded])
                finally:
                    if uploaded is not None and getattr(uploaded, "name", None):
                        try:
                            legacy_genai.delete_file(uploaded.name)
                        except Exception:
                            logger.debug("[Vision] Legacy Gemini cleanup failed for uploaded file.")
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            logger.debug("[Vision] Temporary Gemini upload file cleanup failed: %s", temp_path)

            def generate_content(self, *, model_name: str, instruction: str, media_url: str, mime_type: str):
                model = legacy_genai.GenerativeModel(model_name)
                try:
                    return model.generate_content(
                        [
                            instruction,
                            {
                                "mime_type": mime_type,
                                "file_uri": media_url,
                            },
                        ]
                    )
                except Exception:
                    # Older SDKs may require a local uploaded file instead of a remote URI part.
                    return self._generate_with_uploaded_file(
                        model_name=model_name,
                        instruction=instruction,
                        media_url=media_url,
                        mime_type=mime_type,
                    )

        return _LegacyGenaiVisionAdapter


def _call_gemini_vision_api(*, api_key: str, instruction: str, media_url: str) -> str:
    model_name = os.getenv("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)
    try:
        gemini_adapter_cls = _build_gemini_vision_adapter()
        with _GENAI_LOCK:
            client = gemini_adapter_cls(api_key=api_key)
            mime = _infer_mime_type(media_url)
            response = client.generate_content(
                model_name=model_name,
                instruction=instruction,
                media_url=media_url,
                mime_type=mime,
            )
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            block_reason = None
            if hasattr(response, "prompt_feedback") and response.prompt_feedback:
                block_reason = getattr(response.prompt_feedback, "block_reason", None)
            
            if block_reason:
                raise ValueError(f"SAFETY_BLOCK: {block_reason}")
                
            logger.warning(
                "[Vision] Gemini %s returned no text for media_url=%s. Raw response: %s",
                model_name,
                _sanitize_url_for_logging(media_url),
                response,
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
            timeout=120.0
        )
    except asyncio.TimeoutError:
        logger.error(
            "[Vision] Gemini vision analysis timed out for media_url=%s",
            _sanitize_url_for_logging(media_url),
        )
        raise


def _build_prompt(context: dict[str, Any], vision: dict[str, Any]) -> dict[str, Any]:
    """Build a compact prompt requesting strictly structured TOON output."""
    return {
        "system": (
            "You are an Instagram post analyst. "
            "Return ONLY valid TOON format (Token-Oriented Object Notation). "
            "Use 2-space indentation for nesting. Do not use braces, brackets, or quotes. "
            "For lists of objects, put '-' on its own line and indent fields beneath it. "
            "Example:\n"
            "summary Example summary.\n"
            "drivers\n"
            "  -\n"
            "    id driver_1\n"
            "    label Strong hook\n"
            "    type POSITIVE\n"
            "    explanation Uses core_metrics.reach\n"
            "recommendations\n"
            "  -\n"
            "    id rec_1\n"
            "    text Add a clear CTA\n"
            "    impact_level HIGH\n"
            "engagement_potential_score\n"
            "  emotional_resonance 6\n"
            "  shareability 5\n"
            "  save_worthiness 4\n"
            "  comment_potential 3\n"
            "  novelty_or_value 5\n"
            "  total 23\n"
            "  notes\n"
            "    - concise note\n"
            "Return ONLY valid TOON with keys: "
            "summary (string), "
            "drivers (array of objects with id, label, type, explanation), "
            "recommendations (array of objects with id, text, impact_level), "
            "engagement_potential_score (object with emotional_resonance, shareability, save_worthiness, "
            "comment_potential, novelty_or_value, total, notes). "
            "Do not include markdown, comments, or extra keys. "
            "Summary requirements: 3-5 sentences; must reference concrete values for reach and engagement_rate; "
            "must reference engagement_rate_percent_vs_avg when available; "
            "must reference percentile_engagement_rank when available; "
            "When citing metrics, reference metric keys exactly as they appear in the input payload, including paths "
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
            "Forbid extra keys at every level of the TOON output. "
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


def _build_repair_prompt(raw_output: str) -> dict[str, Any]:
    return {
        "system": (
            "Repair the assistant output into valid TOON only. "
            "Return ONLY TOON with these keys and no extra keys: "
            "summary, drivers, recommendations, engagement_potential_score. "
            "Use 2-space indentation for nesting and '-' for list items. "
            "Rules: driver.type in {POSITIVE,LIMITING}; recommendation.impact_level in {HIGH,MEDIUM,LOW}; "
            "all five engagement sub-scores numeric 0..10; total numeric 0..50; notes array of strings. "
            "If information is missing, fill safe defaults."
        ),
        "user": json.dumps({"raw_output": raw_output}, ensure_ascii=True),
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


async def _repair_llm_toon_output(raw_text: str | None, llm_client: LLMClient | None) -> str | None:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None
    repair_prompt = _build_repair_prompt(raw_text)
    return await _call_llm_async(repair_prompt, llm_client)


async def run_caption_analysis_llm(caption_text: str, llm_client: LLMClient | None = None) -> dict[str, Any] | None:
    """Run LLM-based S2 caption evaluation and return normalized payload."""
    if not isinstance(caption_text, str) or not caption_text.strip():
        return None
    logger.debug("[AIAnalysis] Caption LLM start length=%d", len(caption_text.strip()))

    prompt = {
        "system": (
            "Return only valid TOON format (Token-Oriented Object Notation). "
            "Use 2-space indentation for nesting. Do not use braces, brackets, or quotes."
        ),
        "user": S2_CAPTION_EVALUATION_PROMPT.replace("{caption_text}", format_user_text_block(caption_text)),
    }
    raw_text = await _call_llm_async(prompt, llm_client)
    if not isinstance(raw_text, str) or not raw_text.strip():
        logger.debug("[AIAnalysis] Caption LLM returned empty response")
        return None

    try:
        payload = toon_loads(raw_text)
    except Exception:
        logger.debug("[AIAnalysis] Caption LLM parse failed; attempting repair")
        repaired = await _repair_llm_toon_output(raw_text, llm_client)
        if not isinstance(repaired, str):
            return None
        try:
            payload = toon_loads(repaired)
        except Exception:
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

    user_prompt = S4_AUDIENCE_RELEVANCE_PROMPT.replace("{creator_category}", creator_text).replace("{post_category}", post_text)
    prompt = {
        "system": (
            "Return only valid TOON format (Token-Oriented Object Notation). "
            "Use 2-space indentation for nesting. Do not use braces, brackets, or quotes."
        ),
        "user": user_prompt,
    }
    raw_text = await _call_llm_async(prompt, llm_client)
    if not isinstance(raw_text, str) or not raw_text.strip():
        logger.debug("[AIAnalysis] Audience LLM returned empty response")
        return None

    try:
        payload = toon_loads(raw_text)
    except Exception:
        logger.debug("[AIAnalysis] Audience LLM parse failed; attempting repair")
        repaired = await _repair_llm_toon_output(raw_text, llm_client)
        if not isinstance(repaired, str):
            return None
        try:
            payload = toon_loads(repaired)
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
        payload = toon_loads(raw_text)
    except Exception:
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

    repaired_text = await _repair_llm_toon_output(raw_text, llm_client)
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
    vision_error_reason: str | None = None
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
            logger.info(
                "[AIAnalysis] Skipping AI analysis for very recent post media_id=%s age_seconds=%.2f",
                post.media_id,
                post_age_seconds,
            )
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

    visual_quality_score = compute_visual_quality_score(vision)
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
    logger.debug(
        "[AIAnalysis] Deterministic scores media_id=%s s1=%s s2=%s s3=%s s4=%s s6=%s weighted=%s",
        post.media_id,
        visual_quality_score.total,
        caption_effectiveness_score.total_0_50,
        content_clarity_score.total,
        audience_relevance_score.total_0_50,
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
    logger.debug(
        "[AIAnalysis] LLM parsed media_id=%s summary_present=%s drivers=%d recommendations=%d",
        post.media_id,
        summary is not None,
        len(drivers or []),
        len(recommendations or []),
    )

    if summary is None:
        summary = _fallback_summary(score, band)
        drivers = deterministic_drivers
        recommendations = []
        engagement_potential_score = _fallback_engagement_potential_score()
        fallback_used = True
        logger.info("[AIAnalysis] Using fallback summary media_id=%s", post.media_id)
    else:
        drivers = deterministic_drivers + drivers
        engagement_potential_score = _sanitize_engagement_potential_score(engagement_potential_raw)
        if engagement_potential_score is None:
            engagement_potential_score = _fallback_engagement_potential_score()
            fallback_used = True
            logger.info("[AIAnalysis] Using fallback S5 score media_id=%s", post.media_id)

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
    logger.debug(
        "[AIAnalysis] Final scores media_id=%s s5=%s weighted=%s fallback_used=%s",
        post.media_id,
        engagement_potential_score.total,
        weighted_post_score.score,
        fallback_used,
    )
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
    if vision_error_reason:
        result["vision_error_reason"] = vision_error_reason

    if key is not None:
        with _ANALYSIS_CACHE_LOCK:
            _ANALYSIS_CACHE[key] = _CacheEntry(
                result=result,
                cached_at=now_ts,
                last_regen_attempt_at=now_ts,
            )
            _prune_analysis_cache(now_ts)
    logger.info(
        "[AIAnalysis] Completed media_id=%s vision_status=%s warnings=%d fallback_used=%s",
        post.media_id,
        vision_status,
        len(warnings),
        fallback_used,
    )
    return result
