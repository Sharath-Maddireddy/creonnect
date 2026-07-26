from __future__ import annotations

"""Niche discovery engine using an LLM to infer creator niches.

Provides an async `discover_creator_niche` function which constructs a
strict system prompt, builds a user payload from recent posts and profile
metadata, calls the LLM via `LLMClient`, parses TOON output using the
project `toon` parser, and returns a validated `CreatorNiche`.

The function is defensive: on any LLM or parsing error it logs the
failure and returns a conservative fallback `CreatorNiche`.
"""

from collections import Counter
import re
from typing import List
import asyncio

from backend.app.ai.llm_client import LLMClient
from backend.app.ai.toon import loads as toon_loads
from backend.app.domain.post_models import SinglePostInsights
from backend.app.domain.trend_models import CreatorNiche
from backend.app.utils.logger import logger


_NICHE_KEYWORDS: dict[str, set[str]] = {
    "Fitness": {
        "abs",
        "bodybuilding",
        "cardio",
        "calisthenics",
        "crossfit",
        "exercise",
        "fatloss",
        "fitness",
        "gym",
        "hiit",
        "health",
        "mobility",
        "muscle",
        "protein",
        "running",
        "strength",
        "training",
        "weightloss",
        "workout",
        "yoga",
        "zumba",
    },
    "Food": {
        "bake",
        "biryani",
        "chef",
        "cook",
        "cooking",
        "cuisine",
        "desi",
        "dessert",
        "dhaba",
        "dinner",
        "eat",
        "food",
        "foodie",
        "homemade",
        "kitchen",
        "lunch",
        "recipe",
        "restaurant",
        "snack",
        "streetfood",
        "taste",
        "thali",
    },
    "Beauty": {
        "beauty",
        "blush",
        "eyebrow",
        "foundation",
        "glow",
        "glam",
        "hair",
        "highlighter",
        "lipstick",
        "makeup",
        "mascara",
        "nails",
        "serum",
        "skincare",
        "spf",
        "sunscreen",
        "tutorial",
    },
    "Fashion": {
        "dress",
        "ethnic",
        "fashion",
        "fitcheck",
        "kurta",
        "lehenga",
        "ootd",
        "outfit",
        "saree",
        "style",
        "styling",
        "thrift",
        "wear",
        "wardrobe",
    },
    "Travel": {
        "beach",
        "explore",
        "hill",
        "hotel",
        "india",
        "itinerary",
        "mountains",
        "offbeat",
        "resort",
        "solo",
        "travel",
        "traveller",
        "trip",
        "vacation",
        "vlog",
        "wanderlust",
    },
    "Tech": {
        "ai",
        "app",
        "build",
        "coding",
        "developer",
        "gadget",
        "laptop",
        "programming",
        "review",
        "saas",
        "software",
        "startup",
        "tech",
        "unboxing",
    },
    "Finance": {
        "business",
        "crypto",
        "entrepreneur",
        "finance",
        "freelance",
        "growth",
        "investing",
        "money",
        "passive",
        "profit",
        "saving",
        "sip",
        "startup",
        "stocks",
        "trading",
    },
    "Motivation": {
        "attitude",
        "confidence",
        "discipline",
        "goals",
        "grind",
        "growth",
        "hustle",
        "inspire",
        "inspiration",
        "life",
        "mindset",
        "motivation",
        "motivational",
        "persistence",
        "positivity",
        "quotes",
        "success",
        "thoughts",
        "vision",
        "winning",
    },
    "Lifestyle": {
        "aesthetic",
        "daily",
        "day",
        "grwm",
        "lifestyle",
        "living",
        "morning",
        "productive",
        "productivity",
        "routine",
        "selfcare",
        "vlog",
        "wellness",
    },
    "Education": {
        "career",
        "course",
        "education",
        "exam",
        "explainer",
        "facts",
        "howto",
        "knowledge",
        "learn",
        "learning",
        "school",
        "science",
        "skills",
        "study",
        "teacher",
        "tips",
        "tutorial",
        "upsc",
    },
    "Comedy": {
        "comedy",
        "comic",
        "fun",
        "funny",
        "humor",
        "joke",
        "lol",
        "meme",
        "prank",
        "roast",
        "skit",
        "standup",
        "troll",
    },
}


def _tokenize_text(value: str | None) -> list[str]:
    if not isinstance(value, str):
        return []
    return re.findall(r"[a-z0-9]+", value.lower())


def _fallback_creator_niche(
    posts: List[SinglePostInsights],
    bio: str | None,
    username: str | None,
) -> CreatorNiche:
    tokens: list[str] = []
    tokens.extend(_tokenize_text(username))
    tokens.extend(_tokenize_text(bio))
    media_type_counts: Counter[str] = Counter()
    for post in posts[:20]:
        tokens.extend(_tokenize_text(getattr(post, "caption_text", None)))
        tokens.extend(_tokenize_text(getattr(post, "post_category", None)))
        tokens.extend(_tokenize_text(getattr(post, "creator_dominant_category", None)))
        media_type = str(getattr(post, "media_type", "") or "").lower()
        if media_type:
            media_type_counts[media_type] += 1

    counts = Counter(tokens)
    scores: dict[str, int] = {}
    for category, keywords in _NICHE_KEYWORDS.items():
        scores[category] = sum(counts[keyword] for keyword in keywords)

    category, score = max(scores.items(), key=lambda item: item[1])
    if score <= 0:
        # Last-resort heuristic: dominant media type hints at content category
        if media_type_counts.get("reel", 0) + media_type_counts.get("video", 0) > len(posts) // 2:
            logger.warning(
                "[NicheDiscovery] Keyword score=0; guessing Lifestyle from reel-heavy account (username=%s)",
                username,
            )
            return CreatorNiche(primary_category="Lifestyle", sub_niches=["video", "reels"], confidence_score=0.2)
        logger.warning(
            "[NicheDiscovery] Keyword score=0; returning General (username=%s, post_count=%d)",
            username,
            len(posts),
        )
        return CreatorNiche(primary_category="General", sub_niches=[], confidence_score=0.1)

    matched_keywords = [
        keyword
        for keyword, _count in counts.most_common()
        if keyword in _NICHE_KEYWORDS[category]
    ][:5]
    total_keyword_hits = sum(scores.values())
    confidence = min(0.85, max(0.35, score / max(total_keyword_hits, 1)))
    return CreatorNiche(
        primary_category=category,
        sub_niches=matched_keywords,
        confidence_score=round(confidence, 2),
    )


async def discover_creator_niche(
    posts: List[SinglePostInsights],
    bio: str | None,
    username: str | None,
) -> CreatorNiche:
    """Infer a creator's niche using an LLM and return a `CreatorNiche`.

    The function:
    - builds a strict system prompt instructing the LLM to act as a Senior
      Creator Analyst and to output ONLY TOON that matches the
      `CreatorNiche` schema.
    - extracts recent captions/themes from `posts` to form the user payload.
    - calls `LLMClient.generate` in a thread via `asyncio.to_thread` and
      parses the TOON response with `toon.loads`.
    - validates and returns a `CreatorNiche` instance. On error returns a
      conservative fallback `CreatorNiche(primary_category="General", sub_niches=[], confidence_score=0.1)`.

    Args:
        posts: List of recent `SinglePostInsights` to extract captions/themes from.
        bio: Creator bio text, may be None.
        username: Creator username, may be None.

    Returns:
        A validated `CreatorNiche` object.
    """

    system_prompt = (
        "You are a Senior Creator Analyst. Classify the creator into a single "
        "primary category and a short list of sub-niches using the standard taxonomy. "
        "Return ONLY valid TOON format (Token-Oriented Object Notation, "
        "YAML-like indentation, no braces, no quotes). Use 2-space indentation "
        "for nesting and '-' for list items. Do not include markdown, "
        "commentary, or extra keys. Output exactly the fields: primary_category, "
        "sub_niches, confidence_score. "
        "- `primary_category`: a short high-level label (string).\n"
        "- `sub_niches`: a list of short strings describing focused themes.\n"
        "- `confidence_score`: a float between 0.0 and 1.0 representing confidence."
    )

    # Build user payload from bio, username, and recent post captions/themes.
    captions: list[str] = []
    for p in posts[:12]:
        try:
            text = (p.caption_text or "").strip()
        except Exception:
            text = ""
        if text:
            captions.append(text.replace("\n", " ").strip())

    user_parts: list[str] = []
    if username:
        user_parts.append(f"username: {username}")
    if bio:
        user_parts.append(f"bio: {bio.strip()}")
    if captions:
        sample_captions = "\n".join(captions[:10])
        user_parts.append("recent_captions:\n" + sample_captions)
    else:
        user_parts.append("recent_captions: []")

    user_payload = "\n\n".join(user_parts)

    prompt = {"system": system_prompt, "user": user_payload}

    llm = LLMClient(temperature=0.1, max_tokens=300)

    try:
        raw_response = await asyncio.to_thread(llm.generate, prompt)
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise ValueError("Empty LLM response")

        parsed = toon_loads(raw_response)
        if not isinstance(parsed, dict):
            raise ValueError("TOON did not parse to a dict")

        # Fix sub_niches: LLM sometimes returns comma-separated string instead of list
        sub_niches = parsed.get("sub_niches")
        if isinstance(sub_niches, str):
            parsed["sub_niches"] = [s.strip() for s in sub_niches.split(",") if s.strip()]
        elif not isinstance(sub_niches, list):
            parsed["sub_niches"] = []

        # Safely validate/massage into CreatorNiche using Pydantic.
        try:
            # Prefer pydantic v2-style model validation if available
            niche = CreatorNiche.model_validate(parsed)  # type: ignore[attr-defined]
        except Exception:
            # Fallback to direct construction for pydantic v1 compatibility
            niche = CreatorNiche(**parsed)

        return niche

    except Exception as e:  # broad to catch LLM, parsing, and validation errors
        logger.exception("niche_discovery failed: %s", e)
        return _fallback_creator_niche(posts, bio, username)
