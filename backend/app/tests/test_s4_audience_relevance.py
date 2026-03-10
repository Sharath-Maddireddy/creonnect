"""Tests for deterministic S4 audience relevance scoring."""

from __future__ import annotations

from backend.app.analytics.s4_audience_relevance_engine import compute_s4_audience_relevance


def test_exact_match_is_100() -> None:
    score = compute_s4_audience_relevance("Fitness", "fitness")
    assert score.affinity_band == "EXACT"
    assert score.s4_raw_0_100 == 100
    assert score.total_0_50 == 50.0


def test_adjacent_match_is_75() -> None:
    score = compute_s4_audience_relevance("sports", "fitness")
    assert score.affinity_band == "ADJACENT"
    assert score.s4_raw_0_100 == 75
    assert score.total_0_50 == 37.5


def test_unrelated_is_15() -> None:
    score = compute_s4_audience_relevance("fitness", "technology")
    assert score.affinity_band == "UNRELATED"
    assert score.s4_raw_0_100 == 15
    assert score.total_0_50 == 7.5


def test_missing_inputs_neutral_50() -> None:
    score = compute_s4_audience_relevance(None, "fitness")
    assert score.affinity_band == "UNKNOWN"
    assert score.s4_raw_0_100 == 50
    assert score.total_0_50 == 25.0
    assert any("missing" in note.lower() for note in score.notes)


def test_determinism() -> None:
    first = compute_s4_audience_relevance("sports", "fitness").model_dump(mode="python")
    second = compute_s4_audience_relevance("sports", "fitness").model_dump(mode="python")
    assert first == second
