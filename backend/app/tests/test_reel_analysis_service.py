"""Tests for reel analysis score aggregation."""

from __future__ import annotations

from backend.app.analytics.reel_analysis_service import compute_reel_analysis
from backend.app.analytics.reel_audio_engine import ReelAudioScore, compute_reel_audio_score


def test_fast_pacing_high_hook_scores_well() -> None:
    signals = {"hook_frame_score": 0.9, "pacing_label": "fast", "retention_signal": 0.8}
    audio = ReelAudioScore(total=8.0, audio_available=True)
    result = compute_reel_analysis(signals, audio, watch_time_pct=0.6)
    assert result.total is not None
    assert result.total > 70.0
    assert result.hook_score == 45.0
    assert result.pacing_score == 45.0


def test_missing_audio_is_excluded_not_scored_as_zero() -> None:
    """Ingestion rarely supplies audio_name today; a reel should not be
    capped at 75/100 just because audio couldn't be evaluated."""
    signals = {"hook_frame_score": 0.9, "pacing_label": "fast", "retention_signal": 0.8}

    with_audio = compute_reel_analysis(signals, ReelAudioScore(total=8.0, audio_available=True), watch_time_pct=0.6)
    without_audio = compute_reel_analysis(signals, ReelAudioScore(total=0.0, audio_available=False), watch_time_pct=0.6)

    assert without_audio.audio_alignment_score == 0.0
    assert without_audio.total is not None and with_audio.total is not None
    # Excellent hook/pacing/retention should still score highly even though
    # audio couldn't be evaluated -- it must not drag the total down to ~75%
    # of what it would be with a strong audio_score.
    assert without_audio.total > 85.0
    assert "missing: audio" in " ".join(without_audio.notes)


def test_gemini_only_audio_signal_avoids_renormalization() -> None:
    """A silent or Gemini-scored Reel (no real audio_name) still counts as
    'audio available' -- it must be weighted normally, not excluded."""
    signals = {"hook_frame_score": 0.9, "pacing_label": "fast", "retention_signal": 0.8}
    audio = compute_reel_audio_score(None, "caption", reel_vision_signals={"is_silent": True})

    result = compute_reel_analysis(signals, audio, watch_time_pct=0.6)

    assert audio.audio_available is True
    assert "missing: audio" not in " ".join(result.notes)
    # Silent audio scores 0/50 and IS weighted in (25%), unlike the
    # excluded-from-weighting case which redistributes that 25% elsewhere.
    assert result.audio_alignment_score == 0.0
    assert result.total < 85.0


def test_missing_signals_returns_safe_midpoints() -> None:
    result = compute_reel_analysis({}, ReelAudioScore(), None)
    assert result.total is not None
    assert 0.0 <= result.total <= 100.0


def test_watch_time_boost_applied() -> None:
    signals = {"retention_signal": 0.5}
    audio = ReelAudioScore()
    result = compute_reel_analysis(signals, audio, watch_time_pct=0.7)
    assert result.retention_score == 30.0


def test_watch_time_boost_applied_for_integer_value() -> None:
    signals = {"retention_signal": 0.5}
    audio = ReelAudioScore()
    result = compute_reel_analysis(signals, audio, watch_time_pct=1)
    assert result.retention_score == 30.0
