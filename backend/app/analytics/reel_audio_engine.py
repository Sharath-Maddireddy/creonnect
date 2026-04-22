"""Deterministic audio/trend scoring for Instagram Reels."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReelAudioScore:
    trending_audio_bonus: float = 0.0
    audio_caption_alignment: float = 0.0
    total: float = 0.0
    notes: list[str] = field(default_factory=list)


def compute_reel_audio_score(
    audio_name: str | None,
    caption_text: str,
) -> ReelAudioScore:
    """
    Score audio/trend alignment deterministically.

    - Named audio_name -> trending_audio_bonus = 3.0
    - No audio_name    -> trending_audio_bonus = 0.0
    - audio_caption_alignment = unique token overlap between
      audio_name.lower().split() and caption_text.lower().split(), capped at 5.
    - total = min(trending_audio_bonus + audio_caption_alignment, 10.0)
    """
    notes: list[str] = []
    trending_bonus = 0.0
    alignment = 0.0

    if audio_name and audio_name.strip():
        normalized_audio_name = audio_name.strip()
        trending_bonus = 3.0
        notes.append(f"Named audio: '{normalized_audio_name}'.")
        audio_tokens = set(normalized_audio_name.lower().split())
        caption_tokens = set(caption_text.lower().split()) if caption_text else set()
        overlap = audio_tokens & caption_tokens
        alignment = min(float(len(overlap)), 5.0)
        if overlap:
            notes.append(f"Audio/caption overlap: {sorted(overlap)}.")
    else:
        notes.append("Original or no audio detected.")

    return ReelAudioScore(
        trending_audio_bonus=max(0.0, min(5.0, trending_bonus)),
        audio_caption_alignment=max(0.0, min(5.0, alignment)),
        total=max(0.0, min(10.0, trending_bonus + alignment)),
        notes=notes,
    )
