from __future__ import annotations

"""Generate trend recommendations for a creator using an LLM.

Exposes `generate_trend_recommendations` which instructs an LLM acting as a
Creative Director to produce three highly actionable `TrendRecommendation`
objects in TOON format. The function cross-references the provided
`CreatorIntelligence` with the list of `GlobalTrend` objects and ensures each
recommendation includes a clear rationale explaining why the trend fits the creator.
"""

import asyncio
from typing import List

from backend.app.ai.llm_client import LLMClient
from backend.app.ai.toon import loads as toon_loads
from backend.app.domain.account_models import CreatorIntelligence
from backend.app.domain.trend_models import GlobalTrend, TrendRecommendation
from backend.app.utils.logger import logger


async def generate_trend_recommendations(
    creator_intelligence: CreatorIntelligence,
    trends: List[GlobalTrend],
) -> List[TrendRecommendation]:
    """Generate 3 actionable `TrendRecommendation` objects tailored to the creator.

    The LLM is prompted to act as a Creative Director, cross-referencing
    `creator_intelligence.creator_strengths` and `content_style_summary` with
    the supplied `trends`. The model must output exactly three recommendations
    in TOON format. Each recommendation must include `suggested_title`,
    `rationale`, `expected_impact`, and optional `trend_reference`.

    On any error the function logs and returns an empty list.
    """

    system_prompt = (
        "You are a Creative Director for short-form social video. Using the provided "
        "creator intelligence, produce exactly 3 highly actionable TrendRecommendation "
        "objects tailored to the creator. Each object must include: suggested_title, "
        "rationale, expected_impact, and trend_reference (optional). The rationale "
        "MUST explain WHY this trend fits the creator by referencing creator strengths "
        "and content style. Return ONLY valid TOON format (Token-Oriented "
        "Object Notation, YAML-like indentation, no braces, no quotes). "
        "Use 2-space indentation for nesting and '-' for list items. "
        "Do not include markdown, commentary, or extra keys.\n\n"
        "OUTPUT EXAMPLE (STRICT TOON ONLY):\n"
        "recommendations\n"
        "  -\n"
        "    suggested_title: The aesthetic morning routine\n"
        "    rationale: Visuals match your style\n"
        "    expected_impact: High engagement\n"
        "    trend_reference: Morning Vlog"
    )

    # Build user payload summarizing creator intelligence and trends
    strengths_text = "\n".join(f"- {s}" for s in (creator_intelligence.creator_strengths or []))
    style_summary = creator_intelligence.content_style_summary or ""

    trends_text_lines: list[str] = []
    for t in trends[:8]:
        trends_text_lines.append(f"- {t.topic_name} | type={t.trend_type} | momentum={t.momentum}")
    trends_text = "\n".join(trends_text_lines) or "- None"

    user_payload = (
        f"creator_strengths:\n{strengths_text or '- None'}\n\n"
        f"content_style_summary:\n{style_summary}\n\n"
        f"candidate_trends:\n{trends_text}\n\n"
        "instruction: Produce exactly 3 actionable recommendations as a TOON list."
    )

    prompt = {"system": system_prompt, "user": user_payload}

    llm = LLMClient(temperature=0.7, max_tokens=600)

    try:
        raw = await asyncio.to_thread(llm.generate, prompt)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Empty LLM response")

        text = raw.strip()
        # The LLM natively outputs `recommendations:` due to the example.
        if text.startswith("-"):
            wrapped = "recommendations:\n" + "\n".join("  " + line for line in text.splitlines())
            parsed = toon_loads(wrapped)
            recs_raw = parsed.get("recommendations", []) if isinstance(parsed, dict) else []
        else:
            parsed = toon_loads(text)
            # Find first list inside parsed dict
            recs_raw = None
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        recs_raw = v
                        break
            if recs_raw is None:
                # If parsed directly to a single object, wrap it
                recs_raw = [parsed] if isinstance(parsed, dict) else []

        results: List[TrendRecommendation] = []
        for item in recs_raw:
            if not isinstance(item, dict):
                continue
            try:
                try:
                    rec = TrendRecommendation.model_validate(item)  # type: ignore[attr-defined]
                except Exception:
                    rec = TrendRecommendation(**item)
                results.append(rec)
            except Exception as e:
                logger.warning("Skipping invalid recommendation item: %s", e)

        # Return only up to 3 recommendations (spec requires 3)
        return results[:3]

    except Exception as e:
        logger.exception("generate_trend_recommendations failed: %s", e)
        return []
