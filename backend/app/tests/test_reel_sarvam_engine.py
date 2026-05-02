from __future__ import annotations

import backend.app.analytics.reel_sarvam_engine as reel_sarvam_engine


def test_transcribe_reel_audio_returns_none_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)

    assert reel_sarvam_engine.transcribe_reel_audio("https://example.com/reel.mp4") is None


def test_download_audio_aborts_when_size_cap_exceeded(monkeypatch) -> None:
    oversized_chunks = [b"a" * reel_sarvam_engine.MAX_AUDIO_BYTES, b"b"]

    class FakeStreamResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, _chunk_size: int):
            yield from oversized_chunks

        def __enter__(self) -> "FakeStreamResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            return None

        def stream(self, method: str, url: str) -> FakeStreamResponse:
            assert method == "GET"
            assert url == "https://example.com/reel.mp4"
            return FakeStreamResponse()

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

    monkeypatch.setattr(reel_sarvam_engine.httpx, "Client", FakeClient)

    assert reel_sarvam_engine._download_audio("https://example.com/reel.mp4") is None


def test_call_sarvam_stt_returns_transcript_on_success(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"transcript": "Namaste creators", "language_code": "hi-IN"}

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["data"] = kwargs.get("data")
        return FakeResponse()

    monkeypatch.setattr(reel_sarvam_engine.httpx, "post", fake_post)

    transcript = reel_sarvam_engine._call_sarvam_stt("sarvam-key", b"fake-audio")

    assert transcript == "Namaste creators"
    assert captured["url"] == reel_sarvam_engine.SARVAM_STT_ENDPOINT
    assert captured["headers"] == {"api-subscription-key": "sarvam-key"}
    assert captured["data"] == {
        "model": reel_sarvam_engine.SARVAM_MODEL,
        "mode": reel_sarvam_engine.SARVAM_MODE,
        "language_code": reel_sarvam_engine.SARVAM_LANGUAGE,
        "with_timestamps": "false",
    }


def test_transcribe_reel_audio_downloads_and_calls_sarvam(monkeypatch) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-key")
    monkeypatch.setattr(reel_sarvam_engine, "_download_audio", lambda url: b"audio-bytes")

    captured = {}

    def fake_call(api_key: str, audio_bytes: bytes, suffix: str = ".mp4") -> str:
        captured["api_key"] = api_key
        captured["audio_bytes"] = audio_bytes
        captured["suffix"] = suffix
        return "Transcript text"

    monkeypatch.setattr(reel_sarvam_engine, "_call_sarvam_stt", fake_call)

    result = reel_sarvam_engine.transcribe_reel_audio("https://example.com/reel.mp4")

    assert result == "Transcript text"
    assert captured == {
        "api_key": "sarvam-key",
        "audio_bytes": b"audio-bytes",
        "suffix": ".mp4",
    }
