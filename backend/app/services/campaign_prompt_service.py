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

    niches = ["fitness", "food", "tech", "fashion", "travel", "gaming", "beauty", "lifestyle", "finance", "education"]
    niche_found = None
    for n in niches:
        if n in prompt_lower:
            niche_found = n
            break

    min_followers = None
    follower_match = re.search(r"(\d+)k(\+)?\s*(followers|subs|subscribers)?", prompt_lower)
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
        "additional_requirements": [],
    }


def parse_campaign_prompt(prompt: str, brand_name: str | None = None) -> dict:
    """Take a natural language prompt and return extracted campaign requirements."""
    logger.info("[CampaignPromptService] Parsing campaign prompt via AI...")

    llm = LLMClient(model_name="gpt-4o-mini", temperature=0.3, max_tokens=500)
    system_prompt = "You are an expert brand marketing campaign strategist."
    user_prompt = CAMPAIGN_BRIEF_EXTRACTION_PROMPT.replace("{user_prompt}", prompt)

    try:
        response_text = llm.generate({
            "system": system_prompt,
            "user": user_prompt,
        })

        parsed = parse_toon(response_text)
        if not isinstance(parsed, dict):
            logger.warning(
                "[CampaignPromptService] parse_toon returned non-dict payload %r for response_text=%r; using fallback extraction.",
                type(parsed).__name__,
                response_text,
            )
            parsed = _fallback_keyword_extraction(prompt)
        logger.debug("[CampaignPromptService] AI extraction successful: %s", parsed)

    except Exception as exc:
        logger.exception("[CampaignPromptService] Failed to extract brief via LLM, using fallback: %s", exc)
        parsed = _fallback_keyword_extraction(prompt)

    for key, value in list(parsed.items()):
        if isinstance(value, str) and (not value.strip() or value.strip().lower() == "null"):
            parsed[key] = None

    if brand_name and brand_name.strip():
        parsed["brand_name"] = brand_name.strip()

    if not parsed.get("brand_name"):
        parsed["brand_name"] = "Unnamed Brand Campaign"

    if not parsed.get("niche"):
        parsed["niche"] = "general"

    return parsed


def build_brand_profile_from_parsed(parsed: dict) -> BrandProfile:
    """Construct a validated BrandProfile from parsed campaign data."""
    min_er = parsed.get("min_engagement_rate")
    if min_er is not None:
        try:
            min_er = float(min_er)
        except (ValueError, TypeError):
            min_er = None

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

    if min_f is not None and max_f is not None and min_f > max_f:
        max_f = None

    return BrandProfile(
        brand_name=str(parsed.get("brand_name", "Unknown Brand") or "Unknown Brand"),
        niche=str(parsed.get("niche", "general") or "general"),
        min_followers=min_f,
        max_followers=max_f,
        min_engagement_rate=min_er,
        required_brand_safety_min=70.0,
        content_quality_min=50.0,
        campaign_goal=parsed.get("campaign_goal"),
        content_type_preference=parsed.get("content_type_preference"),
    )


def build_ai_campaign_summary(prompt: str, parsed_brief: dict, brand: BrandProfile) -> str:
    """Generate a short AI summary of the interpreted campaign brief."""
    llm = LLMClient(model_name="gpt-4o-mini", temperature=0.2, max_tokens=120)
    try:
        summary = llm.generate(
            {
                "system": "You summarize parsed campaign briefs in one sentence for a brand user.",
                "user": (
                    "Write one concise sentence that explains what creator profile we will search for. "
                    f"Original prompt: {prompt}\n"
                    f"Parsed brief: {parsed_brief}\n"
                    f"Validated profile: {brand.model_dump(mode='json')}"
                ),
            }
        )
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    except Exception as exc:
        logger.warning("[CampaignPromptService] Failed to build AI campaign summary, using fallback: %s", exc)

    return (
        f"Extracted mission: find a {brand.niche} creator "
        f"with at least {brand.min_followers or 0} followers for {brand.brand_name}."
    )
