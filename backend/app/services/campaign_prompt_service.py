"""Campaign prompt parsing service."""

from __future__ import annotations

import re
from typing import Any

from backend.app.ai.llm_client import LLMClient
from backend.app.ai.prompts_brand import CAMPAIGN_BRIEF_EXTRACTION_PROMPT
from backend.app.ai.toon import loads as parse_toon
from backend.app.domain.brand_models import BrandProfile
from backend.app.utils.logger import logger


_NICHE_KEYWORDS = [
    "fitness",
    "food",
    "tech",
    "fashion",
    "travel",
    "gaming",
    "beauty",
    "lifestyle",
    "finance",
]

_FOLLOWER_BUCKETS: list[tuple[str, int | None, int | None]] = [
    ("nano creators", 1_000, 10_000),
    ("micro creators", 10_000, 100_000),
    ("mid-tier", 100_000, 500_000),
    ("macro", 500_000, 1_000_000),
]


def _split_prompt_template(template: str) -> dict[str, str]:
    """Split the brand prompt template into system and user message strings."""

    text = template.strip()
    system_marker = "System:"
    user_marker = "\nUser:"

    if not text.startswith(system_marker) or user_marker not in text:
        raise ValueError("CAMPAIGN_BRIEF_EXTRACTION_PROMPT must contain System:/User: sections.")

    system_part, user_part = text.split(user_marker, 1)
    system = system_part[len(system_marker):].strip()
    user = user_part.strip()
    return {"system": system, "user": user}


def _coerce_int(value: Any) -> int | None:
    """Convert a loose value into an integer when possible."""

    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    """Convert a loose value into a float when possible."""

    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, numeric))


def _coerce_string(value: Any) -> str | None:
    """Normalize a string-like field."""

    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text or None


def _coerce_string_list(value: Any) -> list[str] | None:
    """Normalize additional requirements into a list of strings."""

    if value is None:
        return None
    if isinstance(value, list):
        result = [_coerce_string(item) for item in value]
        filtered = [item for item in result if item]
        return filtered or None
    text = _coerce_string(value)
    return [text] if text else None


def _extract_follower_bounds(text: str) -> tuple[int | None, int | None]:
    """Best-effort extraction of follower thresholds from natural language."""

    lowered = text.lower()
    for label, min_followers, max_followers in _FOLLOWER_BUCKETS:
        if label in lowered:
            return min_followers, max_followers

    exact_match = re.search(r"(\d+(?:\.\d+)?)\s*([km])?\s+followers\b", lowered)
    if exact_match:
        value = _normalize_number_token(exact_match.group(1), exact_match.group(2))
        if value is not None:
            return value, value

    plus_match = re.search(r"(\d+(?:\.\d+)?)\s*([km])\s*\+", lowered)
    if plus_match:
        value = _normalize_number_token(plus_match.group(1), plus_match.group(2))
        return value, None

    range_match = re.search(
        r"(\d+(?:\.\d+)?)\s*([km])?\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*([km])\b",
        lowered,
    )
    if range_match:
        min_value = _normalize_number_token(range_match.group(1), range_match.group(2))
        max_value = _normalize_number_token(range_match.group(3), range_match.group(4))
        return min_value, max_value

    minimum_match = re.search(r"(?:min(?:imum)?|at least)\s*(\d+(?:\.\d+)?)\s*([km])", lowered)
    if minimum_match:
        min_value = _normalize_number_token(minimum_match.group(1), minimum_match.group(2))
        return min_value, None

    return None, None


def _normalize_number_token(number_text: str | None, suffix: str | None) -> int | None:
    """Normalize number tokens like 50k or 1.5m to integers."""

    if not number_text:
        return None
    try:
        value = float(number_text)
    except (TypeError, ValueError):
        return None

    multiplier = 1
    normalized_suffix = (suffix or "").lower()
    if normalized_suffix == "k":
        multiplier = 1_000
    elif normalized_suffix == "m":
        multiplier = 1_000_000
    return int(value * multiplier)


def _extract_engagement_rate(text: str) -> float | None:
    """Extract a minimum engagement-rate hint from natural language."""

    lowered = text.lower()
    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", lowered)
    if percent_match:
        try:
            return max(0.0, min(1.0, float(percent_match.group(1)) / 100.0))
        except ValueError:
            return None

    decimal_match = re.search(r"(0?\.\d+)\s*(?:engagement|er)", lowered)
    if decimal_match:
        try:
            return max(0.0, min(1.0, float(decimal_match.group(1))))
        except ValueError:
            return None

    return None


def _fallback_parse_campaign_prompt(prompt: str, brand_name: str | None = None) -> dict[str, Any]:
    """Best-effort keyword and regex extraction when LLM parsing fails."""

    lowered = prompt.lower()
    niche = next((keyword for keyword in _NICHE_KEYWORDS if keyword in lowered), None)
    min_followers, max_followers = _extract_follower_bounds(prompt)
    min_engagement_rate = _extract_engagement_rate(prompt)

    content_type_preference = None
    for token in ("reels", "stories", "static posts", "ugc videos", "tutorial content", "videos"):
        if token in lowered:
            content_type_preference = token
            break

    campaign_goal = None
    for token in ("awareness", "sales", "launch", "conversions", "trials", "engagement", "ugc"):
        if token in lowered:
            campaign_goal = f"Drive {token}"
            break

    additional_requirements: list[str] = []
    for marker in ("india", "female creators", "male creators", "english speaking", "budget friendly"):
        if marker in lowered:
            additional_requirements.append(marker)

    parsed = {
        "brand_name": brand_name or None,
        "niche": niche,
        "min_followers": min_followers,
        "max_followers": max_followers,
        "min_engagement_rate": min_engagement_rate,
        "campaign_goal": campaign_goal,
        "content_type_preference": content_type_preference,
        "additional_requirements": additional_requirements or None,
    }
    logger.info("[CampaignPrompt] Using fallback prompt parser for brand_name=%s", brand_name)
    return parsed


async def parse_campaign_prompt(prompt: str, brand_name: str | None = None) -> dict:
    """
    Parse a natural-language brand brief into a structured campaign dictionary.

    Args:
        prompt: Natural-language brand request.
        brand_name: Optional explicit brand name override.

    Returns:
        Parsed campaign brief dictionary.
    """

    template_parts = _split_prompt_template(CAMPAIGN_BRIEF_EXTRACTION_PROMPT)
    formatted_user_prompt = template_parts["user"].format(user_prompt=prompt)
    client = LLMClient(model_name="gpt-4o-mini", temperature=0.3, max_tokens=500)

    try:
        response_text = client.generate(
            {
                "system": template_parts["system"],
                "user": formatted_user_prompt,
            }
        )
        parsed = parse_toon(response_text or "")
        if not isinstance(parsed, dict):
            raise ValueError("TOON payload did not parse to a dictionary")
    except Exception as exc:
        logger.warning("[CampaignPrompt] LLM parse failed, using fallback: %s", exc)
        parsed = _fallback_parse_campaign_prompt(prompt, brand_name=brand_name)

    normalized = {
        "brand_name": _coerce_string(brand_name) or _coerce_string(parsed.get("brand_name")),
        "niche": _coerce_string(parsed.get("niche")),
        "min_followers": _coerce_int(parsed.get("min_followers")),
        "max_followers": _coerce_int(parsed.get("max_followers")),
        "min_engagement_rate": _coerce_float(parsed.get("min_engagement_rate")),
        "campaign_goal": _coerce_string(parsed.get("campaign_goal")),
        "content_type_preference": _coerce_string(parsed.get("content_type_preference")),
        "additional_requirements": _coerce_string_list(parsed.get("additional_requirements")),
    }
    return normalized


def build_brand_profile_from_parsed(parsed: dict) -> BrandProfile:
    """
    Build a validated ``BrandProfile`` from a parsed campaign brief dictionary.

    Args:
        parsed: Parsed campaign brief payload.

    Returns:
        Validated ``BrandProfile`` instance.
    """

    payload = parsed or {}
    min_followers = _coerce_int(payload.get("min_followers"))
    max_followers = _coerce_int(payload.get("max_followers"))
    if min_followers is not None and max_followers is not None and min_followers > max_followers:
        min_followers, max_followers = max_followers, min_followers

    profile = BrandProfile(
        brand_name=_coerce_string(payload.get("brand_name")) or "Unknown Brand",
        niche=_coerce_string(payload.get("niche")) or "general",
        min_followers=min_followers,
        max_followers=max_followers,
        min_engagement_rate=_coerce_float(payload.get("min_engagement_rate")),
        required_brand_safety_min=70.0,
        content_quality_min=50.0,
    )
    logger.info(
        "[CampaignPrompt] Built BrandProfile brand=%s niche=%s min_followers=%s max_followers=%s",
        profile.brand_name,
        profile.niche,
        profile.min_followers,
        profile.max_followers,
    )
    return profile
