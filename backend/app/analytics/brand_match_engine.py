"""Deterministic brand-creator match scoring engine."""

from __future__ import annotations

import math
from typing import Literal

from backend.app.analytics.audience_quality import calculate_authenticity_score
from backend.app.domain.brand_models import BrandProfile, CreatorMatchScore
from backend.app.utils.logger import logger


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _niche_fit(creator_category: str | None, brand_niche: str) -> tuple[float, list[str]]:
    """
    Score niche fit (0-20).

    - Exact match -> 20
    - Partial overlap or shared word -> 12
    - Missing creator category -> 8
    - No match -> 3
    """
    notes: list[str] = []
    if not creator_category:
        notes.append("Creator category unknown; applying neutral niche score.")
        return 8.0, notes

    category = creator_category.lower().strip()
    niche = brand_niche.lower().strip()
    if category == niche:
        notes.append(f"Exact niche match: '{category}'.")
        return 20.0, notes
    if niche in category or category in niche:
        notes.append(f"Partial niche match: creator='{category}', brand='{niche}'.")
        return 12.0, notes

    category_words = set(category.split())
    niche_words = set(niche.split())
    overlap = category_words & niche_words
    if overlap:
        notes.append(f"Niche word overlap: {sorted(overlap)}.")
        return 12.0, notes

    notes.append(f"No niche match: creator='{category}', brand='{niche}'.")
    return 3.0, notes


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    if magnitude1 == 0.0 or magnitude2 == 0.0:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)


def _semantic_fit(
    creator_category: str | None,
    brand_niche: str,
    *,
    brand_search_embedding: list[float] | None = None,
    creator_embedding: list[float] | None = None,
) -> tuple[float, list[str]]:
    """
    Score semantic niche fit (0-20) using embeddings when available,
    otherwise fall back to the legacy niche rules.
    """
    if brand_search_embedding is not None and creator_embedding is not None:
        similarity = _cosine_similarity(brand_search_embedding, creator_embedding)
        normalized = _clamp((similarity + 1.0) / 2.0, 0.0, 1.0)
        semantic_score = _clamp(normalized * 20.0, 0.0, 20.0)

        # Make common positive similarities feel stronger than a purely linear map.
        if similarity >= 0.5:
            semantic_score = max(semantic_score, 20.0)
        elif similarity < 0.2:
            semantic_score = min(semantic_score, 5.0)

        notes = [
            (
                f"AI Semantic Match: cosine similarity={similarity:.3f} "
                f"-> niche_fit={semantic_score:.1f}/20."
            )
        ]
        return round(semantic_score, 2), notes

    score, notes = _niche_fit(creator_category, brand_niche)
    return score, [f"Fallback Match: {note}" for note in notes]


def _engagement_quality(ahs_score: float | None, predicted_er: float | None) -> tuple[float, list[str]]:
    """
    Score engagement quality (0-20).

    - ahs_score scaled from 0-100 to 0-15
    - predicted_er bonus: >=5% +5, >=3% +3, >=1% +1
    """
    notes: list[str] = []
    ahs = _clamp(float(ahs_score or 0.0), 0.0, 100.0)
    base = ahs * 0.15

    er_bonus = 0.0
    if isinstance(predicted_er, float):
        if predicted_er >= 0.05:
            er_bonus = 5.0
            notes.append(f"High engagement rate {predicted_er:.1%} -> +5 bonus.")
        elif predicted_er >= 0.03:
            er_bonus = 3.0
            notes.append(f"Good engagement rate {predicted_er:.1%} -> +3 bonus.")
        elif predicted_er >= 0.01:
            er_bonus = 1.0
            notes.append(f"Moderate engagement rate {predicted_er:.1%} -> +1 bonus.")
        else:
            notes.append(f"Low engagement rate {predicted_er:.1%}.")
    else:
        notes.append("No predicted engagement rate available.")

    total = _clamp(base + er_bonus, 0.0, 20.0)
    notes.append(f"AHS={ahs:.1f} -> base={base:.1f}, ER bonus={er_bonus:.1f}.")
    return round(total, 2), notes


def _brand_safety_fit(safety_score_0_50: float) -> tuple[float, list[str]]:
    """Score brand safety fit by scaling S6 0-50 to 0-20."""
    notes: list[str] = []
    scaled = _clamp(safety_score_0_50 * (20.0 / 50.0), 0.0, 20.0)
    notes.append(f"S6={safety_score_0_50:.1f}/50 -> brand_safety_fit={scaled:.1f}/20.")
    return round(scaled, 2), notes


def _content_quality_fit(visual_quality_0_50: float) -> tuple[float, list[str]]:
    """Score content quality fit by scaling S1 0-50 to 0-20."""
    notes: list[str] = []
    scaled = _clamp(visual_quality_0_50 * (20.0 / 50.0), 0.0, 20.0)
    notes.append(f"S1={visual_quality_0_50:.1f}/50 -> content_quality_fit={scaled:.1f}/20.")
    return round(scaled, 2), notes


def _audience_size_fit(
    follower_count: int | None,
    min_followers: int | None,
    max_followers: int | None,
) -> tuple[float, list[str]]:
    """
    Score follower count fit (0-20).

    - No bounds -> 15
    - Within range -> 20
    - Within 2x bounds -> 12
    - Within 5x bounds -> 6
    - Else -> 2
    """
    notes: list[str] = []
    if min_followers is None and max_followers is None:
        notes.append("No follower bounds specified; neutral audience size score.")
        return 15.0, notes
    if follower_count is None:
        notes.append("Creator follower count unknown.")
        return 8.0, notes

    follower_value = max(0, int(follower_count))
    lower = int(min_followers) if min_followers is not None else 0
    upper = int(max_followers) if max_followers is not None else None

    within_lower = follower_value >= lower
    within_upper = upper is None or follower_value <= upper
    if within_lower and within_upper:
        upper_label = f"{upper:,}" if upper is not None else "inf"
        notes.append(f"Follower count {follower_value:,} within target range [{lower:,}, {upper_label}].")
        return 20.0, notes

    if follower_value < lower:
        ratio = lower / max(follower_value, 1)
    else:
        bounded_upper = max(upper or 1, 1)
        ratio = follower_value / bounded_upper

    if ratio <= 2.0:
        notes.append(f"Follower count {follower_value:,} within 2x of target range.")
        return 12.0, notes
    if ratio <= 5.0:
        notes.append(f"Follower count {follower_value:,} within 5x of target range.")
        return 6.0, notes

    notes.append(f"Follower count {follower_value:,} is >5x outside target range.")
    return 2.0, notes


def _match_band(score: float) -> Literal["EXCELLENT", "GOOD", "MODERATE", "POOR"]:
    if score >= 80.0:
        return "EXCELLENT"
    if score >= 60.0:
        return "GOOD"
    if score >= 40.0:
        return "MODERATE"
    return "POOR"


def score_creator_against_brand(
    account_id: str,
    brand: BrandProfile,
    *,
    creator_dominant_category: str | None = None,
    brand_search_embedding: list[float] | None = None,
    creator_embedding: list[float] | None = None,
    follower_count: int | None = None,
    avg_views: int = 0,
    avg_likes: int = 0,
    avg_comments: int = 0,
    ahs_score: float | None = None,
    predicted_engagement_rate: float | None = None,
    visual_quality_score_total: float = 0.0,
    brand_safety_score_total_0_50: float = 50.0,
    adult_content_detected: bool | None = None,
) -> CreatorMatchScore:
    """Compute deterministic match score for one creator against a brand profile."""
    notes: list[str] = []
    disqualify_reasons: list[str] = []

    visual_quality = _clamp(float(visual_quality_score_total or 0.0), 0.0, 50.0)
    brand_safety = _clamp(float(brand_safety_score_total_0_50 or 0.0), 0.0, 50.0)
    authenticity_score = calculate_authenticity_score(
        follower_count=int(follower_count or 0),
        avg_views=int(avg_views or 0),
        avg_likes=int(avg_likes or 0),
        avg_comments=int(avg_comments or 0),
    )
    predicted_er = (
        _clamp(float(predicted_engagement_rate), 0.0, 1.0)
        if isinstance(predicted_engagement_rate, float)
        else None
    )

    niche_fit, niche_notes = _semantic_fit(
        creator_dominant_category,
        brand.niche,
        brand_search_embedding=brand_search_embedding,
        creator_embedding=creator_embedding,
    )
    engagement_quality, engagement_notes = _engagement_quality(ahs_score, predicted_er)
    brand_safety_fit, safety_notes = _brand_safety_fit(brand_safety)
    content_quality_fit, content_notes = _content_quality_fit(visual_quality)
    audience_size_fit, audience_notes = _audience_size_fit(follower_count, brand.min_followers, brand.max_followers)
    notes.extend(niche_notes + engagement_notes + safety_notes + content_notes + audience_notes)

    disqualified = False
    notes.append(f"Audience authenticity score={authenticity_score:.1f}/100.")

    if authenticity_score < 40.0:
        disqualified = True
        disqualify_reasons.append(
            "Failed Audience Authenticity Check "
            f"(Score: {authenticity_score:.1f}). High probability of fake followers or bot engagement."
        )

    if adult_content_detected is True:
        disqualified = True
        disqualify_reasons.append("Adult content detected on creator posts.")
    elif adult_content_detected is None:
        disqualified = True
        disqualify_reasons.append("Adult content status unknown.")

    safety_score_0_100 = _clamp(brand_safety * 2.0, 0.0, 100.0)
    if safety_score_0_100 < brand.required_brand_safety_min:
        disqualified = True
        disqualify_reasons.append(
            f"Brand safety score {safety_score_0_100:.0f} below required {brand.required_brand_safety_min:.0f}."
        )

    if (
        brand.min_engagement_rate is not None
        and predicted_er is not None
        and predicted_er < brand.min_engagement_rate
    ):
        disqualified = True
        disqualify_reasons.append(
            f"Engagement rate {predicted_er:.1%} below required {brand.min_engagement_rate:.1%}."
        )

    if disqualified:
        total = 0.0
    else:
        total = _clamp(
            niche_fit + engagement_quality + brand_safety_fit + content_quality_fit + audience_size_fit,
            0.0,
            100.0,
        )

    logger.debug(
        "[BrandMatch] account_id=%s disqualified=%s total=%.2f",
        account_id,
        disqualified,
        total,
    )
    return CreatorMatchScore(
        account_id=account_id,
        total_match_score=round(total, 2),
        niche_fit=round(_clamp(niche_fit, 0.0, 20.0), 2),
        engagement_quality=round(_clamp(engagement_quality, 0.0, 20.0), 2),
        brand_safety_fit=round(_clamp(brand_safety_fit, 0.0, 20.0), 2),
        content_quality_fit=round(_clamp(content_quality_fit, 0.0, 20.0), 2),
        audience_size_fit=round(_clamp(audience_size_fit, 0.0, 20.0), 2),
        match_band=_match_band(total),
        disqualified=disqualified,
        disqualify_reasons=disqualify_reasons,
        notes=notes,
    )
