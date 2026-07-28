"""Caption generation service for content suggestions."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from backend.app.ai.llm_client import LLMClient
from backend.app.domain.content_suggestion_models import GeneratedCaption, GenerateCaptionResponse
from backend.app.utils.logger import logger


async def generate_caption(
    idea_id: str,
    title: str,
    hook: str | None,
    script_summary: str | None,
    platforms: list[str],
    tone: str,
    language: str,
    include_hashtags: bool,
    max_hashtags: int,
) -> GenerateCaptionResponse:
    """Generate captions for an idea.

    Args:
        idea_id: The idea ID for lineage tracking
        title: The idea title
        hook: Optional hook text
        script_summary: Optional script summary for context
        platforms: List of platforms to generate captions for
        tone: friendly | professional | funny
        language: Language code
        include_hashtags: Whether to include hashtags
        max_hashtags: Maximum number of hashtags

    Returns:
        GenerateCaptionResponse with platform-specific captions
    """
    logger.info("[CaptionGenerator] Generating captions for idea=%s platforms=%s", idea_id, platforms)

    captions = []
    for platform in platforms:
        caption = await _generate_for_platform(
            idea_id=idea_id,
            title=title,
            hook=hook,
            script_summary=script_summary,
            platform=platform,
            tone=tone,
            language=language,
            include_hashtags=include_hashtags,
            max_hashtags=max_hashtags,
        )
        captions.append(caption)

    return GenerateCaptionResponse(idea_id=idea_id, captions=captions)


async def _generate_for_platform(
    idea_id: str,
    title: str,
    hook: str | None,
    script_summary: str | None,
    platform: str,
    tone: str,
    language: str,
    include_hashtags: bool,
    max_hashtags: int,
) -> GeneratedCaption:
    """Generate caption for a specific platform."""
    system_prompt = (
        f"You are an expert social media copywriter specializing in {platform} content. "
        "Create engaging captions that drive interaction. "
        "Return ONLY one valid JSON object and no markdown."
    )

    context = f"Title: {title}"
    if hook:
        context += f"\nHook: {hook}"
    if script_summary:
        context += f"\nScript summary: {script_summary[:200]}"

    user_prompt = f"""{context}

Platform: {platform}
Tone: {tone}
Language: {language}
Include hashtags: {include_hashtags}
Max hashtags: {max_hashtags}

Create an engaging caption with:
- caption_text: The main caption
- hashtags: List of relevant hashtags (without #)
- tips_applied: List of writing tips used

Return JSON shape:
{{
  "caption_text": "Your caption here",
  "hashtags": ["hashtag1", "hashtag2", "hashtag3"],
  "tips_applied": ["Open with a strong hook", "Add question to increase engagement"]
}}
"""

    try:
        llm = LLMClient(temperature=0.7, max_tokens=800)
        raw = await asyncio.to_thread(
            llm.generate,
            {"system": system_prompt, "user": user_prompt, "response_format": {"type": "json_object"}},
        )

        if not raw or not raw.strip():
            raise ValueError("Empty LLM response")

        parsed = _parse_json_caption(raw)

        caption_text = parsed.get("caption_text", "")
        hashtags = parsed.get("hashtags", [])[:max_hashtags]
        tips = parsed.get("tips_applied", [])

        # Add hashtags to caption if requested
        if include_hashtags and hashtags:
            hashtag_str = " ".join(f"#{tag}" for tag in hashtags)
            caption_text = f"{caption_text}\n\n{hashtag_str}"

        return GeneratedCaption(
            platform=platform,
            caption_text=caption_text,
            hashtags=hashtags,
            character_count=len(caption_text),
            hashtag_count=len(hashtags),
            tips_applied=tips,
        )

    except Exception as e:
        logger.exception("[CaptionGenerator] Failed for platform=%s: %s", platform, e)
        return _fallback_caption(idea_id, title, platform, include_hashtags, max_hashtags)


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) > 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_json_caption(raw: str) -> dict[str, Any]:
    """Parse JSON caption response."""
    stripped = _strip_markdown_fences(raw)
    if "{" in stripped and "}" in stripped:
        stripped = stripped[stripped.find("{"):stripped.rfind("}") + 1]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("Caption response must be a JSON object")
    payload.setdefault("caption_text", "")
    payload.setdefault("hashtags", [])
    payload.setdefault("tips_applied", [])
    return payload


def _fallback_caption(
    idea_id: str,
    title: str,
    platform: str,
    include_hashtags: bool,
    max_hashtags: int,
) -> GeneratedCaption:
    """Return a fallback caption when LLM fails."""
    caption_text = f"Check out this {title.lower()}! What do you think? 👇"
    hashtags = ["contentcreator", "socialmedia", "trending"]

    if include_hashtags:
        hashtag_str = " ".join(f"#{tag}" for tag in hashtags[:max_hashtags])
        caption_text = f"{caption_text}\n\n{hashtag_str}"

    return GeneratedCaption(
        platform=platform,
        caption_text=caption_text,
        hashtags=hashtags[:max_hashtags],
        character_count=len(caption_text),
        hashtag_count=min(len(hashtags), max_hashtags),
        tips_applied=["Ask a question to increase engagement"],
    )
