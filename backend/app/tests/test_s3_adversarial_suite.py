"""Adversarial test suite for S3 content clarity anti-spam behavior."""

from __future__ import annotations

import random
import statistics

from backend.app.analytics.vision_s3_engine import compute_s3_content_clarity


CASE_1_CAPTION_SPAM_VISION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [{"primary_objects": ["person"]}],
}
CASE_1_CAPTION_SPAM_CAPTION = "person person person person person person person person person"

CASE_2_HASHTAG_FLOOD_VISION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [{"primary_objects": ["product"]}],
}
CASE_2_HASHTAG_FLOOD_CAPTION = "new drop now " + " ".join(f"#tag{i}" for i in range(21))

CASE_3_POSTER_ALIGNED_VISION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "objects": ["poster"],
            "dominant_focus": "poster",
            "scene_description": "graphic poster",
            "detected_text": "join challenge today",
        }
    ],
}
CASE_3_POSTER_ALIGNED_CAPTION = "join challenge today and save this post"

CASE_4_CLUTTER_LONG_VISION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "objects": ["a", "b", "c", "d", "e", "f", "g", "h"],
            "detected_text": " ".join(["promo"] * 20),
        }
    ],
}
CASE_4_CLUTTER_LONG_CAPTION = " ".join(["ramblingcontext"] * 140) + " " + " ".join(f"#h{i}" for i in range(22))

CASE_5_EMPTY_VISION = {}
CASE_5_EMPTY_CAPTION = ""

CASE_6_STRONG_SHORT_VISION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "dominant_focus": "product",
            "primary_objects": ["product"],
            "scene_type": "studio",
            "scene_description": "product on table",
            "detected_text": "new drop",
        }
    ],
}
CASE_6_STRONG_SHORT_CAPTION = "new drop today"

CASE_7_OVERLAP_REPETITION_TRAP_VISION = {
    "provider": "gemini",
    "status": "ok",
    "signals": [
        {
            "objects": ["poster"],
            "dominant_focus": "poster",
            "scene_description": "poster",
            "detected_text": "join challenge today",
        }
    ],
}
CASE_7_OVERLAP_REPETITION_TRAP_CAPTION = (
    "join challenge today join challenge today join challenge today #cta #promo #sale"
)


def _score(vision: dict, caption: str) -> float:
    return compute_s3_content_clarity(vision, caption).total


def _fixtures() -> list[tuple[dict, str]]:
    return [
        (CASE_1_CAPTION_SPAM_VISION, CASE_1_CAPTION_SPAM_CAPTION),
        (CASE_2_HASHTAG_FLOOD_VISION, CASE_2_HASHTAG_FLOOD_CAPTION),
        (CASE_3_POSTER_ALIGNED_VISION, CASE_3_POSTER_ALIGNED_CAPTION),
        (CASE_4_CLUTTER_LONG_VISION, CASE_4_CLUTTER_LONG_CAPTION),
        (CASE_5_EMPTY_VISION, CASE_5_EMPTY_CAPTION),
        (CASE_6_STRONG_SHORT_VISION, CASE_6_STRONG_SHORT_CAPTION),
        (CASE_7_OVERLAP_REPETITION_TRAP_VISION, CASE_7_OVERLAP_REPETITION_TRAP_CAPTION),
    ]


def test_case_1_caption_spam() -> None:
    assert _score(CASE_1_CAPTION_SPAM_VISION, CASE_1_CAPTION_SPAM_CAPTION) <= 35.0


def test_case_2_hashtag_flood() -> None:
    assert _score(CASE_2_HASHTAG_FLOOD_VISION, CASE_2_HASHTAG_FLOOD_CAPTION) < 30.0


def test_case_3_poster_aligned() -> None:
    total = _score(CASE_3_POSTER_ALIGNED_VISION, CASE_3_POSTER_ALIGNED_CAPTION)
    assert 35.0 <= total <= 45.0


def test_case_4_clutter_long() -> None:
    assert _score(CASE_4_CLUTTER_LONG_VISION, CASE_4_CLUTTER_LONG_CAPTION) < 20.0


def test_case_5_empty() -> None:
    total = _score(CASE_5_EMPTY_VISION, CASE_5_EMPTY_CAPTION)
    assert 15.0 <= total <= 30.0


def test_case_6_strong_short() -> None:
    total = _score(CASE_6_STRONG_SHORT_VISION, CASE_6_STRONG_SHORT_CAPTION)
    assert 35.0 <= total <= 45.0


def test_case_7_overlap_repetition_trap() -> None:
    trap = _score(CASE_7_OVERLAP_REPETITION_TRAP_VISION, CASE_7_OVERLAP_REPETITION_TRAP_CAPTION)
    poster = _score(CASE_3_POSTER_ALIGNED_VISION, CASE_3_POSTER_ALIGNED_CAPTION)
    assert trap < poster


def test_determinism_10x() -> None:
    for vision, caption in _fixtures():
        baseline = compute_s3_content_clarity(vision, caption).model_dump(mode="python")
        for _ in range(10):
            assert compute_s3_content_clarity(vision, caption).model_dump(mode="python") == baseline


def test_distribution_200_random() -> None:
    rng = random.Random(1337)
    words = [
        "person",
        "product",
        "offer",
        "join",
        "challenge",
        "today",
        "save",
        "share",
        "insight",
        "story",
        "studio",
        "tips",
        "growth",
        "design",
        "workflow",
        "launch",
    ]

    totals: list[float] = []
    for _ in range(200):
        if rng.random() < 0.2:
            vision = {
                "signals": [
                    {
                        "objects": ["a", "b", "c", "d", "e", "f", "g", "h"],
                        "detected_text": " ".join(["promo"] * rng.randint(16, 30)),
                    }
                ]
            }
            caption = (
                " ".join(["spamword"] * rng.randint(80, 160))
                + " "
                + " ".join(f"#h{i}" for i in range(rng.randint(15, 30)))
            )
        else:
            object_count = rng.randint(0, 8)
            objects = [
                rng.choice(["person", "product", "desk", "phone", "poster", "chart", "lamp", "bag"])
                for _ in range(object_count)
            ]
            signal: dict[str, object] = {}
            if objects:
                signal["objects"] = objects
                if rng.random() < 0.5:
                    signal["primary_objects"] = objects[: max(1, min(2, len(objects)))]
            if rng.random() < 0.45:
                signal["dominant_focus"] = rng.choice(["person", "product", "poster"])
            if rng.random() < 0.5:
                signal["scene_description"] = "sample scene"
            if rng.random() < 0.35:
                signal["scene_type"] = rng.choice(["studio", "outdoor", "office"])
            if rng.random() < 0.6:
                signal["detected_text"] = " ".join(rng.choice(words) for _ in range(rng.randint(0, 24)))
            vision = {"signals": [signal]}

            caption_parts = [rng.choice(words) for _ in range(rng.randint(0, 140))]
            caption_parts += [f"#tag{rng.randint(0, 50)}" for _ in range(rng.randint(0, 25))]
            caption = " ".join(caption_parts)

        totals.append(_score(vision, caption))

    assert statistics.pstdev(totals) >= 5.0
    assert min(totals) <= 15.0
    assert max(totals) >= 40.0
