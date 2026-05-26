"""Lightweight creator-intelligence rollup used by dashboard and account analysis."""

from __future__ import annotations

import asyncio
from collections import Counter
import json
import os

from backend.app.ai import toon
from backend.app.ai.llm_client import LLMClient
from backend.app.domain.account_models import BrandFitSignals, CreatorIntelligence
from backend.app.domain.post_models import SinglePostInsights
from backend.app.utils.logger import logger

_DEFAULT_CREATOR_TUNING_MODEL = LLMClient.DEFAULT_MODEL
_CREATOR_INTELLIGENCE_SYSTEM_PROMPT = """
You are a senior creator-strategy analyst producing labeled training data for a fine-tuned creator intelligence model.
Return ONLY valid TOON (Token-Oriented Object Notation).

Formatting rules:
- Use plain keys and values only. Do not use JSON, braces, brackets, or quotes.
- Use 2-space indentation for nested fields.
- For list items, put "-" on its own line item line.
- Omit fields only when truly unknown, but prefer best-effort inference from the creator data.
- Keep every value concise, specific, and evidence-based from the supplied posts.

Schema mapped exactly to CreatorIntelligence:
creator_persona value_or_null
content_style_summary value_or_null
audience_hypothesis value_or_null
creator_strengths
  - value
improvement_areas
  - value
sponsorship_potential HIGH|MEDIUM|LOW
notable_formats
  - value
top_performing_themes
  - value
brand_fit
  fit_categories
    - value
  red_flags
    - value

Field guidance:
- creator_persona: one-sentence summary of who this creator is and what niche they occupy.
- content_style_summary: one-sentence summary of tone, structure, and production style.
- audience_hypothesis: who likely watches or follows this creator.
- creator_strengths: 2 to 5 concise strengths.
- improvement_areas: 1 to 5 concise opportunities to improve.
- sponsorship_potential: choose HIGH, MEDIUM, or LOW based on consistency, safety, clarity, and commercial fit.
- notable_formats: recurring content formats that stand out.
- top_performing_themes: themes that appear to drive traction or define the account.
- brand_fit.fit_categories: categories of sponsors that fit naturally.
- brand_fit.red_flags: brand-safety or partnership concerns only when supported by the data.
""".strip()


def _clean_text(value: object, *, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    return text[:limit] if text else None


def _collect_top_words(posts: list[SinglePostInsights]) -> list[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "your",
        "have",
        "about",
        "into",
        "just",
        "they",
        "them",
        "their",
        "been",
        "were",
        "what",
        "when",
        "where",
        "will",
        "would",
        "there",
        "here",
        "more",
        "than",
        "then",
        "also",
        "https",
        "reel",
        "video",
        "post",
    }
    counts: Counter[str] = Counter()
    for post in posts:
        caption = _clean_text(post.caption_text, limit=400) or ""
        for token in caption.lower().replace("#", " ").split():
            word = "".join(ch for ch in token if ch.isalnum())
            if len(word) < 4 or word in stop_words:
                continue
            counts[word] += 1
    return [word for word, _ in counts.most_common(5)]


def _infer_persona(
    username: str | None,
    creator_dominant_category: str | None,
    niche_tags: list[str] | None,
    follower_count: int | None,
) -> str | None:
    category = _clean_text(creator_dominant_category, limit=80)
    tags = [_clean_text(tag, limit=40) for tag in (niche_tags or [])]
    tags = [tag for tag in tags if tag]
    if category and tags:
        return f"{category} creator focused on {', '.join(tags[:2])}."
    if category:
        return f"{category} creator with a consistent niche-led presence."
    if tags:
        return f"Creator focused on {', '.join(tags[:2])}."
    if username and follower_count:
        scale = "emerging" if follower_count < 100_000 else "established"
        return f"{scale.title()} creator profile for @{username}."
    return None


def _infer_content_style(posts: list[SinglePostInsights]) -> str | None:
    media_types = Counter(
        (post.media_type or "").upper()
        for post in posts
        if isinstance(post.media_type, str) and post.media_type.strip()
    )
    top_words = _collect_top_words(posts)
    leading_media_type = media_types.most_common(1)[0][0] if media_types else None

    parts: list[str] = []
    if leading_media_type:
        parts.append(f"Leans heavily on {leading_media_type.lower()} content.")
    if top_words:
        parts.append(f"Recurring themes include {', '.join(top_words[:3])}.")
    return " ".join(parts)[:240] if parts else None


def _infer_fit_categories(
    creator_dominant_category: str | None,
    niche_tags: list[str] | None,
    top_words: list[str],
) -> list[str]:
    candidates: list[str] = []
    if creator_dominant_category:
        candidates.append(creator_dominant_category)
    candidates.extend(niche_tags or [])
    candidates.extend(top_words[:2])

    seen: set[str] = set()
    normalized: list[str] = []
    for item in candidates:
        text = _clean_text(item, limit=60)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(text)
    return normalized[:5]


def _infer_red_flags(posts: list[SinglePostInsights]) -> list[str]:
    red_flags: list[str] = []
    flagged_posts = 0
    low_brand_safety_posts = 0

    for post in posts:
        first_signal = None
        if post.vision_analysis and post.vision_analysis.signals:
            first_signal = post.vision_analysis.signals[0]
        if first_signal and (
            getattr(first_signal, "adult_content_detected", None) is True
            or getattr(first_signal, "is_cringe", None) is True
        ):
            flagged_posts += 1
        if (post.brand_safety_score.total_0_50 or 0) < 25:
            low_brand_safety_posts += 1

    if flagged_posts:
        red_flags.append(f"{flagged_posts} post(s) flagged by vision safety signals.")
    if low_brand_safety_posts:
        red_flags.append(f"{low_brand_safety_posts} post(s) have weak brand-safety scores.")
    return red_flags[:5]


def _build_creator_prompt_payload(
    posts: list[SinglePostInsights],
    *,
    account_id: str | None,
    username: str | None,
    bio: str | None,
    niche_tags: list[str] | None,
    creator_dominant_category: str | None,
    follower_count: int | None,
) -> dict[str, object]:
    compact_posts: list[dict[str, object]] = []
    for post in posts:
        first_signal = post.vision_analysis.signals[0] if post.vision_analysis and post.vision_analysis.signals else None
        compact_posts.append(
            {
                "media_type": post.media_type,
                "likes": getattr(post.core_metrics, "likes", None),
                "comments": getattr(post.core_metrics, "comments", None),
                "caption_text": _clean_text(post.caption_text, limit=400),
                "cringe_score": getattr(first_signal, "cringe_score", None) if first_signal else None,
                "scene_description": _clean_text(getattr(first_signal, "scene_description", None), limit=180) if first_signal else None,
                "adult_content": getattr(first_signal, "adult_content_detected", None) if first_signal else None,
            }
        )
    return {
        "creator_data": {
            "account_id": account_id,
            "username": username,
            "bio": _clean_text(bio, limit=400),
            "niche_tags": niche_tags or [],
            "creator_dominant_category": creator_dominant_category,
            "follower_count": follower_count,
            "post_count": len(compact_posts),
            "posts": compact_posts,
        }
    }


def _resolve_creator_intelligence_model_name() -> str:
    configured = os.getenv("CREATOR_TUNING_MODEL")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    fallback = os.getenv("LLM_MODEL_NAME")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return _DEFAULT_CREATOR_TUNING_MODEL


async def generate_creator_intelligence(
    posts: list[SinglePostInsights],
    account_id: str | None = None,
    username: str | None = None,
    bio: str | None = None,
    niche_tags: list[str] | None = None,
    creator_dominant_category: str | None = None,
    follower_count: int | None = None,
) -> CreatorIntelligence:
    """Build creator intelligence with an LLM-first path and resilient heuristic fallback."""

    logger.info(
        "[CreatorIntelligence] Start username=%s post_count=%d category=%s niche_tag_count=%d",
        username,
        len(posts),
        creator_dominant_category,
        len(niche_tags or []),
    )
    top_words = _collect_top_words(posts)
    fit_categories = _infer_fit_categories(creator_dominant_category, niche_tags, top_words)
    red_flags = _infer_red_flags(posts)
    logger.debug(
        "[CreatorIntelligence] Derived themes=%s fit_categories=%s red_flags=%s",
        top_words[:5],
        fit_categories,
        red_flags,
    )
    fallback_result = CreatorIntelligence(
        creator_persona=_infer_persona(username, creator_dominant_category, niche_tags, follower_count),
        content_style_summary=_infer_content_style(posts),
        top_performing_themes=top_words[:5],
        brand_fit=BrandFitSignals(
            fit_categories=fit_categories,
            red_flags=red_flags,
        ),
    )

    try:
        prompt = {
            "system": _CREATOR_INTELLIGENCE_SYSTEM_PROMPT,
            "user": json.dumps(
                _build_creator_prompt_payload(
                    posts,
                    account_id=account_id,
                    username=username,
                    bio=bio,
                    niche_tags=niche_tags,
                    creator_dominant_category=creator_dominant_category,
                    follower_count=follower_count,
                ),
                ensure_ascii=False,
            ),
        }
        llm = LLMClient(model_name=_resolve_creator_intelligence_model_name(), temperature=0.2, max_tokens=700)
        raw_response = await asyncio.to_thread(llm.generate, prompt)
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise ValueError("LLM returned empty creator intelligence response.")
        parsed = toon.loads(raw_response)
        if not isinstance(parsed, dict) or not parsed.get("creator_persona"):
            raise ValueError("LLM creator intelligence response missing creator_persona.")

        brand_fit = parsed.get("brand_fit")
        brand_fit_dict = brand_fit if isinstance(brand_fit, dict) else {}
        result = CreatorIntelligence(
            creator_persona=parsed.get("creator_persona"),
            content_style_summary=parsed.get("content_style_summary"),
            audience_hypothesis=parsed.get("audience_hypothesis"),
            creator_strengths=parsed.get("creator_strengths") or [],
            improvement_areas=parsed.get("improvement_areas") or [],
            sponsorship_potential=parsed.get("sponsorship_potential"),
            notable_formats=parsed.get("notable_formats") or [],
            top_performing_themes=parsed.get("top_performing_themes") or [],
            brand_fit=BrandFitSignals(
                fit_categories=brand_fit_dict.get("fit_categories") or [],
                red_flags=brand_fit_dict.get("red_flags") or [],
            ),
        )
        logger.info(
            "[CreatorIntelligence] Completed via LLM username=%s theme_count=%d red_flag_count=%d",
            username,
            len(result.top_performing_themes or []),
            len(result.brand_fit.red_flags or []),
        )
        return result
    except Exception as exc:
        logger.warning(
            "[CreatorIntelligence] LLM generation failed for username=%s account_id=%s: %s",
            username,
            account_id,
            exc,
        )
        logger.info(
            "[CreatorIntelligence] Falling back to heuristics username=%s theme_count=%d red_flag_count=%d",
            username,
            len(fallback_result.top_performing_themes or []),
            len(fallback_result.brand_fit.red_flags or []),
        )
        return fallback_result
