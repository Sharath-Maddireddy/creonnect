"""Post-pipeline helpers for account analysis jobs."""

from __future__ import annotations

from typing import Any

from backend.app.domain.post_models import SinglePostInsights


def caption_preview(value: str | None, max_len: int = 120) -> str:
    if not isinstance(value, str):
        return ""
    return value[:max_len]


def normalize_summary_post_type(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if normalized in {"IMAGE", "REEL"}:
        return normalized
    return None


def bounded_media_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 2048:
        return None
    return text


def is_reel_post(post: SinglePostInsights) -> bool:
    media_type = post.media_type if isinstance(post.media_type, str) else ""
    return media_type.strip().upper() == "REEL"


def maybe_attach_inline_reel_analysis(
    post: SinglePostInsights,
    *,
    run_reel_gemini_analysis,
    compute_reel_audio_score,
    compute_reel_analysis,
    logger,
) -> SinglePostInsights:
    if not is_reel_post(post):
        return post

    media_url = post.media_url if isinstance(post.media_url, str) else ""
    logger.info(
        "[AccountAnalysisJob] Detected REEL post for inline reel analysis media_id=%s",
        post.media_id,
    )
    if not media_url.strip():
        logger.info(
            "[AccountAnalysisJob] Skipping inline reel analysis for media_id=%s: missing media_url",
            post.media_id,
        )
        return post

    try:
        logger.info(
            "[AccountAnalysisJob] Starting inline reel analysis media_id=%s",
            post.media_id,
        )
        vision_result = run_reel_gemini_analysis(media_url.strip())
        vision_status = str(vision_result.get("status", "error"))
        signals = vision_result.get("signals", {})
        if not isinstance(signals, dict):
            signals = {}
        logger.info(
            "[AccountAnalysisJob] Inline reel vision result media_id=%s status=%s signal_keys=%s",
            post.media_id,
            vision_status,
            sorted(signals.keys()),
        )

        audio_score = compute_reel_audio_score(
            audio_name=None,
            caption_text=post.caption_text,
        )
        reel_model = compute_reel_analysis(
            reel_vision_signals=signals,
            audio_score=audio_score,
            watch_time_pct=None,
            reel_vision_status=vision_status,
        )
        logger.info(
            "[AccountAnalysisJob] Inline reel analysis complete media_id=%s status=%s total=%s",
            post.media_id,
            vision_status,
            reel_model.total,
        )
        logger.info(
            "[AccountAnalysisJob] Attached reel_analysis to post media_id=%s",
            post.media_id,
        )
        return post.model_copy(update={"reel_analysis": reel_model})
    except Exception as exc:
        logger.warning(
            "[AccountAnalysisJob] Non-fatal: inline reel analysis failed for media_id=%s: %s",
            post.media_id,
            exc,
        )
        return post


def build_post_summary(
    post: SinglePostInsights,
    *,
    vision_enabled: bool,
    note_overrides: dict[str, Any] | None,
    safe_float,
    logger,
) -> dict[str, Any]:
    note_overrides = note_overrides or {}
    first_signal = None
    try:
        vision_signals = post.vision_analysis.signals if post.vision_analysis is not None else []
        first_signal = vision_signals[0] if vision_signals else None
    except Exception:
        first_signal = None
    vision_status = note_overrides.get("vision_status")
    if vision_status not in {"ok", "error", "disabled"}:
        vision_analysis = post.vision_analysis
        if vision_analysis is not None and isinstance(vision_analysis.status, str):
            if vision_analysis.status == "ok":
                vision_status = "ok"
            elif vision_analysis.status == "error":
                vision_status = "error"
            else:
                vision_status = "disabled" if not vision_enabled else "ok"
        else:
            vision_status = "disabled" if not vision_enabled else "ok"

    fallback_used = bool(note_overrides.get("fallback_used", False))
    ai_summary = note_overrides.get("ai_summary")
    if not isinstance(ai_summary, str) or not ai_summary.strip():
        ai_summary = getattr(first_signal, "scene_description", None) if first_signal is not None else None
    if isinstance(ai_summary, str):
        ai_summary = ai_summary.strip() or None
    summary = {
        "post_id": post.media_id,
        "shortcode": None,
        "post_type": normalize_summary_post_type(post.media_type),
        "media_url": bounded_media_url(post.media_url),
        "caption_preview": caption_preview(post.caption_text, max_len=120),
        "ai_summary": ai_summary,
        "scores": {
            "S1": safe_float(post.visual_quality_score.total if post.visual_quality_score is not None else None),
            "S2": safe_float(
                post.caption_effectiveness_score.total_0_50 if post.caption_effectiveness_score is not None else None
            ),
            "S3": safe_float(post.content_clarity_score.total if post.content_clarity_score is not None else None),
            "S4": safe_float(
                post.audience_relevance_score.total_0_50 if post.audience_relevance_score is not None else None
            ),
            "S5": safe_float(post.engagement_potential_score.total if post.engagement_potential_score is not None else None),
            "S6": safe_float(post.brand_safety_score.total_0_50 if post.brand_safety_score is not None else None),
            "P": safe_float(post.weighted_post_score.score if post.weighted_post_score is not None else None),
            "engagement_rate": safe_float(
                post.derived_metrics.engagement_rate if post.derived_metrics is not None else None
            ),
            "predicted_er": safe_float(post.predicted_engagement_rate),
        },
        "notes": {
            "vision_status": vision_status,
            "fallback_used": fallback_used,
            "cringe_score": safe_float(getattr(first_signal, "cringe_score", None)) if first_signal is not None else None,
            "cringe_label": getattr(first_signal, "cringe_label", None) if first_signal is not None else None,
            "production_level": getattr(first_signal, "production_level", None) if first_signal is not None else None,
            "hook_strength_score": safe_float(getattr(first_signal, "hook_strength_score", None)) if first_signal is not None else None,
            "technical_flaws": list(getattr(first_signal, "technical_flaws", []) or [])[:],
        },
    }
    if post.reel_analysis is not None:
        logger.info(
            "[AccountAnalysisJob] Including reel_analysis in posts_summary media_id=%s total=%s",
            post.media_id,
            post.reel_analysis.total,
        )
        summary["reel_analysis"] = post.reel_analysis.model_dump(mode="python")
    return summary


def bounded_posts_summary(
    posts: list[SinglePostInsights],
    *,
    include_posts_summary_max: int,
    vision_enabled: bool,
    notes_by_post_id: dict[str, dict[str, Any]],
    safe_float,
    logger,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for post in posts:
        post_id = post.media_id if isinstance(post.media_id, str) else ""
        summaries.append(
            build_post_summary(
                post,
                vision_enabled=vision_enabled,
                note_overrides=notes_by_post_id.get(post_id),
                safe_float=safe_float,
                logger=logger,
            )
        )
    summaries.sort(key=lambda item: (str(item.get("post_id") or ""), str(item.get("media_url") or "")))
    return summaries[:include_posts_summary_max]
