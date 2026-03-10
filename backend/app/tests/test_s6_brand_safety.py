"""Tests for deterministic S6 brand safety scoring."""

from __future__ import annotations

from backend.app.analytics.s6_brand_safety_engine import compute_s6_brand_safety


def test_profanity_caption_penalty() -> None:
    score = compute_s6_brand_safety(
        caption_text="This is fucking bad",
        vision=None,
        s1_total_0_50=30.0,
        extracted_brand_mentions=None,
        extra_flags=None,
    )
    assert score.s6_raw_0_100 == 75
    assert score.total_0_50 == 37.5
    assert score.flags["profanity_detected"] is True


def test_low_s1_penalty_threshold() -> None:
    low_score = compute_s6_brand_safety(
        caption_text="Clean caption",
        vision=None,
        s1_total_0_50=14.9,
        extracted_brand_mentions=None,
        extra_flags=None,
    )
    edge_score = compute_s6_brand_safety(
        caption_text="Clean caption",
        vision=None,
        s1_total_0_50=15.0,
        extracted_brand_mentions=None,
        extra_flags=None,
    )
    assert low_score.s6_raw_0_100 == 85
    assert edge_score.s6_raw_0_100 == 100


def test_combined_penalties_and_bounds() -> None:
    score = compute_s6_brand_safety(
        caption_text="shit content",
        vision={"signals": [{"objects": ["beer bottle", "cigarette"]}]},
        s1_total_0_50=10.0,
        extracted_brand_mentions=["brandx"],
        extra_flags={"competitor_brand_mention": True},
    )
    # 100 - 25 - 15 - 20 - 35 = 5
    assert score.s6_raw_0_100 == 5
    assert score.total_0_50 == 2.5
    assert 0 <= score.s6_raw_0_100 <= 100
    assert 0.0 <= score.total_0_50 <= 50.0


def test_missing_inputs_safe() -> None:
    score = compute_s6_brand_safety(
        caption_text="",
        vision=None,
        s1_total_0_50=None,
        extracted_brand_mentions=None,
        extra_flags=None,
    )
    assert score.s6_raw_0_100 == 100
    assert score.total_0_50 == 50.0
    assert score.penalties == []


def test_determinism() -> None:
    payload = {
        "caption_text": "damn",
        "vision": {"signals": [{"objects": ["vape", "table"]}]},
        "s1_total_0_50": 12.0,
        "extracted_brand_mentions": ["foo"],
        "extra_flags": {"competitor_brand_mention": True},
    }
    first = compute_s6_brand_safety(**payload).model_dump(mode="python")
    second = compute_s6_brand_safety(**payload).model_dump(mode="python")
    assert first == second
