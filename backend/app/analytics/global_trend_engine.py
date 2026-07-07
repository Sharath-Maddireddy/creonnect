from __future__ import annotations

"""Engine to fetch global trends for a given creator niche using an LLM.

Exports:
    - fetch_global_trends(niche) -> list[GlobalTrend]

The function uses a strict system prompt instructing the LLM to act as a
viral trend spotter and to return only TOON text representing a list of
`GlobalTrend` objects. Before calling the LLM, live trend signals are fetched
and injected into the prompt payload as grounding context. Results are parsed
with the project's `toon` parser and validated into Pydantic `GlobalTrend`
models. On any error a safe fallback list is returned to keep the pipeline
resilient.
"""

import asyncio
from typing import List

from backend.app.analytics.trend_signals_fetcher import fetch_live_trend_signals
from backend.app.ai.llm_client import LLMClient
from backend.app.ai.toon import loads as toon_loads
from backend.app.domain.trend_models import CreatorNiche, GlobalTrend
from backend.app.utils.logger import logger


async def fetch_global_trends(niche: CreatorNiche) -> List[GlobalTrend]:
    """Return 3-5 hyper-current, rising `GlobalTrend` objects tailored to `niche`.

    The LLM is instructed to output ONLY TOON where the root is a list of
    objects matching the `GlobalTrend` schema (fields: topic_name, trend_type,
    momentum, description, example_reference).

    On failure the function logs the error and returns a conservative
    fallback list containing a single generic `GlobalTrend` named
    "Evergreen Content".
    """

    system_prompt = (
        "You are a viral trend spotter. Identify 3 to 5 hyper-current, rising trends "
        "(formats, audio cues, topical memes, or hashtags) specifically tailored to the "
        "provided creator niche. Return ONLY valid TOON format (Token-Oriented "
        "Object Notation, YAML-like indentation, no braces, no quotes). "
        "Use 2-space indentation for nesting and '-' for list items. "
        "Do not include markdown, commentary, or extra keys.\n\n"
        "OUTPUT EXAMPLE (STRICT TOON ONLY):\n"
        "trends\n"
        "  -\n"
        "    topic_name: High visual vlogs\n"
        "    trend_type: format\n"
        "    momentum: rising\n"
        "    description: Quick cuts of high quality visuals.")

    # Build a compact user payload describing the niche
    sub_niches_text = "\n".join(f"- {s}" for s in (niche.sub_niches or []))
    live_signals = await fetch_live_trend_signals(
        primary_category=niche.primary_category,
        sub_niches=niche.sub_niches,
    )
    live_signals_text = (
        "\n".join(f"- {signal}" for signal in live_signals)
        if live_signals
        else "none available"
    )
    user_payload = (
        f"primary_category: {niche.primary_category}\n"
        f"sub_niches:\n{sub_niches_text if sub_niches_text else '[]'}\n"
        f"live_trend_signals:\n{live_signals_text}\n"
        "instruction: Using the live_trend_signals as your primary evidence, "
        "identify 3-5 rising trends tailored to the above niche. If "
        "live_trend_signals is empty, use your best knowledge of the niche."
    )

    prompt = {"system": system_prompt, "user": user_payload}

    llm = LLMClient(temperature=0.4, max_tokens=800)

    try:
        raw = await asyncio.to_thread(llm.generate, prompt)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Empty LLM response")

        # The project's TOON parser expects a dict root. If LLM returned a
        # top-level list (lines starting with '-'), wrap it under a `trends`
        # key so toon.loads can parse it into a dict that contains the list.
        text = raw.strip()
        if text.startswith("-"):
            wrapped = "trends\n" + "\n".join("  " + line for line in text.splitlines())
            parsed = toon_loads(wrapped)
            trends_raw = parsed.get("trends", []) if isinstance(parsed, dict) else []
        else:
            parsed = toon_loads(text)
            # Locate the first list value in the parsed dict to treat as trends
            if isinstance(parsed, dict):
                trends_raw = None
                for v in parsed.values():
                    if isinstance(v, list):
                        trends_raw = v
                        break
                if trends_raw is None:
                    # If the parsed dict itself represents a single object,
                    # attempt to coerce into a single-element list
                    trends_raw = [parsed]
            else:
                trends_raw = []

        results: List[GlobalTrend] = []
        for item in trends_raw:
            if not isinstance(item, dict):
                continue
            try:
                try:
                    trend = GlobalTrend.model_validate(item)  # type: ignore[attr-defined]
                except Exception:
                    trend = GlobalTrend(**item)
                results.append(trend)
            except Exception as e:
                logger.warning("Skipping invalid trend item: %s", e)

        if not results:
            raise ValueError("No valid trends parsed from LLM output")

        return results

    except Exception as e:
        logger.exception("fetch_global_trends failed: %s", e)
        # Fallback: single generic evergreen trend to keep pipeline moving
        fallback = GlobalTrend(
            topic_name="Evergreen Content",
            trend_type="topic",
            momentum="rising",
            description=(
                "A reliable evergreen topic format that performs consistently across "
                "niches; useful as a safe fallback when fresh trend signals are unavailable."
            ),
            example_reference=None,
        )
        return [fallback]
