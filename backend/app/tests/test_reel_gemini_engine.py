from __future__ import annotations

import sys
import types

import backend.app.analytics.reel_gemini_engine as reel_gemini_engine
from backend.app.ai.prompts import REEL_VISION_EVALUATION_PROMPT


def test_reel_prompt_contains_hook_and_sync_rubrics() -> None:
    assert "Scoring rubric for hook_strength_score (0-1):" in REEL_VISION_EVALUATION_PROMPT
    assert "0.90-1.00: elite hook" in REEL_VISION_EVALUATION_PROMPT
    assert "Slow pacing, dark lighting, no text, and no clear motion should generally land in 0.10-0.30." in (
        REEL_VISION_EVALUATION_PROMPT
    )
    assert "Scoring rubric for audio_visual_sync (0-1):" in REEL_VISION_EVALUATION_PROMPT
    assert "Do not score above 0.85 unless there are clear timed cuts" in REEL_VISION_EVALUATION_PROMPT


def test_upload_and_analyse_uses_imported_reel_prompt(monkeypatch) -> None:
    captured_contents: list[object] = []
    sentinel_prompt = "REEL PROMPT SENTINEL"

    class FakeUploadFileConfig:
        def __init__(self, mime_type: str) -> None:
            self.mime_type = mime_type

    class FakeFilesApi:
        def upload(self, file, config):  # noqa: ANN001
            return types.SimpleNamespace(name="uploaded-file")

        def get(self, name: str):  # noqa: ARG002
            return types.SimpleNamespace(name="uploaded-file", state="ACTIVE")

        def delete(self, name: str) -> None:  # noqa: ARG002
            return None

    class FakeModelsApi:
        def generate_content(self, model: str, contents: list[object]):  # noqa: ARG002
            captured_contents.extend(contents)
            return types.SimpleNamespace(
                text="""
hook_frame_score 0.72
hook_text_overlay Stop scrolling
pacing_label fast
cut_count_estimate 11
dominant_emotion curiosity
retention_signal 0.68
audio_visual_sync 0.74
objects
  - creator
  - phone
scene_description Creator points at text callouts while demonstrating a quick workflow
detected_text 3 editing mistakes
visual_style talking-head tutorial
hook_strength_score 0.78
cringe_score 18
cringe_signals
  - Slightly generic thumbnail pose
cringe_fixes
  - Start with the strongest payoff frame
production_level medium
adult_content_detected false
""".strip()
            )

    class FakeClient:
        def __init__(self, api_key: str) -> None:  # noqa: ARG002
            self.files = FakeFilesApi()
            self.models = FakeModelsApi()

    fake_genai_module = types.ModuleType("google.genai")
    fake_genai_module.Client = FakeClient
    fake_genai_types = types.SimpleNamespace(UploadFileConfig=FakeUploadFileConfig)
    fake_genai_module.types = fake_genai_types

    fake_google_module = types.ModuleType("google")
    fake_google_module.genai = fake_genai_module

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai_module)
    monkeypatch.setattr(reel_gemini_engine, "REEL_VISION_EVALUATION_PROMPT", sentinel_prompt)
    monkeypatch.setattr(reel_gemini_engine.time, "sleep", lambda *_args, **_kwargs: None)

    payload = reel_gemini_engine._upload_and_analyse(api_key="test-key", video_bytes=b"fake-video")

    assert captured_contents[0] == sentinel_prompt
    assert payload["hook_strength_score"] == 0.78
    assert payload["audio_visual_sync"] == 0.74
