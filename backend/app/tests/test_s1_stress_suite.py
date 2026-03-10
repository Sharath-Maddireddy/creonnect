"""Stress tests for deterministic S1 visual quality scoring."""

from __future__ import annotations

from backend.app.analytics.vision_s1_engine import compute_visual_quality_score


FALSE_HOOK_ILLUSION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "objects": ["sign", "wall", "lamp", "table", "book", "phone"],
            "hook_strength_score": 1.0,
            "detected_text": "Short overlay",
        }
    ],
}

MINIMALIST_CLEAN_POST = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "primary_objects": ["product"],
            "dominant_focus": "product",
            "hook_strength_score": 0.55,
            "detected_text": "Simple launch",
        }
    ],
}

OVER_TEXTED_GRAPHIC = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "objects": ["chart", "phone", "icon"],
            "hook_strength_score": 0.82,
            "detected_text": "Limited seats available now click link in bio to register fast",
        }
    ],
}

LOW_SIGNAL_GARBAGE = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "objects": ["bag", "wall", "plant", "desk", "lamp", "screen"],
            "hook_strength_score": 0.10,
            "detected_text": " ".join(["x"] * 40),
        }
    ],
}

EXTREME_EDGE_CLAMP = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "primary_objects": ["person"] * 20,
            "objects": ["person"] * 20,
            "dominant_focus": "subject",
            "hook_strength_score": 999,
            "detected_text": ["x" * 500],
            "aesthetic_quality": 999,
            "lighting_quality": 999,
            "subject_clarity": 999,
        }
    ],
}


def _score(payload: dict) -> dict[str, float]:
    result = compute_visual_quality_score(payload)
    return {
        "composition": result.composition,
        "lighting": result.lighting,
        "subject_clarity": result.subject_clarity,
        "aesthetic_quality": result.aesthetic_quality,
        "total": result.total,
    }


def _assert_bounds(snapshot: dict[str, float]) -> None:
    assert 0.0 <= snapshot["composition"] <= 10.0
    assert 0.0 <= snapshot["lighting"] <= 10.0
    assert 0.0 <= snapshot["subject_clarity"] <= 10.0
    assert 0.0 <= snapshot["aesthetic_quality"] <= 10.0
    assert 0.0 <= snapshot["total"] <= 50.0


def test_false_hook_illusion() -> None:
    score = _score(FALSE_HOOK_ILLUSION)
    assert 25.0 <= score["total"] <= 35.0


def test_minimalist_clean_post() -> None:
    score = _score(MINIMALIST_CLEAN_POST)
    assert 35.0 <= score["total"] <= 46.0


def test_over_texted_graphic() -> None:
    score = _score(OVER_TEXTED_GRAPHIC)
    assert 28.0 <= score["total"] <= 38.0


def test_low_signal_garbage() -> None:
    score = _score(LOW_SIGNAL_GARBAGE)
    assert score["total"] < 20.0


def test_empty_input_no_crash() -> None:
    scores = [_score({}) for _ in range(10)]
    assert all(20.0 <= score["total"] <= 30.0 for score in scores)
    assert all(score == scores[0] for score in scores[1:])


def test_extreme_edge_clamp() -> None:
    score = _score(EXTREME_EDGE_CLAMP)
    _assert_bounds(score)
    assert score["total"] <= 50.0


def test_determinism_10x() -> None:
    fixtures = [
        FALSE_HOOK_ILLUSION,
        MINIMALIST_CLEAN_POST,
        OVER_TEXTED_GRAPHIC,
        LOW_SIGNAL_GARBAGE,
        {},
        EXTREME_EDGE_CLAMP,
    ]

    for payload in fixtures:
        baseline = _score(payload)
        for _ in range(10):
            assert _score(payload) == baseline


def test_anti_gravity_hook_independence() -> None:
    hook_max = {
        "provider": "gemini",
        "status": "ok",
        "signals": [
            {
                "objects": ["a", "b", "c", "d", "e", "f"],
                "hook_strength_score": 1.0,
            }
        ],
    }
    no_hook = {
        "provider": "gemini",
        "status": "ok",
        "signals": [
            {
                "objects": ["a", "b", "c", "d", "e", "f"],
            }
        ],
    }

    hook_max_score = _score(hook_max)
    no_hook_score = _score(no_hook)

    assert hook_max_score["total"] <= 40.0
    assert no_hook_score["total"] > 10.0
