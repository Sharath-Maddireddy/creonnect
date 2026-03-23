from __future__ import annotations

import asyncio

import backend.app.analytics.vision_s3_engine as vision_s3_engine
from backend.app.analytics.vision_s3_engine import (
    analyze_content_clarity_via_llm,
    compute_s3_content_clarity,
)


VISION = {
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


def test_llm_s3_analysis_uses_weighted_total(monkeypatch) -> None:
    def fake_generate(self, prompt):  # noqa: ANN001
        assert "Vision Signals JSON:" in prompt["user"]
        assert '"dominant_focus": "product"' in prompt["user"]
        return """
message_singularity_0_10 8
context_clarity_0_10 7
caption_alignment_0_10 6
visual_message_support_0_10 9
cognitive_load_0_10 5
technical_flaws
  - Slight clutter
  - Caption could be more specific
""".strip()

    monkeypatch.setattr(vision_s3_engine.LLMClient, "generate", fake_generate)

    result = asyncio.run(analyze_content_clarity_via_llm(VISION, "New drop is live now."))

    assert result.message_singularity == 8
    assert result.context_clarity == 7
    assert result.caption_alignment == 6
    assert result.visual_message_support == 9
    assert result.cognitive_load == 5
    assert result.total == 35.75
    assert result.notes == ["Slight clutter", "Caption could be more specific"]


def test_llm_s3_analysis_falls_back_to_deterministic_notes_when_missing(monkeypatch) -> None:
    caption = "New drop is live now."

    def fake_generate(self, prompt):  # noqa: ANN001
        return """
message_singularity_0_10 8
context_clarity_0_10 7
caption_alignment_0_10 6
visual_message_support_0_10 9
cognitive_load_0_10 5
""".strip()

    monkeypatch.setattr(vision_s3_engine.LLMClient, "generate", fake_generate)

    result = asyncio.run(analyze_content_clarity_via_llm(VISION, caption))

    assert result.notes == compute_s3_content_clarity(VISION, caption).notes


def test_llm_s3_analysis_logs_warning_and_falls_back_on_failure(monkeypatch) -> None:
    warnings: list[str] = []

    def fake_generate(self, prompt):  # noqa: ANN001
        raise RuntimeError("llm transport exploded")

    def fake_warning(message: str, *args: object) -> None:
        warnings.append(message % args if args else message)

    monkeypatch.setattr(vision_s3_engine.LLMClient, "generate", fake_generate)
    monkeypatch.setattr(vision_s3_engine.logger, "warning", fake_warning)

    result = asyncio.run(analyze_content_clarity_via_llm(VISION, "New drop is live now."))

    assert result == compute_s3_content_clarity(VISION, "New drop is live now.")
    assert warnings == ["LLM S3 content clarity analysis failed, using fallback: llm transport exploded"]
