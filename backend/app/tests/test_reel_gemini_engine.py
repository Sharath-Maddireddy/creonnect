from __future__ import annotations

import socket
import sys
import types
from urllib.parse import urlsplit, urlunsplit

import pytest

import backend.app.analytics.reel_gemini_engine as reel_gemini_engine
from backend.app.ai.prompts import REEL_VISION_EVALUATION_PROMPT


def test_reel_prompt_forces_valid_json_output() -> None:
    assert "Return ONLY one valid JSON object. No markdown. No prose. No reasoning. No filler." in REEL_VISION_EVALUATION_PROMPT
    assert "Use the shortest possible labels, especially for enums" in REEL_VISION_EVALUATION_PROMPT
    assert "Return a bare JSON object only." in REEL_VISION_EVALUATION_PROMPT


def test_reel_model_names_are_explicit() -> None:
    assert reel_gemini_engine.PRIMARY_REEL_MODEL == "gemini-2.5-flash-lite"
    assert reel_gemini_engine.FALLBACK_REEL_MODEL == "gemini-flash-lite-latest"

def test_analyse_reel_inline_sends_video_bytes_and_fps(monkeypatch) -> None:
    captured_calls: list[dict[str, object]] = []
    sentinel_prompt = "REEL PROMPT SENTINEL"

    class FakeBlob:
        def __init__(self, data: bytes, mime_type: str) -> None:
            self.data = data
            self.mime_type = mime_type

    class FakeVideoMetadata:
        def __init__(self, fps: float) -> None:
            self.fps = fps

    class FakePart:
        def __init__(self, inline_data, video_metadata) -> None:
            self.inline_data = inline_data
            self.video_metadata = video_metadata

    class FakeModelsApi:
        def generate_content(self, model: str, contents: list[object], config=None):  # noqa: ARG002
            captured_calls.append({"model": model, "contents": contents, "config": config})
            return types.SimpleNamespace(
                text="""
hook_frame_score 0.72
hook_text_overlay Stop scrolling
pacing_label fast
cut_count_estimate 11
dominant_emotion curiosity
retention_signal 0.68
audio_visual_sync 0.74
audio_type music
is_silent false
hook_audio_present true
audio_quality_score 8.0
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
            self.models = FakeModelsApi()

    fake_genai_module = types.ModuleType("google.genai")
    fake_genai_module.Client = FakeClient
    fake_genai_types = types.SimpleNamespace(
        Blob=FakeBlob,
        VideoMetadata=FakeVideoMetadata,
        Part=FakePart,
        GenerateContentConfig=lambda **kwargs: kwargs,
    )
    fake_genai_module.types = fake_genai_types

    fake_google_module = types.ModuleType("google")
    fake_google_module.genai = fake_genai_module

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai_module)
    monkeypatch.setattr(reel_gemini_engine, "REEL_VISION_EVALUATION_PROMPT", sentinel_prompt)
    monkeypatch.setattr(reel_gemini_engine.time, "sleep", lambda *_args, **_kwargs: None)

    payload = reel_gemini_engine._analyse_reel_inline(api_key="test-key", video_bytes=b"fake-video", fps=3.0)

    assert payload["hook_strength_score"] == 0.78
    assert payload["audio_visual_sync"] == 0.74
    assert payload["audio_quality_score"] == 8.0

    contents = captured_calls[0]["contents"]
    assert contents[0] == sentinel_prompt
    video_part = contents[1]
    assert video_part.inline_data.data == b"fake-video"
    assert video_part.inline_data.mime_type == "video/mp4"
    assert video_part.video_metadata.fps == 3.0
    assert captured_calls[0]["config"]["response_mime_type"] == "application/json"


def test_analyse_reel_inline_falls_back_to_google_generativeai(monkeypatch) -> None:
    captured_contents: list[object] = []

    class FakeLegacyModel:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def generate_content(self, contents: list[object], generation_config=None):
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
    fake_legacy_genai.types = types.SimpleNamespace(GenerationConfig=lambda **kwargs: kwargs)
    fake_legacy_genai.GenerativeModel = FakeLegacyModel

    fake_google_module = types.ModuleType("google")
    fake_google_module.__path__ = []

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.delitem(sys.modules, "google.genai", raising=False)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_legacy_genai)
    monkeypatch.setattr(reel_gemini_engine.time, "sleep", lambda *_args, **_kwargs: None)

    payload = reel_gemini_engine._analyse_reel_inline(api_key="test-key", video_bytes=b"fake-video", fps=3.0)

    assert captured_contents[0] == REEL_VISION_EVALUATION_PROMPT
    # Legacy SDK path has no video_metadata/fps equivalent -- inline bytes
    # are still sent, just without frame-rate control.
    assert captured_contents[1] == {"mime_type": "video/mp4", "data": b"fake-video"}
    assert payload["hook_strength_score"] == 0.64
    assert payload["audio_visual_sync"] == 0.66


def test_run_reel_gemini_analysis_uses_configured_fps(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(reel_gemini_engine, "_download_reel", lambda media_url: b"fake-video")

    captured_fps: list[float] = []

    def _fake_analyse(*, api_key: str, video_bytes: bytes, fps: float):
        captured_fps.append(fps)
        return {"hook_frame_score": 0.5}

    monkeypatch.setattr(reel_gemini_engine, "_analyse_reel_inline", _fake_analyse)
    monkeypatch.setattr(reel_gemini_engine, "REEL_VIDEO_FPS", 4.5)

    result = reel_gemini_engine.run_reel_gemini_analysis("https://example.com/reel.mp4")

    assert result["status"] == "ok"
    assert captured_fps == [4.5]


def test_analyse_reel_inline_retries_temporary_503(monkeypatch) -> None:
    calls: list[str] = []
    sleeps: list[int] = []

    class FakeAdapter:
        def __init__(self, api_key: str) -> None:
            assert api_key == "test-key"

        def generate_content(self, model_name: str, prompt_text: str, video_bytes: bytes, fps: float):
            calls.append(model_name)
            if len(calls) == 1:
                raise RuntimeError("503 UNAVAILABLE: high demand")
            return types.SimpleNamespace(text='{"hook_frame_score": 0.8}')

    monkeypatch.setattr(reel_gemini_engine, "_build_genai_adapter", lambda: FakeAdapter)
    monkeypatch.setattr(reel_gemini_engine.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = reel_gemini_engine._analyse_reel_inline(
        api_key="test-key",
        video_bytes=b"fake-video",
        fps=3.0,
    )

    assert result == {"hook_frame_score": 0.8}
    assert calls == [reel_gemini_engine.PRIMARY_REEL_MODEL] * 2
    assert sleeps == [5]


_PUBLIC_IPV4 = "8.8.8.8"
_PUBLIC_IPV6 = "2606:4700:4700::1111"


def _address(ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, 0, 0, 0) if family == socket.AF_INET6 else (ip, 0)
    return family, socket.SOCK_STREAM, 6, "", sockaddr


def _mock_dns(monkeypatch, records: dict[str, list[str]]) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda hostname, *_args, **_kwargs: [
            _address(ip) for ip in records[hostname]
        ],
    )


class _Response:
    def __init__(
        self,
        status_code: int = 200,
        *,
        location: str | None = None,
        chunks: tuple[bytes, ...] = (),
        error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = {"Location": location} if location is not None else {}
        self._chunks = chunks
        self._error = error

    def raise_for_status(self) -> None:
        if self._error:
            raise self._error
        if self.status_code >= 400:
            raise RuntimeError("http %d" % self.status_code)

    def iter_bytes(self, _chunk_size: int = 65536):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Client:
    def __init__(self, routes: dict[str, _Response | Exception]) -> None:
        self.routes = routes
        self.calls: list[str] = []
        self.connection_calls: list[str] = []
        self.request_security: list[tuple[str, str]] = []

    def stream(self, method: str, url: str, *, headers, extensions):
        assert method == "GET"
        parsed = urlsplit(url)
        public_url = urlunsplit((parsed.scheme, headers["Host"], parsed.path, parsed.query, ""))
        self.calls.append(public_url)
        self.connection_calls.append(url)
        self.request_security.append((headers["Host"], extensions["sni_hostname"]))
        result = self.routes[public_url]
        if isinstance(result, Exception):
            raise result
        return result

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _mock_client(monkeypatch, routes: dict[str, _Response | Exception]) -> _Client:
    client = _Client(routes)

    def factory(*, timeout, follow_redirects, trust_env, limits):
        assert timeout == reel_gemini_engine.REEL_DOWNLOAD_TIMEOUT_SEC
        assert follow_redirects is False
        assert trust_env is False
        assert limits.max_keepalive_connections == 0
        return client

    monkeypatch.setattr(reel_gemini_engine.httpx, "Client", factory)
    return client


def test_validate_public_reel_url_rejects_private_and_loopback(monkeypatch) -> None:
    records = {
        "localhost": ["127.0.0.1"],
        "private.test": ["10.0.0.23"],
        "link-local.test": ["169.254.1.1"],
        "lan.test": ["192.168.1.10"],
        "v6-loopback.test": ["::1"],
        "v6-private.test": ["fd12:3456:789a::1"],
        "mixed.test": [_PUBLIC_IPV4, "172.17.0.1"],
    }
    _mock_dns(monkeypatch, records)

    for hostname in records:
        with pytest.raises(ValueError):
            reel_gemini_engine._validate_public_reel_url(
                "https://%s/video.mp4" % hostname
            )


def test_validate_public_reel_url_accepts_public_http_https(monkeypatch) -> None:
    _mock_dns(
        monkeypatch,
        {
            "cdn.example.com": [_PUBLIC_IPV4],
            "dual.example.net": [_PUBLIC_IPV4, _PUBLIC_IPV6],
        },
    )

    for url in (
        "https://cdn.example.com/a.mp4",
        "http://dual.example.net/b.mov",
    ):
        assert reel_gemini_engine._validate_public_reel_url(url) == url

    for url in (
        "ftp://cdn.example.com/x.mp4",
        "file:///etc/passwd",
        "data:text/plain,hi",
        "https:///no-host.mp4",
    ):
        with pytest.raises(ValueError):
            reel_gemini_engine._validate_public_reel_url(url)


def test_download_reel_redirect_to_private_is_rejected_before_second_request(
    monkeypatch,
) -> None:
    start = "https://start.example/entry.mp4"
    private = "http://metadata.internal/latest/meta-data/"
    _mock_dns(
        monkeypatch,
        {
            "start.example": [_PUBLIC_IPV4],
            "metadata.internal": ["169.254.169.254"],
        },
    )
    client = _mock_client(monkeypatch, {start: _Response(302, location=private)})

    assert reel_gemini_engine._download_reel(start) is None
    assert client.calls == [start]


def test_download_reel_relative_public_redirect_is_followed(monkeypatch) -> None:
    start = "https://cdn.example/source/clip.mp4"
    target = "https://cdn.example/assets/final.mp4"
    _mock_dns(monkeypatch, {"cdn.example": [_PUBLIC_IPV4]})
    client = _mock_client(
        monkeypatch,
        {
            start: _Response(301, location="../assets/final.mp4"),
            target: _Response(chunks=(b"FAKE-MP4-DATA",)),
        },
    )

    assert reel_gemini_engine._download_reel(start) == b"FAKE-MP4-DATA"
    assert client.calls == [start, target]
    assert client.connection_calls == [
        f"https://{_PUBLIC_IPV4}/source/clip.mp4",
        f"https://{_PUBLIC_IPV4}/assets/final.mp4",
    ]
    assert client.request_security == [
        ("cdn.example", "cdn.example"),
        ("cdn.example", "cdn.example"),
    ]


def test_download_reel_more_than_three_redirects_fails(monkeypatch) -> None:
    urls = ["https://hop%d.test/v.mp4" % index for index in range(5)]
    _mock_dns(
        monkeypatch,
        {"hop%d.test" % index: [_PUBLIC_IPV4] for index in range(4)},
    )
    client = _mock_client(
        monkeypatch,
        {
            urls[index]: _Response(302, location=urls[index + 1])
            for index in range(4)
        },
    )

    assert reel_gemini_engine._download_reel(urls[0]) is None
    assert client.calls == urls[:4]


def test_download_reel_redirect_without_location_header_rejected(
    monkeypatch,
) -> None:
    url = "https://no-location.test/video.mp4"
    _mock_dns(monkeypatch, {"no-location.test": [_PUBLIC_IPV4]})
    client = _mock_client(monkeypatch, {url: _Response(302)})

    assert reel_gemini_engine._download_reel(url) is None
    assert client.calls == [url]


def test_download_reel_size_cap_and_generic_failure_contract_preserved(
    monkeypatch,
) -> None:
    urls = {
        "big": "https://big.test/video.mp4",
        "broken": "https://broken.test/video.mp4",
        "small": "https://small.test/video.mp4",
    }
    _mock_dns(
        monkeypatch,
        {
            "big.test": [_PUBLIC_IPV4],
            "broken.test": [_PUBLIC_IPV4],
            "small.test": [_PUBLIC_IPV4],
        },
    )
    monkeypatch.setattr(reel_gemini_engine, "MAX_VIDEO_BYTES", 100)
    _mock_client(
        monkeypatch,
        {
            urls["big"]: _Response(chunks=(b"X" * 64, b"Y" * 64)),
            urls["broken"]: _Response(error=RuntimeError("boom")),
            urls["small"]: _Response(chunks=(b"tiny-mp4",)),
        },
    )

    assert reel_gemini_engine._download_reel(urls["big"]) is None
    assert reel_gemini_engine._download_reel(urls["broken"]) is None
    assert reel_gemini_engine._download_reel(urls["small"]) == b"tiny-mp4"
