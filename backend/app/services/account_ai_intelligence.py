"""Account-level creator intelligence generation via a single LLM call."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any

from backend.app.ai.llm_client import LLMClient
from backend.app.domain.account_models import BrandFitSignals, CreatorIntelligence
from backend.app.domain.post_models import SinglePostInsights
from backend.app.utils.logger import logger


LLM_TIMEOUT_SECONDS = 45


def _sanitize_text(value: Any, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    return text[:max_chars] or None


def _sanitize_list(values: Any, max_items: int, max_chars: int | None = None) -> list[str]:
    if values is None:
        return []
    items = values if isinstance(values, list) else [values]
    sanitized: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        text = " ".join(item.strip().split())
        if not text:
            continue
        sanitized.append(text[:max_chars] if max_chars is not None else text)
        if len(sanitized) >= max_items:
            break
    return sanitized


def _safe_average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _extract_first_vision_signal(post: SinglePostInsights) -> Any | None:
    signals = post.vision_analysis.signals if post.vision_analysis else []
    return signals[0] if signals else None


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in LLM response")

    payload = json.loads(candidate[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON root must be an object")
    return payload


def _build_account_context(
    posts: list[SinglePostInsights],
    account_id: str,
    username: str | None,
    bio: str | None,
    niche_tags: list[str] | None,
    creator_dominant_category: str | None,
    follower_count: int | None,
) -> dict[str, Any]:
    sorted_posts = sorted(
        posts,
        key=lambda post: post.weighted_post_score.score,
        reverse=True,
    )

    top_posts: list[dict[str, Any]] = []
    production_levels: list[str] = []
    weighted_scores: list[float] = []
    s6_scores: list[float] = []

    for post in posts:
        weighted_scores.append(float(post.weighted_post_score.score))
        s6_scores.append(float(post.brand_safety_score.s6_raw_0_100))
        signal = _extract_first_vision_signal(post)
        production_level = signal.production_level if signal else None
        if isinstance(production_level, str) and production_level:
            production_levels.append(production_level)

    for post in sorted_posts[:5]:
        signal = _extract_first_vision_signal(post)
        top_posts.append(
            {
                "post_type": post.weighted_post_score.post_type or post.media_type or "UNKNOWN",
                "caption_text": (post.caption_text or "")[:200],
                "visual_style": signal.visual_style if signal else None,
                "production_level": signal.production_level if signal else None,
                "post_category": post.audience_relevance_score.post_category,
                "brand_safety_score": post.brand_safety_score.s6_raw_0_100,
            }
        )

    most_common_production_level = None
    if production_levels:
        most_common_production_level = Counter(production_levels).most_common(1)[0][0]

    return {
        "account_id": account_id,
        "username": _sanitize_text(username, 120),
        "post_count": len(posts),
        "top_posts": top_posts,
        "account_aggregates": {
            "avg_weighted_post_score": _safe_average(weighted_scores),
            "avg_brand_safety_score": _safe_average(s6_scores),
            "most_common_production_level": most_common_production_level,
            "niche_tags": _sanitize_list(niche_tags, max_items=20, max_chars=80),
            "bio": _sanitize_text(bio, 300),
            "creator_dominant_category": _sanitize_text(creator_dominant_category, 120),
            "follower_count": follower_count if isinstance(follower_count, int) and follower_count >= 0 else None,
        },
    }


def _build_prompt(context: dict[str, Any]) -> dict[str, str]:
    system_prompt = (
        "You are a creator strategist. Analyze the account context and return ONLY valid JSON. "
        "Do not wrap the response in markdown or code fences. "
        "Use concise, evidence-based summaries grounded only in the provided data. "
        "Return EXACTLY this JSON structure and no extra keys: "
        "{"
        '"creator_persona":"2-3 sentence natural language description of what this creator does and who their audience is",'
        '"content_style_summary":"1-2 sentence description of their visual/content style",'
        '"top_performing_themes":["theme1","theme2","theme3"],'
        '"brand_fit":{"fit_categories":["category1","category2"],"red_flags":[]}'
        "}"
    )
    user_prompt = (
        "Create creator-level intelligence for this account.\n"
        "Rules:\n"
        "- Infer themes from the highest-performing posts and account aggregates.\n"
        "- Keep creator_persona to 2-3 sentences.\n"
        "- Keep content_style_summary to 1-2 sentences.\n"
        "- top_performing_themes should be short phrases.\n"
        "- fit_categories should be practical brand verticals or campaign categories.\n"
        "- red_flags should be empty unless the context clearly suggests a concern.\n\n"
        f"Account context:\n{json.dumps(context, ensure_ascii=True, indent=2)}"
    )
    return {"system": system_prompt, "user": user_prompt}


def _build_creator_intelligence(payload: dict[str, Any]) -> CreatorIntelligence:
    brand_fit_payload = payload.get("brand_fit")
    brand_fit_dict = brand_fit_payload if isinstance(brand_fit_payload, dict) else {}

    return CreatorIntelligence(
        creator_persona=_sanitize_text(payload.get("creator_persona"), 500),
        content_style_summary=_sanitize_text(payload.get("content_style_summary"), 400),
        top_performing_themes=_sanitize_list(
            payload.get("top_performing_themes"),
            max_items=5,
            max_chars=80,
        ),
        brand_fit=BrandFitSignals(
            fit_categories=_sanitize_list(
                brand_fit_dict.get("fit_categories"),
                max_items=8,
            ),
            red_flags=_sanitize_list(
                brand_fit_dict.get("red_flags"),
                max_items=5,
            ),
        ),
    )


async def generate_creator_intelligence(
    posts: list[SinglePostInsights],
    account_id: str,
    username: str | None = None,
    bio: str | None = None,
    niche_tags: list[str] | None = None,
    creator_dominant_category: str | None = None,
    follower_count: int | None = None,
) -> CreatorIntelligence:
    """Generate creator-level AI intelligence from processed posts and account context."""
    if not posts:
        return CreatorIntelligence()

    context = _build_account_context(
        posts=posts,
        account_id=account_id,
        username=username,
        bio=bio,
        niche_tags=niche_tags,
        creator_dominant_category=creator_dominant_category,
        follower_count=follower_count,
    )
    prompt = _build_prompt(context)
    llm_client = LLMClient()

    try:
        raw_response = await asyncio.wait_for(
            asyncio.to_thread(llm_client.generate, prompt),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        if not isinstance(raw_response, str) or not raw_response.strip():
            logger.warning(
                "[AccountAIIntelligence] Empty LLM response for account_id=%s",
                account_id,
            )
            return CreatorIntelligence()

        payload = _extract_json_payload(raw_response)
        return _build_creator_intelligence(payload)
    except asyncio.TimeoutError:
        logger.warning(
            "[AccountAIIntelligence] LLM call timed out for account_id=%s",
            account_id,
        )
        return CreatorIntelligence()
    except Exception as exc:
        logger.warning(
            "[AccountAIIntelligence] Failed to generate creator intelligence for account_id=%s: %s",
            account_id,
            exc,
        )
        return CreatorIntelligence()
