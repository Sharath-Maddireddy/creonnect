"""Tests for deterministic reel audio scoring."""

from __future__ import annotations

from backend.app.analytics.reel_audio_engine import compute_reel_audio_score


def test_named_audio_gives_bonus() -> None:
    s = compute_reel_audio_score("Trending Song", "love this trending song vibes")
    assert s.trending_audio_bonus == 3.0
    assert s.total > 3.0


def test_no_audio_is_neutral() -> None:
    s = compute_reel_audio_score(None, "my caption")
    assert s.trending_audio_bonus == 0.0
    assert s.total == 0.0


def test_caption_overlap_increases_alignment() -> None:
    s = compute_reel_audio_score("love vibes", "full of love and vibes today")
    assert s.audio_caption_alignment >= 2.0
