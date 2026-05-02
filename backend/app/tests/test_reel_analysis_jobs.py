from __future__ import annotations

import backend.app.services.reel_analysis_jobs as reel_analysis_jobs


def _install_status_store(monkeypatch) -> dict[str, dict]:
    store: dict[str, dict] = {}

    def fake_set_json(key: str, payload: dict, ttl_seconds: int | None = None) -> None:  # noqa: ARG001
        store[key] = payload

    def fake_get_json(key: str) -> dict | None:
        return store.get(key)

    monkeypatch.setattr(reel_analysis_jobs, "set_json", fake_set_json)
    monkeypatch.setattr(reel_analysis_jobs, "get_json", fake_get_json)
    monkeypatch.setattr(reel_analysis_jobs, "get_current_job", lambda: None)
    return store


def test_run_reel_analysis_job_persists_transcript_and_ok_status(monkeypatch) -> None:
    store = _install_status_store(monkeypatch)
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-key")

    monkeypatch.setattr(
        reel_analysis_jobs,
        "run_reel_gemini_analysis",
        lambda media_url: {
            "status": "ok",
            "signals": {"hook_frame_score": 0.9, "pacing_label": "fast", "retention_signal": 0.7},
        },
    )
    monkeypatch.setattr(reel_analysis_jobs, "transcribe_reel_audio", lambda media_url: "Comment below for part 2")

    payload = {
        "job_id": "job-ok",
        "media_url": "https://example.com/reel.mp4",
        "audio_name": "original audio",
        "caption_text": "Short caption",
        "watch_time_pct": 0.55,
    }

    reel_analysis_jobs.run_reel_analysis_job(payload)

    status = store[reel_analysis_jobs._job_key("job-ok")]
    assert status["status"] == "succeeded"
    assert status["error"] is None
    assert status["result"]["spoken_transcript"] == "Comment below for part 2"
    assert status["result"]["sarvam_transcription_status"] == "ok"
    assert "Sarvam STT transcript applied." in status["result"]["notes"]
    assert status["result"]["raw_vision_signals"]["hook_frame_score"] == 0.9


def test_run_reel_analysis_job_marks_sarvam_error_when_transcription_fails(monkeypatch) -> None:
    store = _install_status_store(monkeypatch)
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-key")

    monkeypatch.setattr(
        reel_analysis_jobs,
        "run_reel_gemini_analysis",
        lambda media_url: {
            "status": "ok",
            "signals": {"hook_frame_score": 0.4, "pacing_label": "medium", "retention_signal": 0.5},
        },
    )

    def fake_transcribe(media_url: str) -> str | None:
        raise RuntimeError("sarvam transport failed")

    monkeypatch.setattr(reel_analysis_jobs, "transcribe_reel_audio", fake_transcribe)

    payload = {
        "job_id": "job-error",
        "media_url": "https://example.com/reel.mp4",
        "audio_name": "original audio",
        "caption_text": "Short caption",
        "watch_time_pct": 0.40,
    }

    reel_analysis_jobs.run_reel_analysis_job(payload)

    status = store[reel_analysis_jobs._job_key("job-error")]
    assert status["status"] == "succeeded"
    assert status["result"]["spoken_transcript"] is None
    assert status["result"]["sarvam_transcription_status"] == "error"


def test_run_reel_analysis_job_marks_sarvam_disabled_without_api_key(monkeypatch) -> None:
    store = _install_status_store(monkeypatch)
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)

    monkeypatch.setattr(
        reel_analysis_jobs,
        "run_reel_gemini_analysis",
        lambda media_url: {
            "status": "ok",
            "signals": {"hook_frame_score": 0.5, "pacing_label": "medium", "retention_signal": 0.5},
        },
    )
    monkeypatch.setattr(reel_analysis_jobs, "transcribe_reel_audio", lambda media_url: None)

    payload = {
        "job_id": "job-disabled",
        "media_url": "https://example.com/reel.mp4",
        "audio_name": "original audio",
        "caption_text": "Short caption",
    }

    reel_analysis_jobs.run_reel_analysis_job(payload)

    status = store[reel_analysis_jobs._job_key("job-disabled")]
    assert status["status"] == "succeeded"
    assert status["result"]["sarvam_transcription_status"] == "disabled"
