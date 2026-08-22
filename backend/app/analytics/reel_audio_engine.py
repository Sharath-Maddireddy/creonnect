"""Deterministic audio scoring for Instagram Reels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_GENERIC_ORIGINAL_AUDIO_LABELS = {
    "originalaudio",
    "originalsound",
    "original",
    "originalaudi0",  # tolerate a common OCR-ish typo seen from some sources
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass
class ReelAudioScore:
    trending_audio_bonus: float = 0.0
    audio_caption_alignment: float = 0.0
    audio_quality_bonus: float = 0.0
    total: float = 0.0
    notes: list[str] = field(default_factory=list)
    audio_available: bool = False


def _is_generic_original_audio_label(normalized_name: str) -> bool:
    collapsed = normalized_name.lower().replace(" ", "").replace("_", "").replace("-", "")
    return collapsed in _GENERIC_ORIGINAL_AUDIO_LABELS


def compute_reel_audio_score(
    audio_name: str | None,
    caption_text: str,
    reel_vision_signals: dict[str, Any] | None = None,
) -> ReelAudioScore:
    """
    Score a Reel's audio dimension.

    Two independent sources, in priority order:

    1. ``audio_name`` -- a real (non-generic) track name is a genuine trend
       signal: trending_audio_bonus=3.0, plus up to 5.0 for caption/audio
       token overlap. A generic label like "Original audio" carries no trend
       information and is treated the same as no name at all -- previously
       it scored identically to a licensed trending track, which rewarded
       every original-audio Reel as if it were riding a trend.

    2. Gemini's own audio analysis of the video (``reel_vision_signals``,
       from ``REEL_VISION_EVALUATION_PROMPT``) -- used only when (1) has no
       real name to work with, since Instagram's read API does not expose
       track names for existing media (``audio_name`` is a publish-time-only
       parameter), so path (1) is unavailable for essentially all
       OAuth-ingested Reels today. ``is_silent`` -> 0 (a real, informative
       zero, not "no signal"). Otherwise ``audio_quality_score`` is the
       base, with small bonuses for a present audio hook and for
       audio/visual sync.

    ``audio_available`` means "we have real information about the audio,"
    not "the audio scored well" -- a confirmed silent Reel is available
    (and correctly scores near zero), whereas a Reel where neither signal
    source produced anything is unavailable and excluded from reel
    weighting entirely (see ``compute_reel_analysis``).
    """
    notes: list[str] = []
    trending_bonus = 0.0
    alignment = 0.0
    quality_bonus = 0.0
    audio_available = False

    normalized_name = audio_name.strip() if isinstance(audio_name, str) else ""
    if normalized_name and not _is_generic_original_audio_label(normalized_name):
        audio_available = True
        trending_bonus = 3.0
        notes.append(f"Named audio: '{normalized_name}'.")
        audio_tokens = set(normalized_name.lower().split())
        caption_tokens = set(caption_text.lower().split()) if caption_text else set()
        overlap = audio_tokens & caption_tokens
        alignment = min(float(len(overlap)), 5.0)
        if overlap:
            notes.append(f"Audio/caption overlap: {sorted(overlap)}.")
    else:
        if normalized_name:
            notes.append(f"Audio name '{normalized_name}' is a generic original-audio label, not a trend signal.")
        else:
            notes.append("No audio_name supplied.")

        signals = reel_vision_signals if isinstance(reel_vision_signals, dict) else {}
        is_silent = signals.get("is_silent")
        raw_quality = signals.get("audio_quality_score")

        if is_silent is True:
            audio_available = True
            notes.append("Gemini detected no audible audio track (silent).")
        elif isinstance(raw_quality, (int, float)):
            audio_available = True
            quality_bonus = _clamp(float(raw_quality), 0.0, 10.0)
            audio_type = signals.get("audio_type")
            notes.append(f"Gemini audio_quality_score={raw_quality} (audio_type={audio_type or 'unknown'}).")

            if signals.get("hook_audio_present") is True:
                quality_bonus = _clamp(quality_bonus + 1.0, 0.0, 10.0)
                notes.append("Audio hook present in opening seconds.")

            raw_sync = signals.get("audio_visual_sync")
            if isinstance(raw_sync, (int, float)):
                sync_bonus = _clamp(float(raw_sync), 0.0, 1.0) * 1.0
                quality_bonus = _clamp(quality_bonus + sync_bonus, 0.0, 10.0)
                notes.append(f"audio_visual_sync={raw_sync}.")
        else:
            notes.append("No Gemini audio signals available either; audio excluded from reel weighting.")

    total = _clamp(trending_bonus + alignment + quality_bonus, 0.0, 10.0)

    return ReelAudioScore(
        trending_audio_bonus=_clamp(trending_bonus, 0.0, 5.0),
        audio_caption_alignment=_clamp(alignment, 0.0, 5.0),
        audio_quality_bonus=_clamp(quality_bonus, 0.0, 10.0),
        total=total,
        notes=notes,
        audio_available=audio_available,
    )
