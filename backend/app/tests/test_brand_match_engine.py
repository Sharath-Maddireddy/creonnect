"""Unit tests for brand-creator match scoring engine."""

from __future__ import annotations

from backend.app.analytics.brand_match_engine import (
    _audience_size_fit,
    _engagement_quality,
    _semantic_fit,
    score_creator_against_brand,
)
from backend.app.domain.brand_models import BrandProfile


def _brand(**kwargs: float | int | str) -> BrandProfile:
    return BrandProfile(brand_name="TestBrand", niche="fitness", **kwargs)


def test_exact_niche_match_scores_20() -> None:
    result = score_creator_against_brand("c1", _brand(), creator_dominant_category="fitness")
    assert result.niche_fit == 20.0


def test_no_niche_match_scores_3() -> None:
    result = score_creator_against_brand("c1", _brand(), creator_dominant_category="cooking")
    assert result.niche_fit == 3.0


def test_unknown_niche_scores_neutral() -> None:
    result = score_creator_against_brand("c1", _brand(), creator_dominant_category=None)
    assert result.niche_fit == 8.0


def test_semantic_fit_with_embeddings_scores_20_on_identical_vectors() -> None:
    score, notes = _semantic_fit(
        creator_category="fitness",
        brand_niche="fitness",
        brand_search_embedding=[1.0, 0.0, 0.0],
        creator_embedding=[1.0, 0.0, 0.0],
    )
    assert score == 20.0
    assert notes and "cosine similarity=1.000" in notes[0]


def test_engagement_quality_handles_none_predicted_er() -> None:
    score, notes = _engagement_quality(ahs_score=80.0, predicted_er=None)
    assert score == 12.0
    assert any("No predicted engagement rate available." in note for note in notes)


def test_audience_size_fit_ratio_bands() -> None:
    near_score, _ = _audience_size_fit(follower_count=9_000, min_followers=10_000, max_followers=50_000)
    mid_score, _ = _audience_size_fit(follower_count=3_000, min_followers=10_000, max_followers=50_000)
    far_score, _ = _audience_size_fit(follower_count=1_000, min_followers=10_000, max_followers=50_000)

    assert near_score == 12.0
    assert mid_score == 6.0
    assert far_score == 2.0


def test_predicted_engagement_rate_int_is_treated_as_numeric() -> None:
    result = score_creator_against_brand(
        "c1",
        _brand(),
        creator_dominant_category="fitness",
        predicted_engagement_rate=0,
    )
    assert any("Low engagement rate 0.0%." in note for note in result.notes)
    assert not any("No predicted engagement rate available." in note for note in result.notes)


def test_adult_content_disqualifies() -> None:
    result = score_creator_against_brand(
        "c1",
        _brand(),
        creator_dominant_category="fitness",
        adult_content_detected=True,
    )
    assert result.disqualified is True
    assert result.total_match_score == 0.0
    assert result.match_band == "POOR"


def test_unknown_adult_content_is_not_auto_disqualifying() -> None:
    result = score_creator_against_brand(
        "c1",
        _brand(),
        creator_dominant_category="fitness",
        adult_content_detected=None,
        visual_quality_score_total=40.0,
    )
    assert result.disqualified is False
    assert "Adult content status unknown; defaulting to non-disqualifying treatment." in result.notes


def test_low_brand_safety_disqualifies() -> None:
    result = score_creator_against_brand(
        "c1",
        _brand(required_brand_safety_min=80.0),
        brand_safety_score_total_0_50=30.0,
    )
    assert result.disqualified is True


def test_content_quality_min_disqualifies() -> None:
    result = score_creator_against_brand(
        "c1",
        _brand(content_quality_min=80.0),
        visual_quality_score_total=30.0,
    )
    assert result.disqualified is True
    assert any("Content quality score" in reason for reason in result.disqualify_reasons)


def test_top_creator_scores_excellent() -> None:
    result = score_creator_against_brand(
        "c1",
        _brand(min_followers=10000, max_followers=500000),
        creator_dominant_category="fitness",
        follower_count=85000,
        ahs_score=85.0,
        predicted_engagement_rate=0.06,
        visual_quality_score_total=45.0,
        brand_safety_score_total_0_50=48.0,
        adult_content_detected=False,
    )
    assert result.total_match_score >= 80.0
    assert result.match_band == "EXCELLENT"
    assert not result.disqualified



