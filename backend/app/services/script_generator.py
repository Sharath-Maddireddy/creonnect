"""Script generation service for content suggestions."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from backend.app.ai.llm_client import LLMClient
from backend.app.domain.content_suggestion_models import GenerateScriptResponse, Scene
from backend.app.utils.logger import logger


async def generate_script(
    idea_id: str,
    title: str,
    hook: str | None,
    script_type: str,
    content_type: str,
    tone: str,
    language: str,
    duration_seconds: int,
) -> GenerateScriptResponse:
    """Generate a script for an idea.

    Args:
        idea_id: The idea ID for lineage tracking
        title: The idea title
        hook: Optional existing hook to build on
        script_type: The selected format-specific creative approach
        content_type: reel | carousel | photo
        tone: friendly | professional | funny
        language: Language code (en, hi, es, etc.)
        duration_seconds: Target duration in seconds

    Returns:
        GenerateScriptResponse with hook, scenes, CTA, and full script
    """
    normalized_content_type = (content_type or "reel").strip().lower()
    if normalized_content_type not in {"reel", "carousel", "photo"}:
        normalized_content_type = "reel"
    logger.info("[ScriptGenerator] Generating plan for idea=%s type=%s format=%s", idea_id, script_type, normalized_content_type)

    format_guidance = {
        "reel": "Create a short-form video script with timed scenes, spoken narration, and visual notes.",
        "carousel": "Create an Instagram carousel plan. Each scene is one slide: use time_range as 'Slide N', description as the exact slide copy, and visual_notes as the layout or image direction. Do not write voiceover.",
        "photo": "Create a single-photo post creative brief. Use one scene only: description is the on-image text or headline, and visual_notes gives the composition, subject, lighting, crop, and prop direction. Do not write voiceover or multiple shots.",
    }[normalized_content_type]

    system_prompt = (
        "You are a professional social media creative director. "
        "Create production-ready content plans optimized for engagement. "
        f"{format_guidance} "
        "Return ONLY one valid JSON object and no markdown."
    )

    user_prompt = f"""Create a {script_type} {normalized_content_type} plan for: {title}

Hook: {hook or 'Create an attention-grabbing hook'}
Tone: {tone}
Language: {language}
Target duration: {duration_seconds} seconds (only relevant for reels)

Structure:
- hook: The opening hook, headline, or first-slide text
- scenes: Format-specific production steps with scene_number, time_range, description, visual_notes
- cta: Call to action at the end
- estimated_duration_sec: Actual estimated duration

Important quality rules:
- for reels, description must be actual creator dialogue or voiceover, not labels like "Main content"
- for carousels, description must be concise, ready-to-paste slide copy
- for photos, description must be concise on-image text and visual_notes must be a complete creative brief
- make the plan specific and ready to produce
- do not repeat the same sentence in every scene
- keep the language aligned to the requested tone

Return JSON shape:
{{
  "hook": "Your opening line here",
  "scenes": [
    {{
      "scene_number": 1,
      "time_range": "0-3s",
      "description": "Exact spoken line for this scene",
      "visual_notes": "Visual direction for filming"
    }}
  ],
  "cta": "Your call to action",
  "estimated_duration_sec": 30
}}
"""

    try:
        llm = LLMClient(temperature=0.7, max_tokens=1000)
        raw = await asyncio.to_thread(
            llm.generate,
            {"system": system_prompt, "user": user_prompt, "response_format": {"type": "json_object"}},
        )

        if not raw or not raw.strip():
            raise ValueError("Empty LLM response")

        # Parse TOON response
        parsed = _parse_json_script(raw)

        parsed_scenes = _ensure_scene_copy(
            parsed.get("scenes", []),
            title=title,
            hook=parsed.get("hook", hook or ""),
        )

        scenes = [
            Scene(
                scene_number=s.get("scene_number", i + 1),
                time_range=s.get("time_range", f"{i*5}-{(i+1)*5}s"),
                description=s.get("description", ""),
                visual_notes=s.get("visual_notes"),
            )
            for i, s in enumerate(parsed_scenes)
        ]

        return GenerateScriptResponse(
            idea_id=idea_id,
            hook=parsed.get("hook", hook or "Watch this!"),
            scenes=scenes,
            cta=parsed.get("cta", "Save this for later!"),
            estimated_duration_sec=parsed.get("estimated_duration_sec", duration_seconds),
            full_script=_format_full_script(
                {
                    **parsed,
                    "scenes": parsed_scenes,
                }
            ),
        )

    except Exception as e:
        logger.exception("[ScriptGenerator] Failed: %s", e)
        # Return fallback script
        return _fallback_script(idea_id, title, hook, duration_seconds, normalized_content_type)


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) > 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_json_script(raw: str) -> dict[str, Any]:
    """Parse JSON script response."""
    stripped = _strip_markdown_fences(raw)
    if "{" in stripped and "}" in stripped:
        stripped = stripped[stripped.find("{"):stripped.rfind("}") + 1]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("Script response must be a JSON object")
    payload.setdefault("hook", "")
    payload.setdefault("scenes", [])
    payload.setdefault("cta", "")
    payload.setdefault("estimated_duration_sec", 30)
    return payload


def _ensure_scene_copy(
    scenes: list[dict[str, Any]],
    *,
    title: str,
    hook: str,
) -> list[dict[str, Any]]:
    """Replace placeholder scene labels with actual spoken copy when needed."""
    repaired: list[dict[str, Any]] = []
    normalized_title = title.strip()
    base_hook = hook.strip() or f"Here is why {normalized_title.lower()} works."

    fallback_lines = [
        base_hook,
        f"Here is what makes {normalized_title.lower()} stand out, and why people keep stopping to watch it.",
        "Show one specific takeaway your audience can try today, so the idea feels practical instead of vague.",
        "Wrap by telling viewers exactly what to save, copy, or comment if they want more ideas like this.",
    ]

    for index, scene in enumerate(scenes):
        description = (scene.get("description") or "").strip()
        generic = _is_generic_scene_label(description)
        repaired_scene = dict(scene)
        if generic:
            fallback_idx = min(index, len(fallback_lines) - 1)
            repaired_scene["description"] = fallback_lines[fallback_idx]
        repaired.append(repaired_scene)

    return repaired


def _is_generic_scene_label(text: str) -> bool:
    """Detect placeholder scene labels that are not real spoken copy."""
    normalized = (text or "").strip().lower()
    generic_labels = {
        "",
        "main content",
        "details and tips",
        "cta and wrap up",
        "hook - grab attention",
        "explain the trend",
        "show the process",
        "close with cta",
    }
    if normalized in generic_labels:
        return True
    short_prefixes = ("scene ", "step ", "point ")
    if normalized.startswith(short_prefixes) and len(normalized.split()) <= 4:
        return True
    return False


def _format_full_script(parsed: dict[str, Any]) -> str:
    """Format parsed script into a user-facing recording script."""
    hook = (parsed.get("hook") or "").strip()
    cta = (parsed.get("cta") or "").strip()
    lines = []

    if hook:
        lines.append(f"Hook: {hook}")
        lines.append("")

    for scene in parsed.get("scenes", []):
        spoken_line = _clean_spoken_line(scene.get("description", ""))
        time_range = scene.get("time_range", "?")
        lines.append(f"Scene {scene.get('scene_number', '?')} ({time_range})")
        if spoken_line:
            lines.append(spoken_line)
        if scene.get("visual_notes"):
            lines.append(f"Visual: {scene['visual_notes']}")
        lines.append("")

    if cta:
        lines.append(f"CTA: {cta}")
    return "\n".join(lines)


def _clean_spoken_line(text: str) -> str:
    """Normalize a spoken line for the full-script block."""
    line = (text or "").strip()
    if not line:
        return ""
    replacements = {
        "Hook - ": "",
        "Hook: ": "",
        "Main content: ": "",
        "Main content - ": "",
        "Details and tips: ": "",
        "Details and tips - ": "",
        "CTA and wrap up: ": "",
        "CTA and wrap up - ": "",
    }
    for old, new in replacements.items():
        if line.startswith(old):
            line = f"{new}{line[len(old):]}".strip()
    return line


def _fallback_script(
    idea_id: str,
    title: str,
    hook: str | None,
    duration_seconds: int,
    content_type: str = "reel",
) -> GenerateScriptResponse:
    """Return a fallback script when LLM fails."""
    base_hook = (hook or f"Watch how I {title.lower()}").strip()
    if content_type == "carousel":
        slides = [
            Scene(scene_number=1, time_range="Slide 1", description=base_hook, visual_notes="Bold cover headline with a simple visual that previews the payoff."),
            Scene(scene_number=2, time_range="Slide 2", description=f"The problem behind {title.lower()}.", visual_notes="Use a clean supporting photo or an easy-to-scan comparison."),
            Scene(scene_number=3, time_range="Slide 3", description="The practical takeaway your audience can use today.", visual_notes="Use a numbered tip, checklist, or before-and-after layout."),
            Scene(scene_number=4, time_range="Slide 4", description="Save this for your next post plan.", visual_notes="Close with a branded CTA slide and generous whitespace."),
        ]
        return GenerateScriptResponse(idea_id=idea_id, hook=base_hook, scenes=slides, cta="Save this carousel for later.", estimated_duration_sec=0, full_script=_format_full_script({"hook": base_hook, "scenes": [slide.model_dump() for slide in slides], "cta": "Save this carousel for later."}))
    if content_type == "photo":
        photo_scene = Scene(scene_number=1, time_range="Single photo", description=base_hook, visual_notes=f"Hero image for {title}: use one clear subject, natural directional light, an uncluttered background, and crop for a 4:5 Instagram feed post.")
        return GenerateScriptResponse(idea_id=idea_id, hook=base_hook, scenes=[photo_scene], cta="Use the caption to invite comments or saves.", estimated_duration_sec=0, full_script=_format_full_script({"hook": base_hook, "scenes": [photo_scene.model_dump()], "cta": "Use the caption to invite comments or saves."}))
    scene_2 = f"Here is exactly why {title.lower()} is getting so much attention right now."
    scene_3 = "The trick is to show one clear takeaway, one proof point, and one thing your audience can copy today."
    scene_4 = "If you want more ideas like this, save this and come back when you plan your next post."

    return GenerateScriptResponse(
        idea_id=idea_id,
        hook=base_hook,
        scenes=[
            Scene(scene_number=1, time_range="0-3s", description=base_hook, visual_notes="Open with a confident close-up and bold text on screen."),
            Scene(scene_number=2, time_range="3-15s", description=scene_2, visual_notes="Cut to examples, screenshots, or a quick demo that proves the point."),
            Scene(scene_number=3, time_range="15-25s", description=scene_3, visual_notes="Layer in B-roll, step-by-step visuals, or product details that support the message."),
            Scene(scene_number=4, time_range="25-30s", description=scene_4, visual_notes="Return to direct-to-camera delivery for the closing call to action."),
        ],
        cta="Save this for later!",
        estimated_duration_sec=min(duration_seconds, 30),
        full_script=_format_full_script(
            {
                "hook": base_hook,
                "scenes": [
                    {"scene_number": 1, "time_range": "0-3s", "description": base_hook, "visual_notes": "Open with a confident close-up and bold text on screen."},
                    {"scene_number": 2, "time_range": "3-15s", "description": scene_2, "visual_notes": "Cut to examples, screenshots, or a quick demo that proves the point."},
                    {"scene_number": 3, "time_range": "15-25s", "description": scene_3, "visual_notes": "Layer in B-roll, step-by-step visuals, or product details that support the message."},
                    {"scene_number": 4, "time_range": "25-30s", "description": scene_4, "visual_notes": "Return to direct-to-camera delivery for the closing call to action."},
                ],
                "cta": "Save this for later!",
            }
        ),
    )
