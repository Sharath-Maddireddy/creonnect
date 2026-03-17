"""Unit tests for S2 caption effectiveness scoring."""

from __future__ import annotations

import asyncio

import backend.app.analytics.caption_s2_engine as caption_s2_engine
from backend.app.analytics.caption_s2_engine import analyze_caption_via_llm, compute_s2_caption_effectiveness


def test_hook_scoring_with_question_and_keyword() -> None:
    score = compute_s2_caption_effectiveness("How this works?\nSome body text here")
    assert score.hook_score_0_100 == 100


def test_hook_scoring_missing_first_line_or_too_long() -> None:
    empty_score = compute_s2_caption_effectiveness("")
    assert empty_score.hook_score_0_100 == 30

    long_first_line = "x" * 126
    long_score = compute_s2_caption_effectiveness(long_first_line)
    assert long_score.hook_score_0_100 == 30


def test_length_scoring_ranges() -> None:
    assert compute_s2_caption_effectiveness("x" * 40).length_score_0_100 == 30
    assert compute_s2_caption_effectiveness("x" * 100).length_score_0_100 == 70
    assert compute_s2_caption_effectiveness("x" * 200).length_score_0_100 == 100
    assert compute_s2_caption_effectiveness("x" * 600).length_score_0_100 == 60


def test_hashtag_scoring_ranges() -> None:
    assert compute_s2_caption_effectiveness("No tags here").hashtag_score_0_100 == 20
    assert compute_s2_caption_effectiveness("One #tag").hashtag_score_0_100 == 60
    assert compute_s2_caption_effectiveness(" ".join(f"#t{i}" for i in range(10))).hashtag_score_0_100 == 100
    assert compute_s2_caption_effectiveness(" ".join(f"#t{i}" for i in range(20))).hashtag_score_0_100 == 70


def test_cta_regex() -> None:
    assert compute_s2_caption_effectiveness("Check this and link in bio now").cta_score_0_100 == 100
    assert compute_s2_caption_effectiveness("Please comment below").cta_score_0_100 == 100
    assert compute_s2_caption_effectiveness("No action words here").cta_score_0_100 == 20


def test_s2_weighted_total_matches_reference() -> None:
    caption = "Amazing reveal!\n" + ("x" * 70) + " #tag1 #tag2"
    score = compute_s2_caption_effectiveness(caption)

    # Expected: hook=80, length=70, hashtags=60, cta=20
    expected_raw = round(80 * 0.30 + 70 * 0.20 + 60 * 0.25 + 20 * 0.25)
    assert score.hook_score_0_100 == 80
    assert score.length_score_0_100 == 70
    assert score.hashtag_score_0_100 == 60
    assert score.cta_score_0_100 == 20
    assert score.s2_raw_0_100 == expected_raw
    assert score.total_0_50 == round(expected_raw / 2.0, 1)


def test_llm_caption_analysis_preserves_diagnostic_notes(monkeypatch) -> None:
    def fake_generate(self, prompt):  # noqa: ANN001
        return """
hook_score_0_100 82
length_score_0_100 75
hashtag_score_0_100 40
cta_score_0_100 20
s2_raw_0_100 58
technical_flaws
  - CTA could be more specific
  - Hook takes too long to get to the payoff
improved_hook_suggestion Lead with the transformation
""".strip()

    monkeypatch.setattr(caption_s2_engine.LLMClient, "generate", fake_generate)

    result = asyncio.run(analyze_caption_via_llm("A short caption without a CTA"))

    assert result.notes == [
        "CTA could be more specific",
        "Hook takes too long to get to the payoff",
        "Improved hook suggestion: Lead with the transformation",
    ]


def test_llm_caption_analysis_falls_back_to_deterministic_notes_when_missing(monkeypatch) -> None:
    caption = "Tiny caption"

    def fake_generate(self, prompt):  # noqa: ANN001
        return """
hook_score_0_100 40
length_score_0_100 30
hashtag_score_0_100 20
cta_score_0_100 20
s2_raw_0_100 28
""".strip()

    monkeypatch.setattr(caption_s2_engine.LLMClient, "generate", fake_generate)

    result = asyncio.run(analyze_caption_via_llm(caption))

    assert result.notes == compute_s2_caption_effectiveness(caption).notes


def test_llm_caption_analysis_logs_warning_on_failure(monkeypatch) -> None:
    warnings: list[str] = []

    def fake_generate(self, prompt):  # noqa: ANN001
        raise RuntimeError("llm transport exploded")

    def fake_warning(message: str, *args: object) -> None:
        warnings.append(message % args if args else message)

    monkeypatch.setattr(caption_s2_engine.LLMClient, "generate", fake_generate)
    monkeypatch.setattr(caption_s2_engine.logger, "warning", fake_warning)

    result = asyncio.run(analyze_caption_via_llm("A short caption without a CTA"))

    assert result.notes == compute_s2_caption_effectiveness("A short caption without a CTA").notes
    assert warnings == ["LLM caption analysis failed, using fallback: llm transport exploded"]
