"""Unit tests for the brand campaign prompt service."""

from __future__ import annotations

import pytest

from backend.app.ai.prompts_brand import CAMPAIGN_BRIEF_EXTRACTION_PROMPT
from backend.app.services.campaign_prompt_service import (
    _fallback_keyword_extraction,
    _infer_follower_tier,
    build_brand_profile_from_parsed,
    parse_campaign_prompt,
)


def test_fallback_keyword_extraction() -> None:
    prompt = "I need fitness creators with 50k followers"
    parsed = _fallback_keyword_extraction(prompt)
    
    assert parsed["niche"] == "fitness"
    assert parsed["min_followers"] == 50000
    assert parsed["brand_name"] == "Fallback Brand"


def test_fallback_keyword_extraction_no_niche() -> None:
    prompt = "Give me 100k+ subscribers"
    parsed = _fallback_keyword_extraction(prompt)
    
    assert parsed["niche"] == "general"
    assert parsed["min_followers"] == 100000


def test_infer_nano_tier() -> None:
    result = _infer_follower_tier("I want authentic micro influencers for my brand")
    assert result["min_followers"] == 5000
    assert result["max_followers"] == 100000


def test_infer_macro_tier() -> None:
    result = _infer_follower_tier("We need viral mega creators with massive reach")
    assert result["min_followers"] == 500000
    assert result["max_followers"] is None


def test_infer_no_tier() -> None:
    result = _infer_follower_tier("I want fitness creators")
    assert result["min_followers"] is None
    assert result["max_followers"] is None


def test_build_brand_profile_from_parsed_valid() -> None:
    parsed = {
        "brand_name": "Test Brand",
        "niche": "tech",
        "min_followers": "10000",
        "max_followers": "50000",
        "min_engagement_rate": "0.05",
    }
    profile = build_brand_profile_from_parsed(parsed)
    
    assert profile.brand_name == "Test Brand"
    assert profile.niche == "tech"
    assert profile.min_followers == 10000
    assert profile.max_followers == 50000
    assert profile.min_engagement_rate == 0.05
    assert profile.required_brand_safety_min == 70.0
    assert profile.content_quality_min == 50.0


def test_build_brand_profile_from_parsed_invalid_range_silently_fixed() -> None:
    parsed = {
        "brand_name": "Test Brand",
        "min_followers": 50000,
        "max_followers": 10000,
    }
    profile = build_brand_profile_from_parsed(parsed)
    
    assert profile.min_followers == 50000
    assert profile.max_followers is None  # fixed silently


def test_parse_campaign_prompt_fallback_on_error(monkeypatch) -> None:
    """Test that if LLM raises an error, it falls back."""
    def mock_generate(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("LLM Failure")
        
    monkeypatch.setattr("backend.app.ai.llm_client.LLMClient.generate", mock_generate)
    
    parsed = parse_campaign_prompt("fitness creators 50k followers")
    assert parsed["niche"] == "fitness"
    assert parsed["min_followers"] == 50000


def test_parse_campaign_prompt_success(monkeypatch) -> None:
    """Test successful parsing."""
    def mock_generate(*args, **kwargs):  # noqa: ANN002, ANN003
        return "brand_name: FitCo\nniche: fitness\nmin_followers: 10000\nmin_engagement_rate: 0.03"
        
    monkeypatch.setattr("backend.app.ai.llm_client.LLMClient.generate", mock_generate)
    
    parsed = parse_campaign_prompt("find me creators")
    assert parsed["brand_name"] == "FitCo"
    assert parsed["niche"] == "fitness"
    assert parsed["min_followers"] == 10000
    assert parsed["min_engagement_rate"] == 0.03
    assert parsed["follower_tier_inferred"] is None


def test_parse_campaign_prompt_infers_follower_tier_when_bounds_missing(monkeypatch) -> None:
    def mock_generate(*args, **kwargs):  # noqa: ANN002, ANN003
        return "brand_name: FitCo\nniche: fitness\nmin_followers: null\nmax_followers: null"

    monkeypatch.setattr("backend.app.ai.llm_client.LLMClient.generate", mock_generate)

    parsed = parse_campaign_prompt("I want authentic micro influencers for my brand")

    assert parsed["min_followers"] == 5000
    assert parsed["max_followers"] == 100000
    assert parsed["follower_tier_inferred"] == "nano-micro"


def test_parse_campaign_prompt_falls_back_when_toon_returns_non_dict(monkeypatch) -> None:
    def mock_generate(*args, **kwargs):  # noqa: ANN002, ANN003
        return "- not-a-dict"

    warnings: list[str] = []

    monkeypatch.setattr("backend.app.ai.llm_client.LLMClient.generate", mock_generate)
    monkeypatch.setattr("backend.app.services.campaign_prompt_service.parse_toon", lambda _text: ["not", "a", "dict"])
    monkeypatch.setattr(
        "backend.app.services.campaign_prompt_service.logger.warning",
        lambda message, *args: warnings.append(message % args),
    )

    parsed = parse_campaign_prompt("fitness creators 50k followers", brand_name="FitCo")

    assert parsed["brand_name"] == "FitCo"
    assert parsed["niche"] == "fitness"
    assert parsed["min_followers"] == 50000
    assert warnings
    assert "parse_toon returned non-dict payload" in warnings[0]


def test_campaign_prompt_documents_empty_additional_requirements_shape() -> None:
    assert "Do not omit the key entirely." in CAMPAIGN_BRIEF_EXTRACTION_PROMPT
    assert "include the key line exactly as `additional_requirements:`" in CAMPAIGN_BRIEF_EXTRACTION_PROMPT
    assert "--- OUTPUT EXAMPLE (EMPTY additional_requirements) ---" in CAMPAIGN_BRIEF_EXTRACTION_PROMPT
