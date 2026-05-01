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


def test_upload_and_analyse_fails_fast_when_upload_returns_no_name(monkeypatch) -> None:
    class FakeUploadFileConfig:
        def __init__(self, mime_type: str) -> None:
            self.mime_type = mime_type

    class FakeFilesApi:
        def upload(self, file, config):  # noqa: ANN001
            return types.SimpleNamespace()

        def get(self, name: str):  # pragma: no cover - should never be called
            raise AssertionError(f"files.get should not be called when upload has no name: {name!r}")

        def delete(self, name: str) -> None:  # pragma: no cover - should never be called
            raise AssertionError(f"files.delete should not be called when upload has no name: {name!r}")

    class FakeModelsApi:
        def generate_content(self, model: str, contents: list[object]):  # pragma: no cover - should never be called
            raise AssertionError("generate_content should not run when upload has no file name")

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

    try:
        reel_gemini_engine._upload_and_analyse(api_key="test-key", video_bytes=b"fake-video")
    except RuntimeError as exc:
        assert str(exc) == "Gemini upload did not return a file name."
    else:
        raise AssertionError("Expected RuntimeError when Gemini upload returns no file name")


def test_upload_and_analyse_falls_back_to_google_generativeai(monkeypatch) -> None:
    captured_contents: list[object] = []

    class FakeUploadedFile:
        name = "legacy-uploaded-file"

    class FakeLegacyModel:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def generate_content(self, contents: list[object]):
            captured_contents.extend(contents)
            return types.SimpleNamespace(
                text="""
hook_frame_score 0.55
hook_text_overlay Wait for it
pacing_label medium
cut_count_estimate 5
dominant_emotion surprise
retention_signal 0.61
audio_visual_sync 0.66
objects
  - creator
scene_description Creator gestures toward a reveal card
detected_text Big reveal
visual_style tutorial
hook_strength_score 0.64
cringe_score 14
cringe_signals
  - Slightly busy opening frame
cringe_fixes
  - Trim the first beat
production_level medium
adult_content_detected false
""".strip()
            )

    fake_legacy_genai = types.ModuleType("google.generativeai")
    fake_legacy_genai.configure = lambda **_kwargs: None
    fake_legacy_genai.upload_file = lambda _file_obj, mime_type=None: FakeUploadedFile()
    fake_legacy_genai.get_file = lambda _name: types.SimpleNamespace(name="legacy-uploaded-file", state="ACTIVE")
    fake_legacy_genai.delete_file = lambda _name: None
    fake_legacy_genai.GenerativeModel = FakeLegacyModel

    fake_google_module = types.ModuleType("google")
    fake_google_module.__path__ = []

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.delitem(sys.modules, "google.genai", raising=False)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_legacy_genai)
    monkeypatch.setattr(reel_gemini_engine.time, "sleep", lambda *_args, **_kwargs: None)

    payload = reel_gemini_engine._upload_and_analyse(api_key="test-key", video_bytes=b"fake-video")

    assert captured_contents[0] == REEL_VISION_EVALUATION_PROMPT
    assert payload["hook_strength_score"] == 0.64
    assert payload["audio_visual_sync"] == 0.66
