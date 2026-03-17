"""Aggregates reel vision signals + audio score into the ReelAnalysis model."""

from __future__ import annotations

from typing import Any

from backend.app.analytics.reel_audio_engine import ReelAudioScore
from backend.app.domain.post_models import ReelAnalysis


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def compute_reel_analysis(
    reel_vision_signals: dict[str, Any],
    audio_score: ReelAudioScore,
    watch_time_pct: float | None,
    reel_vision_status: str = "ok",
) -> ReelAnalysis:
    """
    Compute reel scores where sub-scores are 0..50 and final total is 0..100.

    Scoring:
    - hook_score      = hook_frame_score * 50                    weight 30%
    - pacing_score    = fast->45, medium->35, slow->25           weight 20%
    - audio_score_50  = audio_score.total * 5  (0..10 -> 0..50)  weight 25%
    - retention_score = retention_signal * 50                    weight 25%
                        +5 if watch_time_pct >= 0.5
                        -5 if watch_time_pct < 0.25
    - total = (0.30*hook + 0.20*pacing + 0.25*audio + 0.25*retention) * 2
    """
    notes: list[str] = []
    signals = reel_vision_signals if isinstance(reel_vision_signals, dict) else {}

    raw_hook = signals.get("hook_frame_score")
    if isinstance(raw_hook, (int, float)):
        hook_score = _clamp(float(raw_hook) * 50.0, 0.0, 50.0)
    else:
        hook_score = 25.0

    pacing_map = {"fast": 45.0, "medium": 35.0, "slow": 25.0}
    pacing_label = str(signals.get("pacing_label", "medium")).lower().strip()
    pacing_score = _clamp(pacing_map.get(pacing_label, 35.0), 0.0, 50.0)
    notes.append(f"Pacing: {pacing_label}.")

    audio_alignment_score = _clamp(float(audio_score.total) * 5.0, 0.0, 50.0)
    notes.extend(audio_score.notes)

    raw_retention = signals.get("retention_signal")
    if isinstance(raw_retention, (int, float)):
        retention_score = _clamp(float(raw_retention) * 50.0, 0.0, 50.0)
    else:
        retention_score = 25.0

    if isinstance(watch_time_pct, float):
        if watch_time_pct >= 0.5:
            retention_score = _clamp(retention_score + 5.0, 0.0, 50.0)
            notes.append("Watch-time >=50% boosts retention.")
        elif watch_time_pct < 0.25:
            retention_score = _clamp(retention_score - 5.0, 0.0, 50.0)
            notes.append("Watch-time <25% penalises retention.")

    total = _clamp(
        (hook_score * 0.30 + pacing_score * 0.20 + audio_alignment_score * 0.25 + retention_score * 0.25) * 2.0,
        0.0,
        100.0,
    )

    return ReelAnalysis(
        hook_score=round(hook_score, 2),
        pacing_score=round(pacing_score, 2),
        audio_alignment_score=round(audio_alignment_score, 2),
        retention_score=round(retention_score, 2),
        total=round(total, 2),
        reel_vision_status=reel_vision_status,
        notes=notes,
    )
