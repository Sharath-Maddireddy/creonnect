"""Script generation service for content suggestions."""

from __future__ import annotations

from typing import Any

from backend.app.ai.llm_client import LLMClient
from backend.app.domain.content_suggestion_models import GenerateScriptResponse, Scene
from backend.app.utils.logger import logger


async def generate_script(
    idea_id: str,
    title: str,
    hook: str | None,
    script_type: str,
    tone: str,
    language: str,
    duration_seconds: int,
) -> GenerateScriptResponse:
    """Generate a script for an idea.

    Args:
        idea_id: The idea ID for lineage tracking
        title: The idea title
        hook: Optional existing hook to build on
        script_type: viral | natural | story
        tone: friendly | professional | funny
        language: Language code (en, hi, es, etc.)
        duration_seconds: Target duration in seconds

    Returns:
        GenerateScriptResponse with hook, scenes, CTA, and full script
    """
    logger.info("[ScriptGenerator] Generating script for idea=%s type=%s", idea_id, script_type)

    system_prompt = (
        "You are a professional short-form video scriptwriter. "
        "Create scripts optimized for social media engagement. "
        "Use clear scene breakdowns with timing. "
        "Return ONLY valid TOON format."
    )

    user_prompt = f"""Write a {script_type} script for: {title}

Hook: {hook or 'Create an attention-grabbing hook'}
Tone: {tone}
Language: {language}
Target duration: {duration_seconds} seconds

Structure:
- hook: The opening line (0-3 seconds)
- scenes: List of scenes with scene_number, time_range, description, visual_notes
- cta: Call to action at the end
- estimated_duration_sec: Actual estimated duration

OUTPUT FORMAT (STRICT TOON):
hook: Your opening line here
scenes
  -
    scene_number: 1
    time_range: 0-3s
    description: What happens in this scene
    visual_notes: Visual direction for filming
  -
    scene_number: 2
    time_range: 3-8s
    description: What happens in this scene
    visual_notes: Visual direction
cta: Your call to action
estimated_duration_sec: 30
"""

    try:
        llm = LLMClient(temperature=0.7, max_tokens=1000)
        raw = await llm.generate_async({"system": system_prompt, "user": user_prompt})

        if not raw or not raw.strip():
            raise ValueError("Empty LLM response")

        # Parse TOON response
        parsed = _parse_toon_script(raw)

        scenes = [
            Scene(
                scene_number=s.get("scene_number", i + 1),
                time_range=s.get("time_range", f"{i*5}-{(i+1)*5}s"),
                description=s.get("description", ""),
                visual_notes=s.get("visual_notes"),
            )
            for i, s in enumerate(parsed.get("scenes", []))
        ]

        return GenerateScriptResponse(
            idea_id=idea_id,
            hook=parsed.get("hook", hook or "Watch this!"),
            scenes=scenes,
            cta=parsed.get("cta", "Save this for later!"),
            estimated_duration_sec=parsed.get("estimated_duration_sec", duration_seconds),
            full_script=_format_full_script(parsed),
        )

    except Exception as e:
        logger.exception("[ScriptGenerator] Failed: %s", e)
        # Return fallback script
        return _fallback_script(idea_id, title, hook, duration_seconds)


def _parse_toon_script(raw: str) -> dict[str, Any]:
    """Parse TOON format script response."""
    result = {
        "hook": "",
        "scenes": [],
        "cta": "",
        "estimated_duration_sec": 30,
    }

    lines = raw.strip().split("\n")
    current_scene = None
    scenes = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("hook:"):
            result["hook"] = line[5:].strip()
        elif line.startswith("cta:"):
            result["cta"] = line[4:].strip()
        elif line.startswith("estimated_duration_sec:"):
            try:
                result["estimated_duration_sec"] = int(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("-") and current_scene is None:
            current_scene = {}
        elif line.startswith("scene_number:") and current_scene is not None:
            try:
                current_scene["scene_number"] = int(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("time_range:") and current_scene is not None:
            current_scene["time_range"] = line.split(":", 1)[1].strip()
        elif line.startswith("description:") and current_scene is not None:
            current_scene["description"] = line.split(":", 1)[1].strip()
        elif line.startswith("visual_notes:") and current_scene is not None:
            current_scene["visual_notes"] = line.split(":", 1)[1].strip()
        elif line.startswith("-") and current_scene is not None:
            scenes.append(current_scene)
            current_scene = {}

    if current_scene:
        scenes.append(current_scene)

    result["scenes"] = scenes
    return result


def _format_full_script(parsed: dict[str, Any]) -> str:
    """Format parsed script into readable text."""
    lines = [f"Hook: {parsed.get('hook', '')}", ""]

    for scene in parsed.get("scenes", []):
        lines.append(f"Scene {scene.get('scene_number', '?')} ({scene.get('time_range', '?')}):")
        lines.append(f"  {scene.get('description', '')}")
        if scene.get("visual_notes"):
            lines.append(f"  Visual: {scene['visual_notes']}")
        lines.append("")

    lines.append(f"CTA: {parsed.get('cta', '')}")
    return "\n".join(lines)


def _fallback_script(
    idea_id: str,
    title: str,
    hook: str | None,
    duration_seconds: int,
) -> GenerateScriptResponse:
    """Return a fallback script when LLM fails."""
    return GenerateScriptResponse(
        idea_id=idea_id,
        hook=hook or f"Watch how I {title.lower()}",
        scenes=[
            Scene(scene_number=1, time_range="0-3s", description="Hook - grab attention", visual_notes="Close-up shot"),
            Scene(scene_number=2, time_range="3-15s", description="Main content", visual_notes="Show the process"),
            Scene(scene_number=3, time_range="15-25s", description="Details and tips", visual_notes="B-roll footage"),
            Scene(scene_number=4, time_range="25-30s", description="CTA and wrap up", visual_notes="Direct to camera"),
        ],
        cta="Save this for later!",
        estimated_duration_sec=min(duration_seconds, 30),
        full_script="Hook: Watch this!\n\nScene 1 (0-3s): Hook - grab attention\nScene 2 (3-15s): Main content\nScene 3 (15-25s): Details and tips\nScene 4 (25-30s): CTA and wrap up\n\nCTA: Save this for later!",
    )
