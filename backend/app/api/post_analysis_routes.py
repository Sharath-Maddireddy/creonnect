"""API routes for single-post analysis."""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.ai.cringe_analysis import build_cringe_section_for_brand_safety
from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.domain.post_models import SinglePostInsights, VisionAnalysis
from backend.app.services.post_insights_service import build_single_post_insights


router = APIRouter(prefix="/api", tags=["Post Analysis"])
_CRINGE_SUMMARY_CACHE: dict[str, dict[str, Any]] = {}
_CRINGE_SUMMARY_CACHE_LOCK = threading.Lock()


class PostAnalysisRequest(BaseModel):
    """Request payload for single-post analysis endpoint."""

    model_config = ConfigDict(extra="forbid")

    post_id: str | None = None
    account_id: str | None = None
    creator_id: str | None = None
    platform: str = "instagram"
    post_type: Literal["IMAGE", "REEL"] = "IMAGE"
    media_url: str
    thumbnail_url: str = ""
    caption_text: str = ""
    hashtags: list[str] = Field(default_factory=list)
    likes: int = 0
    comments: int = 0
    views: int | None = None
    audio_name: str | None = None
    posted_at: datetime | None = None

    @field_validator("media_url", mode="before")
    @classmethod
    def _validate_media_url(cls, value: Any) -> str:
        text = value.strip() if isinstance(value, str) else ""
        if not text:
            raise ValueError("media_url must be non-empty.")
        return text

    @field_validator("post_type", mode="before")
    @classmethod
    def _normalize_post_type(cls, value: Any) -> Literal["IMAGE", "REEL"]:
        text = value.strip().upper() if isinstance(value, str) else ""
        if text in {"REEL", "VIDEO", "REELS", "CLIPS"}:
            return "REEL"
        return "IMAGE"

    @field_validator("post_id", "account_id", "creator_id", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text if text else None


def _stable_post_id(*, media_url: str, post_type: str, caption_text: str) -> str:
    payload = f"{media_url}|{post_type}|{caption_text}".encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()[:16]
    return f"auto_{digest}"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _post_payload(post: SinglePostInsights, fallback_post_id: str, fallback_media_url: str) -> dict[str, Any]:
    return {
        "post_id": post.media_id or fallback_post_id,
        "post_type": post.media_type or "IMAGE",
        "media_url": post.media_url or fallback_media_url,
        "caption_text": post.caption_text or "",
    }


def _vision_payload(post: SinglePostInsights, ai_analysis: dict[str, Any]) -> dict[str, Any]:
    vision_status = None
    if post.vision_analysis is not None and isinstance(post.vision_analysis.status, str):
        vision_status = post.vision_analysis.status
    if vision_status is None:
        vision_status = ai_analysis.get("vision_status")
    if vision_status not in {"ok", "error", "disabled", "no_media"}:
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
            pass
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


def _scores_payload(post: SinglePostInsights, ai_analysis: dict[str, Any]) -> dict[str, Any]:
    predicted_notes = post.predicted_engagement_rate_notes
    if not isinstance(predicted_notes, list):
        predicted_notes = []
    if not predicted_notes:
        raw_notes = ai_analysis.get("predicted_engagement_rate_notes")
        if isinstance(raw_notes, list):
            predicted_notes = [str(item) for item in raw_notes if isinstance(item, str)]

    predicted_er = _safe_float(ai_analysis.get("predicted_engagement_rate"))
    if predicted_er is None:
        predicted_er = post.predicted_engagement_rate

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
        "S4": _coalesce(
            _nested_total(ai_analysis, "audience_relevance_score", "total_0_50"),
            _safe_float(post.audience_relevance_score.total_0_50),
        ),
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
        "predicted_engagement_rate": _safe_float(predicted_er),
        "predicted_engagement_rate_notes": predicted_notes,
    }


def _ai_payload(ai_analysis: dict[str, Any]) -> dict[str, Any]:
    summary = ai_analysis.get("summary")
    drivers = ai_analysis.get("drivers")
    recommendations = ai_analysis.get("recommendations")
    return {
        "summary": summary if isinstance(summary, str) else "",
        "drivers": drivers if isinstance(drivers, list) else [],
        "recommendations": recommendations if isinstance(recommendations, list) else [],
        "vision_status": ai_analysis.get("vision_status"),
        "fallback_used": bool(ai_analysis.get("fallback_used", False)),
    }


@router.post("/post-analysis")
async def post_analysis(request: PostAnalysisRequest) -> dict[str, Any]:
    """Run single-post analysis and return deterministic normalized API payload."""
    post_id = request.post_id or _stable_post_id(
        media_url=request.media_url,
        post_type=request.post_type,
        caption_text=request.caption_text,
    )
    creator_id = request.account_id or request.creator_id or ""

    creator_post = CreatorPostAIInput(
        post_id=post_id,
        creator_id=creator_id,
        platform=request.platform,
        post_type=request.post_type,
        media_url=request.media_url,
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
        raise HTTPException(status_code=500, detail=f"Failed to analyze post: {exc}")

    raw_post = pipeline_result.get("post")
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

    with _CRINGE_SUMMARY_CACHE_LOCK:
        _CRINGE_SUMMARY_CACHE[str(post_payload["post_id"])] = cringe_summary

    return {
        "status": "succeeded",
        "post": post_payload,
        "vision": vision_payload,
        "scores": _scores_payload(post, ai_analysis),
        "ai": _ai_payload(ai_analysis),
        "warnings": warnings_list,
        "quality": {
            "vision_enabled": vision_enabled,
            "ai_fallback_used": fallback_used,
        },
    }


@router.get("/v1/posts/{post_id}/cringe-summary")
def post_cringe_summary(post_id: str) -> dict[str, Any]:
    """Return concise cringe summary for a previously analyzed post."""
    normalized_post_id = post_id.strip()
    if not normalized_post_id:
        raise HTTPException(status_code=400, detail="post_id must be non-empty.")

    with _CRINGE_SUMMARY_CACHE_LOCK:
        payload = _CRINGE_SUMMARY_CACHE.get(normalized_post_id)

    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="Cringe summary not found for post_id. Run /api/post-analysis for this post first.",
        )
    return payload
