"""Deterministic S4 audience relevance scoring."""

from __future__ import annotations

import asyncio

from backend.app.ai.llm_client import LLMClient, LLMClientError
from backend.app.ai.prompts import S4_AUDIENCE_RELEVANCE_PROMPT
from backend.app.ai.toon import loads as toon_loads
from backend.app.domain.post_models import AudienceRelevanceScore


CATEGORY_GROUPS: dict[str, str] = {
    "fitness": "fitness_sports",
    "sports": "fitness_sports",
    "workout": "fitness_sports",
    "health": "health_wellness",
    "wellness": "health_wellness",
    "nutrition": "food_nutrition",
    "food": "food_nutrition",
    "cooking": "food_nutrition",
    "beauty": "beauty_makeup",
    "makeup": "beauty_makeup",
    "skincare": "beauty_makeup",
    "travel": "travel_lifestyle",
    "lifestyle": "travel_lifestyle",
    "fashion": "travel_lifestyle",
    "technology": "tech_gadgets",
    "tech": "tech_gadgets",
    "gadgets": "tech_gadgets",
    "gaming": "tech_gadgets",
    "business": "business_career",
    "career": "business_career",
    "finance": "business_career",
    "education": "education_learning",
    "learning": "education_learning",
}


def _normalize_category(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized else None


def _coerce_int_0_100(value: int | float | str | None) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(max(0.0, min(100.0, round(numeric))))


async def analyze_audience_relevance_via_llm(
    post_category: str | None,
    creator_dominant_category: str | None,
) -> AudienceRelevanceScore:
    """Analyze S4 audience relevance via LLM with deterministic fallback."""
    normalized_post = _normalize_category(post_category)
    normalized_creator = _normalize_category(creator_dominant_category)

    if normalized_post is None or normalized_creator is None:
        return compute_s4_audience_relevance(post_category, creator_dominant_category)

    prompt = {
        "system": (
            "Return only valid TOON format (Token-Oriented Object Notation). "
            "Use 2-space indentation for nesting. Do not use braces, brackets, or quotes."
        ),
        "user": S4_AUDIENCE_RELEVANCE_PROMPT.replace("{creator_category}", normalized_creator).replace(
            "{post_category}", normalized_post
        ),
    }

    try:
        raw_text = await asyncio.to_thread(LLMClient().generate, prompt)
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise LLMClientError("LLM returned empty response.")
        payload = toon_loads(raw_text)
        if not isinstance(payload, dict):
            raise ValueError("LLM output must be a TOON object.")

        s4_raw_0_100 = _coerce_int_0_100(payload.get("s4_raw_0_100"))
        affinity_band = payload.get("affinity_band")
        explanation = payload.get("audience_overlap_explanation")

        if not isinstance(affinity_band, str):
            raise ValueError("Invalid affinity_band from LLM output.")
        affinity_band = affinity_band.strip().upper()
        if affinity_band not in {"EXACT", "HIGH_OVERLAP", "ADJACENT", "UNRELATED", "UNKNOWN"}:
            raise ValueError("Unsupported affinity_band from LLM output.")
        if s4_raw_0_100 is None:
            raise ValueError("Missing s4_raw_0_100 from LLM output.")
        if not isinstance(explanation, str) or not explanation.strip():
            raise ValueError("Missing audience_overlap_explanation from LLM output.")

        total_0_50 = round(s4_raw_0_100 / 2.0, 1)
        notes = [explanation.strip()[:160]]

        return AudienceRelevanceScore(
            post_category=normalized_post,
            creator_dominant_category=normalized_creator,
            affinity_band=affinity_band,
            s4_raw_0_100=s4_raw_0_100,
            total_0_50=total_0_50,
            notes=notes,
        )
    except (ValueError, LLMClientError):
        return compute_s4_audience_relevance(post_category, creator_dominant_category)
    except Exception:
        return compute_s4_audience_relevance(post_category, creator_dominant_category)


def compute_s4_audience_relevance(
    post_category: str | None,
    creator_dominant_category: str | None,
) -> AudienceRelevanceScore:
    """Compute S4 from post/creator category affinity.

    Exact match = 100, adjacent (same broad group) = 75, unrelated = 15.
    Missing category input returns neutral 50 with UNKNOWN affinity.
    """

    normalized_post = _normalize_category(post_category)
    normalized_creator = _normalize_category(creator_dominant_category)
    notes: list[str] = []

    if normalized_post is None or normalized_creator is None:
        notes.append("Missing post_category or creator_dominant_category; using neutral S4 score.")
        return AudienceRelevanceScore(
            post_category=normalized_post,
            creator_dominant_category=normalized_creator,
            affinity_band="UNKNOWN",
            s4_raw_0_100=50,
            total_0_50=25.0,
            notes=notes,
        )

    if normalized_post == normalized_creator:
        return AudienceRelevanceScore(
            post_category=normalized_post,
            creator_dominant_category=normalized_creator,
            affinity_band="EXACT",
            s4_raw_0_100=100,
            total_0_50=50.0,
            notes=[],
        )

    post_group = CATEGORY_GROUPS.get(normalized_post)
    creator_group = CATEGORY_GROUPS.get(normalized_creator)
    if post_group is not None and creator_group is not None and post_group == creator_group:
        notes.append("Post and creator categories are adjacent within the same category group.")
        return AudienceRelevanceScore(
            post_category=normalized_post,
            creator_dominant_category=normalized_creator,
            affinity_band="ADJACENT",
            s4_raw_0_100=75,
            total_0_50=37.5,
            notes=notes,
        )

    notes.append("Post category appears unrelated to creator dominant category.")
    return AudienceRelevanceScore(
        post_category=normalized_post,
        creator_dominant_category=normalized_creator,
        affinity_band="UNRELATED",
        s4_raw_0_100=15,
        total_0_50=7.5,
        notes=notes,
    )
