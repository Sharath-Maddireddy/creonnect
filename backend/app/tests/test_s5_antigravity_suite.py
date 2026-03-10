"""S5 Anti-Gravity adversarial test suite.

Tests schema fallback, numeric clamping, total recomputation,
consistency cap, notes truncation, and determinism of the
S5 engagement-potential post-processing pipeline.

All tests mock GPT output directly — no external API calls.
"""

from __future__ import annotations

from backend.app.domain.post_models import (
    ContentClarityScore,
    EngagementPotentialScore,
    VisualQualityScore,
)
from backend.app.services.ai_analysis_service import (
    _apply_s5_consistency_cap,
    _fallback_engagement_potential_score,
    _sanitize_engagement_potential_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fb() -> EngagementPotentialScore:
    """Shorthand for the standard fallback score."""
    return _fallback_engagement_potential_score()


def _low_s1(total: float = 10.0) -> VisualQualityScore:
    return VisualQualityScore(
        composition=2.0, lighting=2.0, subject_clarity=2.0, aesthetic_quality=2.0, total=total
    )


def _low_s3(total: float = 10.0) -> ContentClarityScore:
    return ContentClarityScore(
        message_singularity=2.0, context_clarity=2.0, caption_alignment=2.0,
        visual_message_support=2.0, cognitive_load=2.0, total=total,
    )


def _mid_s3(total: float = 25.0) -> ContentClarityScore:
    return ContentClarityScore(
        message_singularity=5.0, context_clarity=5.0, caption_alignment=5.0,
        visual_message_support=5.0, cognitive_load=5.0, total=total,
    )


# ===================================================================
# A) Schema & Fallback Attacks
# ===================================================================


def test_missing_required_key_triggers_fallback() -> None:
    """A1 — GPT output missing 'novelty_or_value' → fallback total=25."""
    raw = {
        "emotional_resonance": 8.0,
        "shareability": 7.0,
        "save_worthiness": 6.0,
        "comment_potential": 7.0,
        # novelty_or_value MISSING
        "total": 28.0,
        "notes": [],
    }
    result = _sanitize_engagement_potential_score(raw)

    assert result is None, "Missing key must return None so caller falls back"

    fb = _fb()
    assert fb.total == 25.0
    assert any("fallback" in n for n in fb.notes)


def test_extra_key_is_dropped_and_payload_still_parses() -> None:
    """A2 — Extra key ('virality_score') is dropped by sanitizer and parsing succeeds."""
    raw = {
        "emotional_resonance": 8.0,
        "shareability": 7.0,
        "save_worthiness": 6.0,
        "comment_potential": 7.0,
        "novelty_or_value": 8.0,
        "total": 36.0,
        "notes": [],
        "virality_score": 9.0,  # extra key
    }
    result = _sanitize_engagement_potential_score(raw)

    assert result is not None
    assert result.total == 36.0


def test_wrong_type_coerces_or_falls_back() -> None:
    """A3 — String 'high' for shareability cannot be cast to float.

    Pydantic _clamp_sub_score catches ValueError and returns 0.0,
    so model_validate succeeds with shareability=0.0.
    """
    raw = {
        "emotional_resonance": 8.0,
        "shareability": "high",  # wrong type
        "save_worthiness": 6.0,
        "comment_potential": 7.0,
        "novelty_or_value": 8.0,
        "total": 36.0,
        "notes": [],
    }
    result = _sanitize_engagement_potential_score(raw)

    if result is None:
        # Also acceptable — strict fallback
        fb = _fb()
        assert fb.total == 25.0
    else:
        # Pydantic coerced "high" → 0.0 via _clamp_sub_score
        assert result.shareability == 0.0
        expected_total = (
            result.emotional_resonance
            + result.shareability
            + result.save_worthiness
            + result.comment_potential
            + result.novelty_or_value
        )
        assert result.total == round(expected_total, 2)


# ===================================================================
# B) Numeric Cheating Attacks
# ===================================================================


def test_out_of_range_subscores_clamped() -> None:
    """B4 — Extreme subscores (999, -5) must clamp to [0, 10]."""
    raw = {
        "emotional_resonance": 999,
        "shareability": 8.0,
        "save_worthiness": 6.0,
        "comment_potential": -5,
        "novelty_or_value": 7.0,
        "total": 1015.0,
        "notes": [],
    }
    result = _sanitize_engagement_potential_score(raw)

    assert result is not None
    assert result.emotional_resonance == 10.0
    assert result.comment_potential == 0.0

    for field_name in ("emotional_resonance", "shareability", "save_worthiness",
                       "comment_potential", "novelty_or_value"):
        val = getattr(result, field_name)
        assert 0.0 <= val <= 10.0, f"{field_name}={val} out of bounds"

    expected_total = (
        result.emotional_resonance
        + result.shareability
        + result.save_worthiness
        + result.comment_potential
        + result.novelty_or_value
    )
    assert result.total == round(expected_total, 2)
    assert 0.0 <= result.total <= 50.0


def test_total_mismatch_recomputed() -> None:
    """B5 — GPT claims total=50 but subscores sum to 24 → total overwritten."""
    raw = {
        "emotional_resonance": 5.0,
        "shareability": 5.0,
        "save_worthiness": 5.0,
        "comment_potential": 5.0,
        "novelty_or_value": 4.0,
        "total": 50.0,  # WRONG — should be 24
        "notes": [],
    }
    result = _sanitize_engagement_potential_score(raw)

    assert result is not None
    assert result.total == 24.0, f"Total must be recomputed to 24.0, got {result.total}"


# ===================================================================
# C) Consistency Cap (Core "anti-gravity")
# ===================================================================


def test_consistency_cap_triggers_when_both_s1_s3_low() -> None:
    """C6 — S1=10, S3=10, GPT all-10 subscores → total capped at 30."""
    s5 = EngagementPotentialScore(
        emotional_resonance=10.0,
        shareability=10.0,
        save_worthiness=10.0,
        comment_potential=10.0,
        novelty_or_value=10.0,
        total=50.0,
    )
    capped = _apply_s5_consistency_cap(s5, _low_s1(10.0), _low_s3(10.0))

    assert capped.total <= 30.0
    assert any("consistency cap applied" in n for n in capped.notes)
    # Subscores may remain 10 — only total is capped
    assert capped.emotional_resonance == 10.0


def test_consistency_cap_does_not_trigger_when_only_s1_low() -> None:
    """C7 — S1=10, S3=25 → no cap (rule requires BOTH < 15)."""
    s5 = EngagementPotentialScore(
        emotional_resonance=10.0,
        shareability=10.0,
        save_worthiness=10.0,
        comment_potential=10.0,
        novelty_or_value=10.0,
        total=50.0,
    )
    result = _apply_s5_consistency_cap(s5, _low_s1(10.0), _mid_s3(25.0))

    assert result.total == 50.0, "Cap should NOT trigger when only S1 is low"
    assert not any("consistency cap" in n for n in result.notes)


def test_consistency_cap_does_not_trigger_when_only_s3_low() -> None:
    """Extra — S1=25, S3=10 → no cap."""
    high_s1 = VisualQualityScore(
        composition=5.0, lighting=5.0, subject_clarity=5.0, aesthetic_quality=5.0, total=25.0
    )
    s5 = EngagementPotentialScore(
        emotional_resonance=9.0,
        shareability=9.0,
        save_worthiness=9.0,
        comment_potential=9.0,
        novelty_or_value=9.0,
        total=45.0,
    )
    result = _apply_s5_consistency_cap(s5, high_s1, _low_s3(10.0))

    assert result.total == 45.0
    assert not any("consistency cap" in n for n in result.notes)


# ===================================================================
# D) Notes Field Abuse
# ===================================================================


def test_notes_field_truncation() -> None:
    """D8 — Huge notes list shouldn't crash; items truncated to ≤120 chars."""
    raw = {
        "emotional_resonance": 7.0,
        "shareability": 7.0,
        "save_worthiness": 7.0,
        "comment_potential": 7.0,
        "novelty_or_value": 7.0,
        "total": 35.0,
        "notes": ["A" * 5000, "B" * 300, "short note"],
    }
    result = _sanitize_engagement_potential_score(raw)

    assert result is not None
    for note in result.notes:
        assert len(note) <= 120, f"Note too long: {len(note)} chars"
    assert result.total == 35.0


def test_notes_field_none_is_safe() -> None:
    """Notes field as None should default to empty list."""
    raw = {
        "emotional_resonance": 6.0,
        "shareability": 6.0,
        "save_worthiness": 6.0,
        "comment_potential": 6.0,
        "novelty_or_value": 6.0,
        "total": 30.0,
        "notes": None,
    }
    result = _sanitize_engagement_potential_score(raw)

    assert result is not None
    assert result.notes == []


# ===================================================================
# E) Determinism
# ===================================================================


def test_determinism_10x_sanitize() -> None:
    """E9 — Same input 10x → identical output every time."""
    raw = {
        "emotional_resonance": 7.5,
        "shareability": 8.0,
        "save_worthiness": 6.5,
        "comment_potential": 7.0,
        "novelty_or_value": 8.0,
        "total": 99.0,  # will be recomputed
        "notes": ["test note"],
    }
    baseline = _sanitize_engagement_potential_score(raw)
    assert baseline is not None

    for i in range(10):
        result = _sanitize_engagement_potential_score(raw)
        assert result is not None, f"Run {i+1} returned None"
        assert result.model_dump() == baseline.model_dump(), f"Mismatch on run {i+1}"


def test_determinism_10x_full_pipeline() -> None:
    """Determinism including consistency cap."""
    raw = {
        "emotional_resonance": 9.0,
        "shareability": 9.0,
        "save_worthiness": 9.0,
        "comment_potential": 9.0,
        "novelty_or_value": 9.0,
        "total": 45.0,
        "notes": [],
    }
    s1 = _low_s1(10.0)
    s3 = _low_s3(10.0)

    results = []
    for _ in range(10):
        sanitized = _sanitize_engagement_potential_score(raw)
        assert sanitized is not None
        capped = _apply_s5_consistency_cap(sanitized, s1, s3)
        results.append(capped.model_dump())

    for i, r in enumerate(results[1:], start=2):
        assert r == results[0], f"Determinism failed on run {i}"


# ===================================================================
# Bonus: Fallback object integrity
# ===================================================================


def test_fallback_object_integrity() -> None:
    """Fallback score must have all-5.0 subscores, total=25, 'fallback' in notes."""
    fb = _fb()

    assert fb.emotional_resonance == 5.0
    assert fb.shareability == 5.0
    assert fb.save_worthiness == 5.0
    assert fb.comment_potential == 5.0
    assert fb.novelty_or_value == 5.0
    assert fb.total == 25.0
    assert any("fallback" in n for n in fb.notes)


def test_none_input_returns_none() -> None:
    """Sanitizer given None returns None → caller should use fallback."""
    assert _sanitize_engagement_potential_score(None) is None


def test_empty_dict_returns_none() -> None:
    """Sanitizer given {} returns None (missing required keys)."""
    assert _sanitize_engagement_potential_score({}) is None
