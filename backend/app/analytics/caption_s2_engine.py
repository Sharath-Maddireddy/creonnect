"""Deterministic S2 caption effectiveness scoring."""

from __future__ import annotations

import asyncio
import json
import re

from backend.app.ai.llm_client import LLMClient, LLMClientError
from backend.app.ai.prompts import S2_CAPTION_EVALUATION_PROMPT
from backend.app.domain.post_models import CaptionEffectivenessScore


_HOOK_KEYWORD_RE = re.compile(r"\b(you|your|this|secret|how|why)\b", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"#\S+")
_CTA_RE = re.compile(
    r"\b(comment|share|save|link in bio|dm|follow|click|swipe|watch)\b",
    re.IGNORECASE,
)


def _clamp_0_100(value: int | float) -> int:
    return int(max(0, min(100, round(float(value)))))


def _coerce_int_0_100(value: int | float | str | None) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(max(0.0, min(100.0, round(numeric))))


async def analyze_caption_via_llm(caption_text: str) -> CaptionEffectivenessScore:
    """Analyze S2 caption effectiveness via LLM with deterministic fallback."""
    if not isinstance(caption_text, str) or not caption_text.strip():
        return compute_s2_caption_effectiveness(caption_text)

    prompt = {
        "system": "Return only valid JSON matching the schema requested.",
        "user": S2_CAPTION_EVALUATION_PROMPT.replace("{caption_text}", caption_text),
        "response_format": {"type": "json_object"},
    }

    try:
        raw_text = await asyncio.to_thread(LLMClient().generate, prompt)
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise LLMClientError("LLM returned empty response.")
        payload = json.loads(raw_text)
        if not isinstance(payload, dict):
            raise ValueError("LLM output must be a JSON object.")

        hook_score = _coerce_int_0_100(payload.get("hook_score_0_100"))
        length_score = _coerce_int_0_100(payload.get("length_score_0_100"))
        hashtag_score = _coerce_int_0_100(payload.get("hashtag_score_0_100"))
        cta_score = _coerce_int_0_100(payload.get("cta_score_0_100"))
        s2_raw_0_100 = _coerce_int_0_100(payload.get("s2_raw_0_100"))

        if None in {hook_score, length_score, hashtag_score, cta_score, s2_raw_0_100}:
            raise ValueError("Missing required S2 fields from LLM output.")

        total_0_50 = round(s2_raw_0_100 / 2.0, 1)

        return CaptionEffectivenessScore(
            hook_score_0_100=hook_score,
            length_score_0_100=length_score,
            hashtag_score_0_100=hashtag_score,
            cta_score_0_100=cta_score,
            s2_raw_0_100=s2_raw_0_100,
            total_0_50=total_0_50,
            notes=[],
        )
    except (json.JSONDecodeError, LLMClientError):
        return compute_s2_caption_effectiveness(caption_text)
    except Exception:
        return compute_s2_caption_effectiveness(caption_text)


def compute_s2_caption_effectiveness(caption_text: str | None) -> CaptionEffectivenessScore:
    """Compute S2 using the PDF/TS reference logic on a 0..100 raw scale.

    S2 raw formula:
    S2 = hook*0.30 + length*0.20 + hashtags*0.25 + cta*0.25
    Mapped total_0_50 = s2_raw_0_100 / 2.
    """

    caption = caption_text if isinstance(caption_text, str) else ""
    first_line = caption.split("\n")[0] if caption else ""
    notes: list[str] = []

    # Hook scoring
    first_line_len = len(first_line)
    if 0 < first_line_len <= 125:
        hook_score = 60
        if "?" in first_line or "!" in first_line:
            hook_score += 20
        if _HOOK_KEYWORD_RE.search(first_line):
            hook_score += 20
        hook_score = min(100, hook_score)
    else:
        hook_score = 30

    # Length scoring (excluding hashtags)
    caption_without_hashtags = _HASHTAG_RE.sub("", caption).strip()
    char_count = len(caption_without_hashtags)
    if 138 <= char_count <= 500:
        length_score = 100
    elif 50 <= char_count < 138:
        length_score = 70
    elif char_count > 500:
        length_score = 60
    else:
        length_score = 30

    # Hashtag scoring
    hashtags = _HASHTAG_RE.findall(caption)
    tag_count = len(hashtags)
    if 5 <= tag_count <= 15:
        hashtag_score = 100
    elif 1 <= tag_count < 5:
        hashtag_score = 60
    elif tag_count > 15:
        hashtag_score = 70
    else:
        hashtag_score = 20

    # CTA scoring
    cta_score = 100 if _CTA_RE.search(caption) else 20

    s2_raw_0_100 = round(
        hook_score * 0.30
        + length_score * 0.20
        + hashtag_score * 0.25
        + cta_score * 0.25
    )
    total_0_50 = round(s2_raw_0_100 / 2.0, 1)

    if hook_score == 30:
        notes.append("Weak or missing hook in first line")
    if hashtag_score == 20:
        notes.append("No hashtags detected")
    if cta_score == 20:
        notes.append("No CTA detected")
    if char_count < 50:
        notes.append("Caption too short")

    return CaptionEffectivenessScore(
        hook_score_0_100=_clamp_0_100(hook_score),
        length_score_0_100=_clamp_0_100(length_score),
        hashtag_score_0_100=_clamp_0_100(hashtag_score),
        cta_score_0_100=_clamp_0_100(cta_score),
        s2_raw_0_100=_clamp_0_100(s2_raw_0_100),
        total_0_50=max(0.0, min(50.0, total_0_50)),
        notes=notes,
    )
