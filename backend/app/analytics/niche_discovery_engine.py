from __future__ import annotations

"""Niche discovery engine using an LLM to infer creator niches.

Provides an async `discover_creator_niche` function which constructs a
strict system prompt, builds a user payload from recent posts and profile
metadata, calls the LLM via `LLMClient`, parses TOON output using the
project `toon` parser, and returns a validated `CreatorNiche`.

The function is defensive: on any LLM or parsing error it logs the
failure and returns a conservative fallback `CreatorNiche`.
"""

from typing import List
import asyncio

from backend.app.ai.llm_client import LLMClient
from backend.app.ai.toon import loads as toon_loads
from backend.app.domain.post_models import SinglePostInsights
from backend.app.domain.trend_models import CreatorNiche
from backend.app.utils.logger import logger


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
        # Safe conservative fallback
        return CreatorNiche(primary_category="General", sub_niches=[], confidence_score=0.1)
