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

from backend.app.analytics.trend_signals_fetcher import fetch_live_trend_signals
from backend.app.ai.llm_client import LLMClient
from backend.app.ai.toon_helpers import toon_parse_list
from backend.app.domain.trend_models import CreatorNiche, GlobalTrend
from backend.app.utils.logger import logger


# ── Normalisation helpers ─────────────────────────────────────────────────────

_TREND_TYPE_MAP: dict[str, str] = {
    "topic": "topic", "topical": "topic", "topical meme": "topic",
    "subject": "topic", "content topic": "topic",
    "format": "format", "video format": "format", "content format": "format", "style": "format",
    "audio": "audio", "sound": "audio", "music": "audio", "trending audio": "audio",
    "hashtag": "hashtag", "challenge": "hashtag", "tag": "hashtag", "trend tag": "hashtag",
}

_MOMENTUM_MAP: dict[str, str] = {
    "rising": "rising", "growing": "rising", "gaining": "rising", "emerging": "rising",
    "peaking": "peaking", "peaked": "peaking", "peak": "peaking", "at peak": "peaking",
    "falling": "falling", "declining": "falling", "fading": "falling", "dropping": "falling",
}


def _normalise_trend_type(raw: str) -> str:
    clean = raw.lower().strip()
    if clean in _TREND_TYPE_MAP:
        return _TREND_TYPE_MAP[clean]
    for key, value in _TREND_TYPE_MAP.items():
        if key in clean or clean in key:
            return value
    return "topic"  # safe default


def _normalise_momentum(raw: str) -> str:
    clean = raw.lower().strip()
    if clean in _MOMENTUM_MAP:
        return _MOMENTUM_MAP[clean]
    for key, value in _MOMENTUM_MAP.items():
        if key in clean:
            return value
    return "rising"  # safe default


async def fetch_global_trends(niche: CreatorNiche) -> List[GlobalTrend]:
    """Return 3-5 hyper-current, rising `GlobalTrend` objects tailored to `niche`.

    The LLM is instructed to output ONLY TOON where the root is a list of
    objects matching the `GlobalTrend` schema (fields: topic_name, trend_type,
    momentum, description, example_reference).

    On failure the function logs the error and returns no trends. Callers can
    surface a degraded state without presenting fabricated trend data.
    """

    system_prompt = (
        "You are a viral trend spotter. Identify 3 to 5 hyper-current, rising trends "
        "specifically tailored to the provided creator niche. "
        "Return ONLY valid TOON format (Token-Oriented "
        "Object Notation, YAML-like indentation, no braces, no quotes). "
        "Use 2-space indentation for nesting and '-' for list items. "
        "Do not include markdown, commentary, or extra keys.\n\n"
        "IMPORTANT: trend_type MUST be exactly one of: topic, format, audio, hashtag\n"
        "  topic   = subject-matter trends (e.g. mental health, AI tools)\n"
        "  format  = video structure trends (e.g. POV, day-in-life, talking head)\n"
        "  audio   = sound/music trends (e.g. trending audio, voiceover styles)\n"
        "  hashtag = hashtag/challenge-driven trends (e.g. #75hard, #GlowUp)\n\n"
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

                # Parse TOON response using shared helper
        trends_raw = toon_parse_list(raw, root_key="trends", model_cls=GlobalTrend)

        # Normalise trend_type and momentum for each parsed item
        results: list[GlobalTrend] = []
        for trend in trends_raw:
            trend.trend_type = _normalise_trend_type(trend.trend_type)
            trend.momentum = _normalise_momentum(trend.momentum)
            results.append(trend)

        if not results:
            raise ValueError("No valid trends parsed from LLM output")

        return results

    except Exception as e:
        logger.exception("fetch_global_trends failed: %s", e)
        return []
