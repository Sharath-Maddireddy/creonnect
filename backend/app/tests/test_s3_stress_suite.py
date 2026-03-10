"""Stress suite for deterministic S3 content clarity scoring."""

from __future__ import annotations

from backend.app.analytics.vision_s3_engine import compute_s3_content_clarity


CLEAR_SINGLE_MESSAGE_VISION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "dominant_focus": "product",
            "primary_objects": ["product"],
            "scene_type": "studio",
            "scene_description": "Product showcase scene",
            "detected_text": "new drop",
        }
    ],
}
CLEAR_SINGLE_MESSAGE_CAPTION = "New drop is live now."

CLUTTER_NO_FOCUS_VISION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "objects": ["a", "b", "c", "d", "e", "f", "g", "h"],
            "detected_text": " ".join(["promo"] * 20),
        }
    ],
}
CLUTTER_NO_FOCUS_CAPTION = (
    " ".join(["ramblingcontext"] * 130) + " " + " ".join(f"#tag{i}" for i in range(25))
)

POSTER_ALIGNED_VISION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "objects": ["poster"],
            "dominant_focus": "poster",
            "detected_text": "join challenge today",
            "scene_description": "Graphic poster",
        }
    ],
}
POSTER_ALIGNED_CAPTION = "Join challenge today and save this post."


def _snapshot(vision: dict | None, caption: str) -> dict[str, float]:
    score = compute_s3_content_clarity(vision, caption)
    return {
        "message_singularity": score.message_singularity,
        "context_clarity": score.context_clarity,
        "caption_alignment": score.caption_alignment,
        "visual_message_support": score.visual_message_support,
        "cognitive_load": score.cognitive_load,
        "total": score.total,
    }


def _assert_in_bounds(snapshot: dict[str, float]) -> None:
    assert 0.0 <= snapshot["message_singularity"] <= 10.0
    assert 0.0 <= snapshot["context_clarity"] <= 10.0
    assert 0.0 <= snapshot["caption_alignment"] <= 10.0
    assert 0.0 <= snapshot["visual_message_support"] <= 10.0
    assert 0.0 <= snapshot["cognitive_load"] <= 10.0
    assert 0.0 <= snapshot["total"] <= 50.0


def test_clear_single_message() -> None:
    score = _snapshot(CLEAR_SINGLE_MESSAGE_VISION, CLEAR_SINGLE_MESSAGE_CAPTION)
    assert score["total"] >= 35.0


def test_clutter_no_focus() -> None:
    score = _snapshot(CLUTTER_NO_FOCUS_VISION, CLUTTER_NO_FOCUS_CAPTION)
    assert score["total"] <= 20.0


def test_poster_with_aligned_caption() -> None:
    score = _snapshot(POSTER_ALIGNED_VISION, POSTER_ALIGNED_CAPTION)
    assert score["caption_alignment"] >= 7.0


def test_empty_everything() -> None:
    results = [_snapshot({}, "") for _ in range(10)]
    assert all(15.0 <= result["total"] <= 30.0 for result in results)
    assert all(result == results[0] for result in results[1:])


def test_determinism_10x() -> None:
    fixtures = [
        (CLEAR_SINGLE_MESSAGE_VISION, CLEAR_SINGLE_MESSAGE_CAPTION),
        (CLUTTER_NO_FOCUS_VISION, CLUTTER_NO_FOCUS_CAPTION),
        (POSTER_ALIGNED_VISION, POSTER_ALIGNED_CAPTION),
        ({}, ""),
    ]

    for vision, caption in fixtures:
        baseline = _snapshot(vision, caption)
        for _ in range(10):
            assert _snapshot(vision, caption) == baseline


def test_clamping() -> None:
    extreme_vision = {
        "provider": "gemini",
        "status": "ok",
        "signals": [
            {
                "primary_objects": ["item"] * 200,
                "objects": ["obj"] * 200,
                "dominant_focus": "",
                "scene_description": 999,
                "scene_type": None,
                "detected_text": [None, "X" * 5000, 123],
            }
        ],
    }
    extreme_caption = ("word " * 300) + ("#spam " * 50)

    score = _snapshot(extreme_vision, extreme_caption)
    _assert_in_bounds(score)
