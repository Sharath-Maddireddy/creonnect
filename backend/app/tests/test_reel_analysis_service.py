"""Tests for reel analysis score aggregation."""

from __future__ import annotations

from backend.app.analytics.reel_analysis_service import compute_reel_analysis
from backend.app.analytics.reel_audio_engine import ReelAudioScore


def test_fast_pacing_high_hook_scores_well() -> None:
    signals = {"hook_frame_score": 0.9, "pacing_label": "fast", "retention_signal": 0.8}
    audio = ReelAudioScore(total=8.0)
    result = compute_reel_analysis(signals, audio, watch_time_pct=0.6)
    assert result.total is not None
    assert result.total > 70.0
    assert result.hook_score == 45.0
    assert result.pacing_score == 45.0


def test_missing_signals_returns_safe_midpoints() -> None:
    result = compute_reel_analysis({}, ReelAudioScore(), None)
    assert result.total is not None
    assert 0.0 <= result.total <= 100.0


def test_watch_time_boost_applied() -> None:
    signals = {"retention_signal": 0.5}
    audio = ReelAudioScore()
    result = compute_reel_analysis(signals, audio, watch_time_pct=0.7)
    assert result.retention_score == 30.0
