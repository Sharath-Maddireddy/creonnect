"""API routes for single-post analysis."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.ai.cringe_analysis import build_cringe_section_for_brand_safety
from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.api.auth import verify_api_key
from backend.app.api.instagram_auth_routes import AuthenticatedInstagramUser, get_current_instagram_user
from backend.app.utils.env import is_production_environment
from backend.app.domain.post_models import SinglePostInsights, VisionAnalysis
from backend.app.infra.redis_client import get_json, set_json
from backend.app.infra.outbound_media import unwrap_supported_media_proxy_url
from backend.app.services.post_insights_service import build_single_post_insights
from backend.app.services.post_score_history_store import get_account_score_baseline, record_post_score_snapshot
from backend.app.services.single_post_analysis_jobs import (
    enqueue_single_post_analysis_job_async,
    get_single_post_analysis_job_status,
    run_single_post_analysis_inline,
)
from backend.app.services.post_snapshot_store import read_post_insights_snapshot
from backend.app.utils.logger import logger
from backend.app.utils.number_utils import safe_float as _safe_float


router = APIRouter(tags=["Post Analysis"])
v1_router = APIRouter(prefix="/api/v1", tags=["Post Analysis"])
legacy_router = APIRouter(prefix="/api", tags=["Post Analysis"])
CRINGE_SUMMARY_CACHE_KEY_PREFIX = "post:cringe_summary:"
CRINGE_SUMMARY_CACHE_TTL_SECONDS = 86400
CRINGE_SUMMARY_CACHE_MAX_ENTRIES = 512
POST_ANALYSIS_CONTRACT_VERSION = "v2"
# Best-effort process-local fallback for single-process/dev when Redis is unavailable.
_CRINGE_SUMMARY_CACHE: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_CRINGE_SUMMARY_CACHE_LOCK = threading.Lock()


def _require_post_analysis_api_key_if_configured(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str | None:
    if not is_production_environment():
        return None

    expected_api_key = (os.getenv("BRAND_API_KEY") or "").strip()
    if not expected_api_key:
        raise HTTPException(status_code=503, detail="Post analysis is unavailable until service authentication is configured.")
    return verify_api_key(x_api_key)


def _request_for_current_user(request: "PostAnalysisRequest", current_user: AuthenticatedInstagramUser) -> "PostAnalysisRequest":
    requested_account = request.account_id or request.creator_id
    if requested_account and requested_account != current_user.id:
        raise HTTPException(status_code=403, detail="You are not allowed to analyze another account.")
    return request.model_copy(update={"account_id": current_user.id, "creator_id": current_user.id})


class PostAnalysisRequest(BaseModel):
    """Request payload for single-post analysis endpoint."""

    model_config = ConfigDict(extra="forbid")

    post_id: str | None = None
    account_id: str | None = None
    creator_id: str | None = None
    platform: str = "instagram"
    post_type: Literal["AUTO", "IMAGE", "REEL", "CAROUSEL"] = "AUTO"
    media_url: str
    media_urls: list[str] = Field(default_factory=list, max_length=10)
    thumbnail_url: str = ""
    caption_text: str = ""
    hashtags: list[str] = Field(default_factory=list)
    likes: int = 0
    comments: int = 0
    views: int | None = None
    audio_name: str | None = None
    posted_at: datetime | None = None
    actor_user_id: str | None = None
    actor_user_email: str | None = None

    @field_validator("media_url", mode="before")
    @classmethod
    def _validate_media_url(cls, value: Any) -> str:
        text = value.strip() if isinstance(value, str) else ""
        if not text:
            raise ValueError("media_url must be non-empty.")
        return unwrap_supported_media_proxy_url(text)

    @field_validator("post_type", mode="before")
    @classmethod
    def _normalize_post_type(cls, value: Any) -> Literal["AUTO", "IMAGE", "REEL", "CAROUSEL"]:
        text = value.strip().upper() if isinstance(value, str) else ""
        if text in {"REEL", "VIDEO", "REELS", "CLIPS"}:
            return "REEL"
        if text in {"CAROUSEL", "ALBUM"}:
            return "CAROUSEL"
        if text in {"IMAGE", "POST"}:
            return "IMAGE"
        return "AUTO"

    @field_validator("media_urls", mode="before")
    @classmethod
    def _normalize_media_urls(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [unwrap_supported_media_proxy_url(item.strip()) for item in value if isinstance(item, str) and item.strip()]

    @field_validator("post_id", "account_id", "creator_id", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text if text else None


def _stable_post_id(*, media_url: str, post_type: str, caption_text: str) -> str:
    payload = json.dumps(
        [media_url, post_type, caption_text],
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:24]
    return f"auto_{digest}"


def _resolve_post_type(request: PostAnalysisRequest) -> Literal["IMAGE", "REEL", "CAROUSEL"]:
    if len(request.media_urls) >= 2 or request.post_type == "CAROUSEL":
        return "CAROUSEL"
    if request.post_type in {"IMAGE", "REEL"}:
        return request.post_type
    suffix = urlparse(request.media_url).path.lower()
    return "REEL" if suffix.endswith((".mp4", ".mov", ".webm", ".m4v")) else "IMAGE"


def _cringe_summary_key(account_id: str, post_id: str) -> str:
    return f"{CRINGE_SUMMARY_CACHE_KEY_PREFIX}{account_id}:{post_id}"


def _set_local_cringe_summary_cache(account_id: str, post_id: str, payload: dict[str, Any]) -> None:
    expires_at = time.monotonic() + CRINGE_SUMMARY_CACHE_TTL_SECONDS
    cache_key = _cringe_summary_key(account_id, post_id)
    _CRINGE_SUMMARY_CACHE.pop(cache_key, None)
    _CRINGE_SUMMARY_CACHE[cache_key] = (expires_at, dict(payload))

    while len(_CRINGE_SUMMARY_CACHE) > CRINGE_SUMMARY_CACHE_MAX_ENTRIES:
        _CRINGE_SUMMARY_CACHE.popitem(last=False)


def _get_local_cringe_summary_cache(account_id: str, post_id: str) -> dict[str, Any] | None:
    cache_key = _cringe_summary_key(account_id, post_id)
    cached_entry = _CRINGE_SUMMARY_CACHE.get(cache_key)
    if cached_entry is None:
        return None

    expires_at, payload = cached_entry
    if expires_at <= time.monotonic():
        _CRINGE_SUMMARY_CACHE.pop(cache_key, None)
        return None

    _CRINGE_SUMMARY_CACHE.move_to_end(cache_key)
    return dict(payload)


def _write_cringe_summary(account_id: str, post_id: str, payload: dict[str, Any]) -> None:
    normalized_account_id = account_id.strip() if isinstance(account_id, str) else ""
    normalized_post_id = post_id.strip()
    if not normalized_account_id or not normalized_post_id:
        return
    try:
        set_json(
            _cringe_summary_key(normalized_account_id, normalized_post_id),
            payload,
            ttl_seconds=CRINGE_SUMMARY_CACHE_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "[PostAnalysis] Failed to write cringe summary to Redis for post_id=%s: %s",
            normalized_post_id,
            exc,
        )
    with _CRINGE_SUMMARY_CACHE_LOCK:
        _set_local_cringe_summary_cache(normalized_account_id, normalized_post_id, payload)


def _read_cringe_summary(account_id: str, post_id: str) -> dict[str, Any] | None:
    normalized_account_id = account_id.strip() if isinstance(account_id, str) else ""
    normalized_post_id = post_id.strip()
    if not normalized_account_id or not normalized_post_id:
        return None
    try:
        payload = get_json(_cringe_summary_key(normalized_account_id, normalized_post_id))
    except Exception as exc:
        logger.warning(
            "[PostAnalysis] Failed to read cringe summary from Redis for post_id=%s: %s",
            normalized_post_id,
            exc,
        )
        payload = None

    if isinstance(payload, dict):
        with _CRINGE_SUMMARY_CACHE_LOCK:
            _set_local_cringe_summary_cache(normalized_account_id, normalized_post_id, payload)
        return payload

    with _CRINGE_SUMMARY_CACHE_LOCK:
        return _get_local_cringe_summary_cache(normalized_account_id, normalized_post_id)


def _post_payload(post: SinglePostInsights, fallback_post_id: str, fallback_media_url: str) -> dict[str, Any]:
    return {
        "post_id": post.media_id or fallback_post_id,
        "post_type": post.media_type or "IMAGE",
        "media_url": post.media_url or fallback_media_url,
        "caption_text": post.caption_text or "",
    }


def _vision_payload(post: SinglePostInsights, ai_analysis: dict[str, Any]) -> dict[str, Any]:
    valid_statuses = {"ok", "error", "disabled", "no_media"}
    vision_status: str | None = None
    post_status = post.vision_analysis.status if post.vision_analysis is not None and isinstance(post.vision_analysis.status, str) else None
    ai_status = ai_analysis.get("vision_status")
    post_identifier = post.media_id or "unknown"

    if post_status is not None:
        if post_status in valid_statuses:
            vision_status = post_status
        else:
            vision_status = post_status
            logger.warning(
                "[PostAnalysis] Unexpected post vision status '%s' for post_id=%s; preserving original status.",
                post_status,
                post_identifier,
            )
    elif isinstance(ai_status, str) and ai_status in valid_statuses:
        vision_status = ai_status
    else:
        vision_status = "error"

    if post.vision_analysis is not None:
        payload = post.vision_analysis.model_dump(mode="python")
        payload["status"] = str(vision_status)
        return payload
    cached_vision = ai_analysis.get("vision_analysis")
    if isinstance(cached_vision, dict):
        try:
            payload = VisionAnalysis.model_validate(cached_vision).model_dump(mode="python")
            payload["status"] = str(vision_status)
            return payload
        except Exception:
            logger.debug(
                "Failed to validate cached vision_analysis payload: %s",
                cached_vision,
                exc_info=True,
            )
    return VisionAnalysis(provider="gemini", status=str(vision_status), signals=[]).model_dump(mode="python")


def _cringe_summary_from_vision(vision_payload: dict[str, Any]) -> dict[str, Any]:
    section = build_cringe_section_for_brand_safety(vision_payload)
    signals = vision_payload.get("signals")
    first_signal = signals[0] if isinstance(signals, list) and signals and isinstance(signals[0], dict) else {}
    raw_fixes = first_signal.get("cringe_fixes")
    cringe_fixes = [item.strip() for item in raw_fixes if isinstance(item, str) and item.strip()] if isinstance(raw_fixes, list) else []

    return {
        "cringe_score": section.get("cringe_score"),
        "cringe_label": section.get("cringe_label"),
        "is_cringe": bool(section.get("is_cringe", False)),
        "cringe_signals": section.get("cringe_signals", []),
        "cringe_fixes": cringe_fixes[:3],
        "production_level": section.get("production_level"),
        "adult_content_detected": bool(section.get("adult_content_detected", False)),
    }


def _nested_total(payload: dict[str, Any], key: str, field: str) -> float | None:
    value = payload.get(key)
    if not isinstance(value, dict):
        return None
    return _safe_float(value.get(field))


def _coalesce(preferred: float | None, fallback: float | None) -> float | None:
    return fallback if preferred is None else preferred


def _audience_fit_total(post: SinglePostInsights, ai_analysis: dict[str, Any]) -> float | None:
    raw_ai_score = ai_analysis.get("audience_relevance_score")
    if isinstance(raw_ai_score, dict):
        if raw_ai_score.get("status") == "unavailable":
            return None
        if raw_ai_score.get("status") == "available":
            return _safe_float(raw_ai_score.get("total_0_50"))
    if post.audience_relevance_score.status != "available":
        return None
    return _safe_float(post.audience_relevance_score.total_0_50)


def _scores_payload(post: SinglePostInsights, ai_analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "S1": _coalesce(
            _nested_total(ai_analysis, "visual_quality_score", "total"),
            _safe_float(post.visual_quality_score.total),
        ),
        "S2": _coalesce(
            _nested_total(ai_analysis, "caption_effectiveness_score", "total_0_50"),
            _safe_float(post.caption_effectiveness_score.total_0_50),
        ),
        "S3": _coalesce(
            _nested_total(ai_analysis, "content_clarity_score", "total"),
            _safe_float(post.content_clarity_score.total),
        ),
        "S4": _audience_fit_total(post, ai_analysis),
        "S5": _coalesce(
            _nested_total(ai_analysis, "engagement_potential_score", "total"),
            _safe_float(post.engagement_potential_score.total),
        ),
        "S6": _coalesce(
            _nested_total(ai_analysis, "brand_safety_score", "total_0_50"),
            _safe_float(post.brand_safety_score.total_0_50),
        ),
        "P": _coalesce(
            _nested_total(ai_analysis, "weighted_post_score", "score"),
            _safe_float(post.weighted_post_score.score),
        ),
        # Compatibility keys remain present, but performance prediction is not
        # part of the AI-only creative report.
        "predicted_engagement_rate": None,
        "predicted_engagement_rate_notes": ["Not part of the AI-only creative analysis contract."],
        "predicted_er_confidence": "unavailable",
    }


def _score_components_payload(scores: dict[str, Any], *, confidence: str) -> list[dict[str, Any]]:
    """Expose presentation-ready component scores without changing raw scoring units."""
    labels = {
        "S1": "Visual quality",
        "S2": "Caption strength",
        "S3": "Content clarity",
        "S4": "Audience fit",
        "S5": "Engagement pull",
        "S6": "Brand safety",
    }
    components: list[dict[str, Any]] = []
    for component_id, label in labels.items():
        raw_value = _safe_float(scores.get(component_id))
        components.append(
            {
                "id": component_id,
                "label": label,
                "raw_value": raw_value,
                "raw_max": 50,
                "normalized_value": round(raw_value * 2, 2) if raw_value is not None else None,
                "normalized_max": 100,
                "confidence": confidence if raw_value is not None else ("unavailable" if component_id == "S4" else "limited"),
                "status": "available" if raw_value is not None else "unavailable",
                "reason": (
                    None
                    if raw_value is not None
                    else (
                        "Creator niche context is required to score audience fit."
                        if component_id == "S4"
                        else "This component did not have enough input evidence to score."
                    )
                ),
            }
        )
    return components


def _unavailable_features_payload() -> dict[str, dict[str, str]]:
    """Make deliberately unsupported product surfaces explicit to API consumers."""
    return {
        "retention_curve": {
            "status": "not_supported",
            "reason": "Second-by-second audience-retention data is not part of the single-post analysis contract.",
        },
        "post_attributed_follows": {
            "status": "not_supported",
            "reason": "Instagram does not provide reliable post-attributed follower counts for this report.",
        },
        "post_demographics": {
            "status": "not_supported",
            "reason": "Demographics are account-level signals and belong in Account Analysis, not this post report.",
        },
    }


def _confidence_payload(*, vision: dict[str, Any], fallback_used: bool, warnings: list[Any]) -> dict[str, str]:
    if fallback_used:
        return {"level": "estimated", "reason": "A fallback analysis path was used; treat this as a preliminary score."}
    if vision.get("status") != "ok":
        return {"level": "limited", "reason": "Visual analysis was unavailable or incomplete, so some score inputs are limited."}
    coverage = vision.get("slide_coverage")
    if isinstance(coverage, dict):
        analyzed, submitted = coverage.get("analyzed"), coverage.get("submitted")
        if isinstance(analyzed, int) and isinstance(submitted, int) and submitted > 0 and analyzed < submitted:
            return {
                "level": "standard",
                "reason": (
                    f"Only {analyzed} of {submitted} carousel slides were analyzed; "
                    "treat visual scores as a partial sample."
                ),
            }
    if warnings:
        return {"level": "standard", "reason": "Primary analysis completed with non-blocking warnings."}
    return {"level": "high", "reason": "Primary visual and scoring inputs completed successfully."}


def _er_payload(scores: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "not_supported",
        "reason": "Predicted engagement is not part of the AI-only creative analysis contract.",
        "value": None,
        "confidence": "unavailable",
    }


def _score_evidence_payload(scores: dict[str, Any], vision: dict[str, Any], caption_text: str) -> list[dict[str, str]]:
    labels = {"S1": "Visual quality", "S2": "Caption strength", "S3": "Content clarity", "S4": "Audience fit", "S5": "Engagement pull", "S6": "Brand safety"}
    available = [(key, value) for key, value in ((key, _safe_float(scores.get(key))) for key in labels) if value is not None]
    if not available:
        return []
    weakest_key, weakest_value = min(available, key=lambda item: item[1])
    signal_list = vision.get("signals")
    first_signal = signal_list[0] if isinstance(signal_list, list) and signal_list and isinstance(signal_list[0], dict) else {}
    if weakest_key == "S2" and not caption_text.strip():
        detail = "No caption was supplied, so caption strength cannot be meaningfully evaluated."
    elif weakest_key == "S1" and not first_signal.get("scene_description"):
        detail = "The vision result did not provide enough scene detail to support a stronger visual assessment."
    else:
        detail = f"{labels[weakest_key]} is the lowest available component at {weakest_value:.1f}/50."
    signal_type = "caption_missing" if weakest_key == "S2" and not caption_text.strip() else "vision_context"
    evidence = [{
        "component_id": weakest_key,
        "signal_type": signal_type,
        "label": f"Main score constraint: {labels[weakest_key]}",
        "detail": detail,
    }]
    # Below-threshold components are legitimate deterministic constraints even
    # when the analysis did not return a richer causal signal. They are kept
    # distinct from vision/caption evidence so clients never mistake them for
    # model-observed explanations.
    for component_id, value in available:
        if component_id == weakest_key or value >= 30:
            continue
        evidence.append({
            "component_id": component_id,
            "signal_type": "score_threshold",
            "label": f"Below target: {labels[component_id]}",
            "detail": f"{labels[component_id]} is {value:.1f}/50, below the 30/50 review threshold.",
        })
    return evidence


def _data_sources_payload(request: PostAnalysisRequest) -> dict[str, Any]:
    """State provenance rather than implying that URL-test inputs are OAuth insights."""
    supplied = request.model_fields_set
    engagement_fields = {"likes", "comments", "views"}
    return {
        "media": "request_supplied",
        "engagement_metrics": "request_supplied_not_used_for_ai_score" if supplied & engagement_fields else "not_provided",
        "score": "ai_creative_weighted_score",
        "account_baseline": "durable_post_analysis_history",
    }


def _ai_payload(ai_analysis: dict[str, Any]) -> dict[str, Any]:
    summary = ai_analysis.get("summary")
    drivers = ai_analysis.get("drivers")
    recommendations = ai_analysis.get("recommendations")
    caption_improvement = ai_analysis.get("caption_improvement")
    posting_intelligence = ai_analysis.get("posting_intelligence")
    hashtag_quality_note = ai_analysis.get("hashtag_quality_note")
    return {
        "summary": summary if isinstance(summary, str) else "",
        "drivers": drivers if isinstance(drivers, list) else [],
        "recommendations": recommendations if isinstance(recommendations, list) else [],
        "vision_status": ai_analysis.get("vision_status"),
        "fallback_used": bool(ai_analysis.get("fallback_used", False)),
        "caption_improvement": caption_improvement if isinstance(caption_improvement, dict) else None,
        "posting_intelligence": posting_intelligence if isinstance(posting_intelligence, str) else None,
        "hashtag_quality_note": hashtag_quality_note if isinstance(hashtag_quality_note, str) else None,
        "creative_score": _safe_float(ai_analysis.get("creative_score")),
        "creative_band": str(ai_analysis.get("creative_band") or "UNAVAILABLE"),
        "score_source": "ai_creative_weighted_score",
    }


async def _analyze_single_post_inline(request: PostAnalysisRequest) -> dict[str, Any]:
    post_type = _resolve_post_type(request)
    media_urls = request.media_urls or [request.media_url]
    post_id = request.post_id or _stable_post_id(
        media_url=request.media_url,
        post_type=post_type,
        caption_text=request.caption_text,
    )
    creator_id = request.account_id or request.creator_id or ""

    creator_post = CreatorPostAIInput(
        post_id=post_id,
        creator_id=creator_id,
        platform=request.platform,
        post_type=post_type,
        media_url=request.media_url,
        media_urls=media_urls,
        thumbnail_url=request.thumbnail_url,
        caption_text=request.caption_text,
        hashtags=request.hashtags,
        likes=request.likes,
        comments=request.comments,
        views=request.views,
        audio_name=request.audio_name,
        posted_at=request.posted_at,
    )

    try:
        pipeline_result = await build_single_post_insights(
            target_post=creator_post,
            historical_posts=[],
            run_ai=True,
        )
    except Exception as exc:
        logger.exception("Failed to analyze post: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to analyze post. Please try again later.")

    raw_post = pipeline_result.get("post")
    if raw_post is None:
        raise HTTPException(status_code=500, detail="Analysis pipeline returned no post data.")
    post = raw_post if isinstance(raw_post, SinglePostInsights) else SinglePostInsights.model_validate(raw_post)
    ai_analysis_raw = pipeline_result.get("ai_analysis")
    ai_analysis = ai_analysis_raw if isinstance(ai_analysis_raw, dict) else {}

    warnings = ai_analysis.get("warnings")
    warnings_list = warnings if isinstance(warnings, list) else []
    vision_enabled = bool((os.getenv("GEMINI_API_KEY") or "").strip())
    fallback_used = bool(ai_analysis.get("fallback_used", False))

    post_payload = _post_payload(post, fallback_post_id=post_id, fallback_media_url=request.media_url)
    vision_payload = _vision_payload(post, ai_analysis)
    cringe_summary = _cringe_summary_from_vision(vision_payload)
    cringe_summary["vision_status"] = vision_payload.get("status", "error")
    _write_cringe_summary(request.account_id or request.creator_id or "", str(post_payload["post_id"]), cringe_summary)

    score_analysis = ai_analysis.get("score_analysis")
    scores = _scores_payload(post, ai_analysis)
    confidence = _confidence_payload(vision=vision_payload, fallback_used=fallback_used, warnings=warnings_list)
    score_components = _score_components_payload(scores, confidence=confidence["level"])
    canonical_score = _safe_float(scores.get("P"))
    account_id = request.account_id or request.creator_id or ""
    try:
        record_post_score_snapshot(
            account_id=account_id,
            post_id=str(post_payload["post_id"]),
            contract_version=POST_ANALYSIS_CONTRACT_VERSION,
            score=canonical_score,
            score_components=score_components,
            confidence_level=confidence["level"],
            source_posted_at=request.posted_at,
        )
    except Exception as exc:
        # The analysis itself stays available while an additive historical
        # comparison is temporarily unavailable (for example before migration).
        logger.warning("[PostAnalysis] Failed to persist score history post_id=%s: %s", post_payload["post_id"], exc)
    baseline = get_account_score_baseline(
        account_id=account_id,
        current_score=canonical_score,
        exclude_post_id=str(post_payload["post_id"]),
    )

    return {
        "contract_version": POST_ANALYSIS_CONTRACT_VERSION,
        "status": "succeeded",
        "post": post_payload,
        "data_sources": _data_sources_payload(request),
        "vision": vision_payload,
        "reel_analysis": post.reel_analysis.model_dump() if post.reel_analysis is not None else None,
        "scores": scores,
        "score": {
            "value": canonical_score,
            "max": 100,
            "band": str(ai_analysis.get("creative_band") or "UNAVAILABLE"),
            "source": "ai_creative_weighted_score",
        },
        "confidence": confidence,
        "score_components": score_components,
        "account_score_baseline": baseline,
        "predicted_er": _er_payload(scores),
        "score_evidence": _score_evidence_payload(scores, vision_payload, request.caption_text),
        "unavailable_features": _unavailable_features_payload(),
        "ai": _ai_payload(ai_analysis),
        "cringe": cringe_summary,
        "score_analysis": score_analysis if isinstance(score_analysis, dict) else None,
        "warnings": warnings_list,
        "quality": {
            "vision_enabled": vision_enabled,
            "ai_fallback_used": fallback_used,
            "ai_fallback_reason": ai_analysis.get("fallback_reason"),
        },
    }


@v1_router.post("/post-analysis", dependencies=[Depends(_require_post_analysis_api_key_if_configured)])
@legacy_router.post("/post-analysis", include_in_schema=False, dependencies=[Depends(_require_post_analysis_api_key_if_configured)])
async def post_analysis(
    request: PostAnalysisRequest,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> dict[str, Any]:
    """Run single-post analysis and return deterministic normalized API payload."""
    return await _analyze_single_post_inline(_request_for_current_user(request, current_user))


@v1_router.get("/posts/{post_id}/cringe-summary", dependencies=[Depends(_require_post_analysis_api_key_if_configured)])
def post_cringe_summary(post_id: str, current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user)) -> dict[str, Any]:
    """Return concise cringe summary for a previously analyzed post."""
    normalized_post_id = post_id.strip()
    if not normalized_post_id:
        raise HTTPException(status_code=400, detail="post_id must be non-empty.")

    payload = _read_cringe_summary(current_user.id, normalized_post_id)

    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="Cringe summary not found for post_id. Run /api/v1/post-analysis for this post first.",
        )
    return payload


@v1_router.get("/posts/{post_id}/insights", dependencies=[Depends(_require_post_analysis_api_key_if_configured)])
def get_post_insights(post_id: str, current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user)) -> dict[str, Any]:
    """Return cached SinglePostInsights + ai_analysis payload for a previously analyzed post."""
    normalized_post_id = post_id.strip()
    if not normalized_post_id:
        raise HTTPException(status_code=400, detail="post_id must be non-empty.")

    payload = read_post_insights_snapshot(current_user.id, normalized_post_id)
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=404,
            detail="Post insights not found for post_id. Run /api/v1/post-analysis for this post first.",
        )

    raw_post = payload.get("post")
    if not isinstance(raw_post, dict):
        raise HTTPException(status_code=500, detail="Cached post insights payload is invalid.")
    return {
        "status": "succeeded",
        "post": raw_post,
        "ai_analysis": payload.get("ai_analysis") if isinstance(payload.get("ai_analysis"), dict) else None,
    }


@v1_router.post("/single-post-analysis", dependencies=[Depends(_require_post_analysis_api_key_if_configured)])
@legacy_router.post("/single-post-analysis", include_in_schema=False, dependencies=[Depends(_require_post_analysis_api_key_if_configured)])
async def enqueue_single_post_analysis(
    request: PostAnalysisRequest,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> dict[str, Any]:
    """Enqueue single-post analysis as a background job."""
    payload = _request_for_current_user(request, current_user).model_dump(mode="python")
    try:
        return await enqueue_single_post_analysis_job_async(payload)
    except Exception as exc:
        logger.exception("[SinglePostJob] Failed to enqueue single-post analysis job: %s", exc)
        raise HTTPException(status_code=503, detail="Analysis queue is temporarily unavailable. Please try again shortly.") from exc


@v1_router.get("/single-post-analysis/{job_id}", dependencies=[Depends(_require_post_analysis_api_key_if_configured)])
@legacy_router.get("/single-post-analysis/{job_id}", include_in_schema=False, dependencies=[Depends(_require_post_analysis_api_key_if_configured)])
def get_single_post_analysis_status(job_id: str, current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user)) -> dict[str, Any]:
    """Poll single-post analysis background job status."""
    status = get_single_post_analysis_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    if status.get("account_id") != current_user.id:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    return status


router.include_router(v1_router)
router.include_router(legacy_router)
