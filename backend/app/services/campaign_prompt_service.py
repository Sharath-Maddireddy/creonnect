"""Service for parsing natural language brand campaign prompts into structured profiles."""

from __future__ import annotations

import re

from backend.app.ai.llm_client import LLMClient
from backend.app.ai.prompts_brand import CAMPAIGN_BRIEF_EXTRACTION_PROMPT
from backend.app.ai.toon import loads as parse_toon
from backend.app.domain.brand_models import BrandProfile
from backend.app.utils.logger import logger

def _fallback_keyword_extraction(prompt: str) -> dict:
    """Best-effort regex extraction if LLM fails."""
    prompt_lower = prompt.lower()
    
    # Simple niche matching
    niches = ["fitness", "food", "tech", "fashion", "travel", "gaming", "beauty", "lifestyle", "finance", "education"]
    niche_found = None
    for n in niches:
        if n in prompt_lower:
            niche_found = n
            break

    # Simple follower min matching (e.g. "50k", "100k+")
    min_followers = None
    follower_match = re.search(r'(\d+)k(\+)?\s*(followers|subs|subscribers)?', prompt_lower)
    if follower_match:
        try:
            min_followers = int(follower_match.group(1)) * 1000
        except ValueError:
            pass

    return {
        "brand_name": "Fallback Brand",
        "niche": niche_found or "general",
        "min_followers": min_followers,
        "max_followers": None,
        "min_engagement_rate": None,
        "campaign_goal": None,
        "content_type_preference": None,
        "additional_requirements": []
    }

def parse_campaign_prompt(prompt: str, brand_name: str | None = None) -> dict:
    """
    Takes a natural language prompt and returns a dictionary of extracted campaign requirements.
    """
    logger.info("[CampaignPromptService] Parsing campaign prompt via AI...")
    
    llm = LLMClient(model_name="gpt-4o-mini", temperature=0.3, max_tokens=500)
    system_prompt = "You are an expert brand marketing campaign strategist."
    user_prompt = CAMPAIGN_BRIEF_EXTRACTION_PROMPT.replace("{user_prompt}", prompt)
    
    try:
        response_text = llm.generate({
            "system": system_prompt,
            "user": user_prompt
        })
        
        parsed = parse_toon(response_text)
        logger.info(f"[CampaignPromptService] AI extraction successful: {parsed}")
        
    except Exception as e:
        logger.exception(f"[CampaignPromptService] Failed to extract brief via LLM, using fallback: {e}")
        parsed = _fallback_keyword_extraction(prompt)

    # Clean up empty strings and 'null' text
    for key, value in list(parsed.items()):
        if isinstance(value, str) and (not value.strip() or value.strip().lower() == "null"):
            parsed[key] = None

    if brand_name and brand_name.strip():
        parsed["brand_name"] = brand_name.strip()
        
    # Ensure brand_name exists
    if not parsed.get("brand_name"):
        parsed["brand_name"] = "Unnamed Brand Campaign"
        
    # Ensure niche exists (defaults to 'general' if absolutely nothing is found)
    if not parsed.get("niche"):
        parsed["niche"] = "general"

    return parsed

def build_brand_profile_from_parsed(parsed: dict) -> BrandProfile:
    """
    Constructs a validated BrandProfile from the loose dictionary returned by the parser.
    """
    # Safe float parsing
    min_er = parsed.get("min_engagement_rate")
    if min_er is not None:
        try:
            min_er = float(min_er)
        except (ValueError, TypeError):
            min_er = None

    # Safe int parsing
    min_f = parsed.get("min_followers")
    if min_f is not None:
        try:
            min_f = int(min_f)
        except (ValueError, TypeError):
            min_f = None
            
    max_f = parsed.get("max_followers")
    if max_f is not None:
        try:
            max_f = int(max_f)
        except (ValueError, TypeError):
            max_f = None
            
    # Fix invalid ranges silently instead of throwing 500
    if min_f is not None and max_f is not None and min_f > max_f:
        max_f = None

    return BrandProfile(
        brand_name=str(parsed.get("brand_name", "Unknown Brand") or "Unknown Brand"),
        niche=str(parsed.get("niche", "general") or "general"),
        min_followers=min_f,
        max_followers=max_f,
        min_engagement_rate=min_er,
        required_brand_safety_min=70.0,
        content_quality_min=50.0
    )
