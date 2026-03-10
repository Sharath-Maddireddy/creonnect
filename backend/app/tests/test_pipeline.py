"""
End-to-end pipeline test for Creonnect AI backend.
Tests the full flow from ingestion to explanation without mocks.
"""

import sys
from datetime import datetime
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.app.ai.schemas import CreatorProfileAIInput, CreatorPostAIInput
from backend.app.ai.growth_score import compute_growth_score
from backend.app.ai.context import build_creator_context
from backend.app.ai.explain import CreatorExplanationService
from backend.app.ingestion.instagram_mapper import map_instagram_to_ai_inputs


# ------------------------------------------------
# Dummy Test Data
# ------------------------------------------------

DUMMY_SCRAPED_DATA = {
    "profile": {
        "username": "test_creator",
        "biography": "Fitness and lifestyle content creator",
        "followers_count": 50000,
        "follows_count": 500,
        "media_count": 150
    },
    "posts": [
        {
            "id": "post_001",
            "caption": "Morning workout routine! ???? #fitness #gym",
            "like_count": 2500,
            "comments_count": 150,
            "video_view_count": 45000,
            "media_type": "VIDEO",
            "media_url": "https://cdn.example/post_001.mp4",
            "thumbnail_url": "https://cdn.example/post_001.jpg",
            "timestamp": "2024-01-31T12:00:00Z"
        },
        {
            "id": "post_002",
            "caption": "Healthy meal prep for the week",
            "like_count": 1800,
            "comments_count": 80,
            "video_view_count": 30000,
            "media_type": "VIDEO",
            "media_url": "https://cdn.example/post_002.mp4",
            "thumbnail_url": "https://cdn.example/post_002.jpg",
            "timestamp": "2024-01-30T12:00:00Z"
        },
        {
            "id": "post_003",
            "caption": "Before and after transformation",
            "like_count": 5000,
            "comments_count": 300,
            "video_view_count": 80000,
            "media_type": "VIDEO",
            "media_url": "https://cdn.example/post_003.mp4",
            "thumbnail_url": "https://cdn.example/post_003.jpg",
            "timestamp": "2024-01-29T12:00:00Z"
        }
    ]
}


# ------------------------------------------------
# Tests
# ------------------------------------------------

def test_ingestion_mapping():
    """Test that ingestion correctly maps scraped data."""
    profile, posts = map_instagram_to_ai_inputs(
        DUMMY_SCRAPED_DATA["profile"],
        DUMMY_SCRAPED_DATA["posts"]
    )

    assert profile is not None, "Profile should not be None"
    assert profile.username == "test_creator"
    assert profile.followers_count == 50000
    assert profile.avg_likes > 0
    assert profile.avg_comments >= 0
    assert profile.posting_frequency_per_week > 0

    assert len(posts) == 3, "Should have 3 posts"
    assert all(p.post_type == "REEL" for p in posts), "All posts should be reels"
    assert all(p.media_url.startswith("https://cdn.example/") for p in posts), "Media URLs should be mapped"
    assert all(isinstance(p.caption_text, str) for p in posts), "Captions should be strings"

    print("✓ test_ingestion_mapping passed")


def test_growth_score_computation():
    """Test that growth score is computed correctly."""
    profile, posts = map_instagram_to_ai_inputs(
        DUMMY_SCRAPED_DATA["profile"],
        DUMMY_SCRAPED_DATA["posts"]
    )

    growth_result = compute_growth_score(profile, posts)

    assert "growth_score" in growth_result, "Should have growth_score"
    assert isinstance(growth_result["growth_score"], (int, float)), "Growth score should be numeric"
    assert 0 <= growth_result["growth_score"] <= 100, "Growth score should be 0-100"

    assert "breakdown" in growth_result, "Should have breakdown"
    assert "metrics" in growth_result, "Should have metrics"

    print("✓ test_growth_score_computation passed")


def test_context_builds():
    """Test that context builds without errors."""
    profile, posts = map_instagram_to_ai_inputs(
        DUMMY_SCRAPED_DATA["profile"],
        DUMMY_SCRAPED_DATA["posts"]
    )
    growth_result = compute_growth_score(profile, posts)

    ai_outputs = {
        "growth": growth_result,
        "niche": {"primary_niche": "fitness"},
        "posts": []
    }

    context = build_creator_context(profile, posts, ai_outputs)

    assert context is not None, "Context should not be None"
    assert "creator_profile" in context, "Should have creator_profile"
    assert "ai_analysis" in context, "Should have ai_analysis"
    assert "recent_posts" in context, "Should have recent_posts"
    assert "retrieved_knowledge" in context, "Should have retrieved_knowledge"

    print("✓ test_context_builds passed")


def test_explain_returns_without_exception():
    """Test that explain() returns without crashing (uses fallback if no API key)."""
    profile, posts = map_instagram_to_ai_inputs(
        DUMMY_SCRAPED_DATA["profile"],
        DUMMY_SCRAPED_DATA["posts"]
    )
    growth_result = compute_growth_score(profile, posts)

    ai_outputs = {
        "growth": growth_result,
        "niche": {"primary_niche": "fitness"},
        "posts": []
    }

    service = CreatorExplanationService()

    # This should NOT raise an exception - either returns LLM response or fallback
    result = service.explain_creator(profile, posts, ai_outputs)

    assert result is not None, "Result should not be None"

    # Result is either a string (LLM success) or dict (fallback)
    if isinstance(result, dict):
        assert result.get("status") == "partial", "Fallback should have status=partial"
        assert "growth" in result, "Fallback should include growth data"
        print("✓ test_explain_returns_without_exception passed (using fallback)")
    else:
        assert isinstance(result, str), "LLM result should be string"
        print("✓ test_explain_returns_without_exception passed (LLM response)")


def run_all_tests():
    """Run all pipeline tests."""
    print("\n" + "=" * 50)
    print("Running Creonnect Pipeline Tests")
    print("=" * 50 + "\n")

    test_ingestion_mapping()
    test_growth_score_computation()
    test_context_builds()
    test_explain_returns_without_exception()

    print("\n" + "=" * 50)
    print("All tests passed! ✓")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    run_all_tests()


