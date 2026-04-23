from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.domain.brand_models import BrandProfile, CreatorMatchScore


def test_brand_profile_rejects_blank_brand_name() -> None:
    with pytest.raises(ValidationError):
        BrandProfile(brand_name="   ", niche="fitness")


def test_brand_profile_rejects_blank_niche() -> None:
    with pytest.raises(ValidationError):
        BrandProfile(brand_name="FitCo", niche="   ")


def test_creator_match_score_rejects_blank_account_id() -> None:
    with pytest.raises(ValidationError):
        CreatorMatchScore(
            account_id="   ",
            total_match_score=90,
            niche_fit=20,
            engagement_quality=18,
            brand_safety_fit=18,
            content_quality_fit=17,
            audience_size_fit=17,
            match_band="EXCELLENT",
        )
