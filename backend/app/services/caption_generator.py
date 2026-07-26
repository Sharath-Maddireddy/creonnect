"""Caption generation service for content suggestions."""

from __future__ import annotations

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
        "Return ONLY valid TOON format."
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

OUTPUT FORMAT (STRICT TOON):
caption_text: Your caption here
hashtags
  - hashtag1
  - hashtag2
  - hashtag3
tips_applied
  - Open with a strong hook
  - Add question to increase engagement
"""

    try:
        llm = LLMClient(temperature=0.7, max_tokens=800)
        raw = await llm.generate_async({"system": system_prompt, "user": user_prompt})

        if not raw or not raw.strip():
            raise ValueError("Empty LLM response")

        parsed = _parse_toon_caption(raw)

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


def _parse_toon_caption(raw: str) -> dict[str, Any]:
    """Parse TOON format caption response."""
    result = {
        "caption_text": "",
        "hashtags": [],
        "tips_applied": [],
    }

    lines = raw.strip().split("\n")
    current_section = None
    hashtags = []
    tips = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("caption_text:"):
            result["caption_text"] = line.split(":", 1)[1].strip()
            current_section = None
        elif line.startswith("hashtags"):
            current_section = "hashtags"
        elif line.startswith("tips_applied"):
            current_section = "tips"
        elif line.startswith("-") and current_section == "hashtags":
            hashtags.append(line[1:].strip())
        elif line.startswith("-") and current_section == "tips":
            tips.append(line[1:].strip())
        elif current_section is None and not line.startswith(("caption_text:", "hashtags", "tips_applied")):
            # Continuation of caption text
            if result["caption_text"]:
                result["caption_text"] += " " + line
            else:
                result["caption_text"] = line

    result["hashtags"] = hashtags
    result["tips_applied"] = tips
    return result


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
