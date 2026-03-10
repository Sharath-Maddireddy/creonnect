"""Unit tests for deterministic S1 visual quality scoring."""

from backend.app.analytics.vision_s1_engine import compute_visual_quality_score


def test_s1_high_signal_yields_high_score() -> None:
    vision_payload = {
        "provider": "gemini",
        "status": "ok",
        "signals": [
            {
                "primary_objects": ["person", "product"],
                "dominant_focus": "person",
                "hook_strength_score": 0.92,
                "detected_text": "Join the challenge",
                "scene_type": "studio",
            }
        ],
    }

    score = compute_visual_quality_score(vision_payload)

    assert 0.0 <= score.composition <= 10.0
    assert 0.0 <= score.lighting <= 10.0
    assert 0.0 <= score.subject_clarity <= 10.0
    assert 0.0 <= score.aesthetic_quality <= 10.0
    assert score.total > 40.0


def test_s1_weak_cluttered_signal_yields_low_score() -> None:
    vision_payload = {
        "provider": "gemini",
        "status": "ok",
        "signals": [
            {
                "objects": ["bag", "wall", "plant", "desk", "lamp", "screen"],
                "hook_strength_score": 0.20,
                "detected_text": "X" * 160,
            }
        ],
    }

    score = compute_visual_quality_score(vision_payload)

    assert score.total < 20.0
    assert score.composition <= 4.0
    assert score.subject_clarity <= 4.0


def test_s1_missing_fields_returns_safe_defaults() -> None:
    score = compute_visual_quality_score({"provider": "gemini", "status": "error", "signals": []})

    assert 0.0 <= score.composition <= 10.0
    assert 0.0 <= score.lighting <= 10.0
    assert 0.0 <= score.subject_clarity <= 10.0
    assert 0.0 <= score.aesthetic_quality <= 10.0
    assert 0.0 <= score.total <= 50.0
    assert score.notes
