"""Deterministic S4 audience relevance scoring."""

from __future__ import annotations

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
