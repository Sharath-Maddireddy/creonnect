import pytest
from backend.app.analytics.brand_match_engine import (
    score_creator_against_brand
)
from backend.app.services.campaign_prompt_service import BrandProfile

def create_mock_brand() -> BrandProfile:
    return BrandProfile(
        brand_name="TestBrand",
        niche="fitness",
        min_followers=100000,
        max_followers=None,
        min_engagement_rate=0.01
    )

def test_perfect_match():
    brand = create_mock_brand()
    
    # 1.0 similarity embedding
    embedding = [0.1] * 1536
    
    score = score_creator_against_brand(
        account_id="perfect_creator",
        brand=brand,
        creator_dominant_category="fitness",
        brand_search_embedding=embedding,
        creator_embedding=embedding,
        follower_count=250000,
        avg_views=50000,
        avg_likes=10000,
        avg_comments=500,
        ahs_score=85,
        predicted_engagement_rate=0.042, # > 0.01
        visual_quality_score_total=45.0,
        brand_safety_score_total_0_50=50.0,
        adult_content_detected=False
    )
    
    assert not score.disqualified
    assert score.match_band == "EXCELLENT"
    assert score.niche_fit == 20.0
    assert score.audience_size_fit == 20.0
    assert score.brand_safety_fit == 20.0
    assert score.total_match_score > 90.0

def test_low_score_low_followers():
    brand = create_mock_brand()
    
    score = score_creator_against_brand(
        account_id="small_creator",
        brand=brand,
        creator_dominant_category="fitness",
        follower_count=50000, # Less than 100k
        ahs_score=85,
    )
    
    # It does not disqualify, but the audience size score should drop heavily.
    assert not score.disqualified
    assert score.audience_size_fit < 20.0

def test_disqualified_adult_content():
    brand = create_mock_brand()
    
    score = score_creator_against_brand(
        account_id="unsafe_creator",
        brand=brand,
        creator_dominant_category="fitness",
        follower_count=200000,
        ahs_score=85,
        adult_content_detected=True # Triggers safety fail
    )
    
    assert score.disqualified
    assert any("Adult content detected" in r for r in score.disqualify_reasons)

def test_disqualified_bot_engagement():
    brand = create_mock_brand()
    
    score = score_creator_against_brand(
        account_id="bot_creator",
        brand=brand,
        creator_dominant_category="fitness",
        follower_count=200000,
        avg_views=50,
        avg_likes=50,    # Very low likes relative to followers -> triggers authenticity flag
        avg_comments=2,
        ahs_score=30,
    )
    
    assert score.disqualified
    assert any("Failed Audience Authenticity Check" in r for r in score.disqualify_reasons)
