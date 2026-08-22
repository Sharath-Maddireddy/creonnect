"""Tests for deterministic reel audio scoring."""

from __future__ import annotations

from backend.app.analytics.reel_audio_engine import compute_reel_audio_score


def test_named_audio_gives_bonus() -> None:
    s = compute_reel_audio_score("Trending Song", "love this trending song vibes")
    assert s.trending_audio_bonus == 3.0
    assert s.total > 3.0
    assert s.audio_available is True


def test_no_audio_is_neutral() -> None:
    s = compute_reel_audio_score(None, "my caption")
    assert s.trending_audio_bonus == 0.0
    assert s.total == 0.0
    assert s.audio_available is False


def test_caption_overlap_increases_alignment() -> None:
    s = compute_reel_audio_score("love vibes", "full of love and vibes today")
    assert s.audio_caption_alignment >= 2.0


def test_generic_original_audio_label_is_not_a_trend_signal() -> None:
    """Regression: 'Original audio' previously scored identically to a
    licensed trending track (both got the same +3.0 bonus)."""
    named = compute_reel_audio_score("Espresso - Sabrina Carpenter", "my caption")
    original = compute_reel_audio_score("Original audio", "my caption")

    assert named.trending_audio_bonus == 3.0
    assert original.trending_audio_bonus == 0.0
    assert original.total != named.total


def test_generic_original_audio_label_variants_are_all_excluded() -> None:
    for label in ["Original audio", "original sound", "Original_Audio", "  original  ".strip()]:
        s = compute_reel_audio_score(label, "caption")
        assert s.trending_audio_bonus == 0.0, label


def test_gemini_signals_score_audio_when_no_real_audio_name() -> None:
    """When audio_name is absent (the common case -- Instagram's read API
    does not expose track names), Gemini's own audio observation of the
    video becomes the audio signal instead of an automatic zero."""
    s = compute_reel_audio_score(
        None,
        "caption",
        reel_vision_signals={
            "audio_type": "ambient_asmr",
            "is_silent": False,
            "audio_quality_score": 7.0,
            "hook_audio_present": True,
            "audio_visual_sync": 0.8,
        },
    )
    assert s.audio_available is True
    assert s.audio_quality_bonus > 7.0  # base quality + hook + sync bonuses
    assert s.total > 0.0


def test_silent_reel_scores_zero_but_is_available() -> None:
    """A confirmed-silent Reel is a real, informative zero -- not 'no
    signal' -- so it must not trigger the missing-audio renormalization."""
    s = compute_reel_audio_score(None, "caption", reel_vision_signals={"is_silent": True})
    assert s.audio_available is True
    assert s.total == 0.0


def test_no_signal_from_either_source_is_unavailable() -> None:
    s = compute_reel_audio_score(None, "caption", reel_vision_signals={})
    assert s.audio_available is False
    assert s.total == 0.0


def test_real_audio_name_takes_priority_over_gemini_signals() -> None:
    s = compute_reel_audio_score(
        "Trending Song",
        "love this trending song",
        reel_vision_signals={"audio_quality_score": 9.0, "is_silent": False},
    )
    assert s.trending_audio_bonus == 3.0
    assert s.audio_quality_bonus == 0.0
