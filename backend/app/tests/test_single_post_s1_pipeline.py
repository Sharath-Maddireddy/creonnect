"""Integration-ish tests for S1 wiring in single-post insights pipeline."""

import asyncio
import json
import socket
import sys
import types
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import pytest

from backend.app.domain.post_models import (
    BenchmarkMetrics,
    CaptionEffectivenessScore,
    ContentClarityScore,
    CoreMetrics,
    DerivedMetrics,
    SinglePostInsights,
    VisualQualityScore,
)
from backend.app.services import ai_analysis_service
from backend.app.services.post_insights_service import build_single_post_insights


def test_failed_vision_result_is_not_cacheable() -> None:
    assert ai_analysis_service._should_cache_analysis_result({"vision_status": "error"}) is False
    assert ai_analysis_service._should_cache_analysis_result({"vision_status": "ok"}) is True


def _build_post(
    media_id: str,
    reach: int,
    engagement_rate: float,
    media_url: str | None = None,
    caption_text: str = "",
) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_1",
        media_id=media_id,
        media_url=media_url,
        media_type="IMAGE",
        caption_text=caption_text,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        core_metrics=CoreMetrics(
            reach=reach,
            impressions=reach + 200,
            likes=120,
            comments=20,
            saves=15,
            shares=10,
            profile_visits=8,
            website_taps=2,
        ),
        derived_metrics=DerivedMetrics(engagement_rate=engagement_rate),
        benchmark_metrics=BenchmarkMetrics(),
    )


def test_build_single_post_insights_includes_s1(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    captured_prompts: list[dict[str, str]] = []

    async def fake_run_vision_analysis(post: SinglePostInsights) -> dict[str, object]:
        return {
            "provider": "gemini",
            "status": "ok",
            "signals": [
                {
                    "objects": ["person", "laptop"],
                    "primary_objects": ["person", "laptop"],
                    "dominant_focus": "person",
                    "detected_text": "Build in public",
                    "hook_strength_score": 0.88,
                    "scene_description": "Person presenting content",
                    "visual_style": "clean",
                }
            ],
        }

    async def fake_call_llm_async(prompt: dict[str, str], llm_client):
        captured_prompts.append(prompt)
        return json.dumps(
            {
                "summary": "Strong post performance with clear visual hook and above-average engagement.",
                "drivers": [
                    {
                        "id": "d1",
                        "label": "Strong hook",
                        "type": "POSITIVE",
                        "explanation": "hook_strength_score is high.",
                    }
                ],
                "recommendations": [
                    {
                        "id": "r1",
                        "text": "Repeat this framing style in upcoming posts.",
                        "impact_level": "MEDIUM",
                    }
                ],
            }
        )

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", fake_run_vision_analysis)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", fake_call_llm_async)

    target_post = _build_post(
        "m_target",
        reach=2000,
        engagement_rate=0.07,
        media_url="https://example.com/post.jpg",
        caption_text="Build in public and save this workflow.",
    )
    history = [
        _build_post("m_1", reach=1500, engagement_rate=0.05),
        _build_post("m_2", reach=1700, engagement_rate=0.06),
        _build_post("m_3", reach=1900, engagement_rate=0.08),
    ]

    response = asyncio.run(build_single_post_insights(target_post=target_post, historical_posts=history, run_ai=True))

    assert response["post"].visual_quality_score.total > 0.0
    assert response["post"].content_clarity_score.total > 0.0
    assert response["ai_analysis"] is not None
    assert response["ai_analysis"]["visual_quality_score"]["total"] == response["post"].visual_quality_score.total
    assert response["ai_analysis"]["content_clarity_score"]["total"] == response["post"].content_clarity_score.total
    assert captured_prompts

    prompt_user_payload = json.loads(captured_prompts[0]["user"])
    assert "s1_visual_quality" in prompt_user_payload["context"]
    assert "s3_content_clarity" in prompt_user_payload["context"]
    assert prompt_user_payload["context"]["s1_visual_quality"]["total"] == response["post"].visual_quality_score.total
    assert prompt_user_payload["context"]["s3_content_clarity"]["total"] == response["post"].content_clarity_score.total


def test_run_vision_analysis_reads_gemini_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-visible")

    async def fake_generate_gemini_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
        assert api_key == "test-key-visible"
        assert isinstance(instruction, str) and instruction
        assert media_url == "https://example.com/post.jpg"
        return json.dumps(
            {
                "visual_quality_score": 7,
                "primary_objects": ["person"],
                "detected_text": None,
                "hook_strength_score": 0.75,
                "lighting_feedback": "Subject is slightly underexposed",
                "composition_feedback": "Good rule of thirds, but background is cluttered",
                "aesthetic_fixes": ["Increase brightness by 10%", "Crop closer to the main subject"],
                "is_cringe": False,
                "adult_content_detected": False,
            }
        )

    monkeypatch.setattr(ai_analysis_service, "_generate_gemini_vision_json", fake_generate_gemini_vision_json)

    post = _build_post(
        "m_vision_env",
        reach=1000,
        engagement_rate=0.05,
        media_url="https://example.com/post.jpg",
    )
    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert result["status"] == "ok"
    assert isinstance(result["signals"], list)
    assert result["signals"][0]["technical_flaws"] == [
        "Subject is slightly underexposed",
        "Good rule of thirds, but background is cluttered",
    ]
    assert result["signals"][0]["aesthetic_fixes"] == [
        "Increase brightness by 10%",
        "Crop closer to the main subject",
    ]
    assert result["signals"][0]["visual_quality_score"]["composition"] == 7.0


def test_call_gemini_vision_api_uses_inline_media_when_google_genai_client_is_missing(monkeypatch) -> None:
    class FakeLegacyModel:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def generate_content(self, contents: list[object], generation_config=None):
            assert contents[0]
            assert contents[1]["mime_type"] == "image/jpeg"
            assert contents[1]["data"] == b"image-bytes"
            return types.SimpleNamespace(
                text=json.dumps(
                    {
                        "objects": ["person"],
                        "scene_description": "Person presenting",
                        "detected_text": None,
                        "visual_style": "clean",
                        "hook_strength_score": 0.75,
                    }
                )
            )

    fake_genai_module = types.ModuleType("google.genai")
    fake_genai_types_module = types.ModuleType("google.genai.types")
    fake_genai_module.types = fake_genai_types_module

    fake_legacy_genai = types.ModuleType("google.generativeai")
    fake_legacy_genai.configure = lambda **_kwargs: None
    fake_legacy_genai.types = types.SimpleNamespace(GenerationConfig=lambda **kwargs: kwargs)
    fake_legacy_genai.GenerativeModel = FakeLegacyModel

    fake_google_module = types.ModuleType("google")
    fake_google_module.__path__ = []
    fake_google_module.genai = fake_genai_module

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_genai_types_module)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_legacy_genai)
    monkeypatch.setattr(ai_analysis_service, "_download_vision_media", lambda _url: (b"image-bytes", "image/jpeg"))

    text = ai_analysis_service._call_gemini_vision_api(
        api_key="test-key",
        instruction="Describe this image",
        media_url="https://example.com/post.jpg",
    )

    payload = json.loads(text)
    assert payload["scene_description"] == "Person presenting"


_PUBLIC_TEST_IP = "8.8.8.8"


class _VisionResponse:
    def __init__(
        self,
        status_code: int = 200,
        *,
        location: str | None = None,
        content_type: str = "image/jpeg",
        chunks: tuple[bytes, ...] = (b"image-bytes",),
    ) -> None:
        self.status_code = status_code
        headers = {"content-type": content_type}
        if location is not None:
            headers["location"] = location
        self.headers = ai_analysis_service.httpx.Headers(headers)
        self._chunks = chunks

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_bytes(self, _chunk_size: int):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _VisionClient:
    def __init__(self, routes: dict[str, _VisionResponse]) -> None:
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
        return self.routes[public_url]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _mock_vision_network(
    monkeypatch,
    *,
    dns: dict[str, list[str]],
    routes: dict[str, _VisionResponse],
) -> _VisionClient:
    def getaddrinfo(hostname, *_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))
            for address in dns[hostname]
        ]

    client = _VisionClient(routes)

    def client_factory(*, timeout, follow_redirects, trust_env, limits):
        assert timeout == ai_analysis_service.VISION_MEDIA_DOWNLOAD_TIMEOUT_SECONDS
        assert follow_redirects is False
        assert trust_env is False
        assert limits.max_keepalive_connections == 0
        return client

    monkeypatch.setattr(ai_analysis_service.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(ai_analysis_service.httpx, "Client", client_factory)
    return client


def test_download_vision_media_follows_validated_relative_redirect(monkeypatch) -> None:
    start = "https://instagram.example/posts/source.jpg"
    target = "https://instagram.example/images/final.jpg"
    client = _mock_vision_network(
        monkeypatch,
        dns={"instagram.example": [_PUBLIC_TEST_IP]},
        routes={
            start: _VisionResponse(302, location="../images/final.jpg"),
            target: _VisionResponse(chunks=(b"image-bytes",)),
        },
    )

    media_bytes, mime_type = ai_analysis_service._download_vision_media(start)

    assert client.calls == [start, target]
    assert client.connection_calls == [
        f"https://{_PUBLIC_TEST_IP}/posts/source.jpg",
        f"https://{_PUBLIC_TEST_IP}/images/final.jpg",
    ]
    assert client.request_security == [
        ("instagram.example", "instagram.example"),
        ("instagram.example", "instagram.example"),
    ]
    assert media_bytes == b"image-bytes"
    assert mime_type == "image/jpeg"


def test_run_vision_analysis_aggregates_carousel_slides_with_bounded_fanout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _public_host(_hostname: str) -> bool:
        return True

    async def _vision_signal(*, media_url: str, **_kwargs):
        index = 1 if media_url.endswith("slide-1.jpg") else 2
        return {
            "objects": [f"object-{index}"],
            "primary_objects": [f"object-{index}"],
            "hook_strength_score": 0.4 + index / 10,
            "virality_potential": 4 + index,
            "visual_quality_score": {"composition": float(5 + index)},
            "technical_flaws": [f"flaw-{index}"],
            "aesthetic_fixes": [f"fix-{index}"],
            "cringe_signals": [],
            "cringe_fixes": [],
            "cringe_score": 10 * index,
            "is_cringe": False,
            "adult_content_detected": False,
        }

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_analysis_service, "_is_safe_public_hostname", _public_host)
    monkeypatch.setattr(ai_analysis_service, "_retry_parse_with_retry_only", _vision_signal)
    post = _build_post("carousel_1", reach=100, engagement_rate=0.1, media_url="https://cdn.example/slide-1.jpg")
    post.media_type = "CAROUSEL"
    post.carousel_media_urls = ["https://cdn.example/slide-1.jpg", "https://cdn.example/slide-2.jpg"]

    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert result["status"] == "ok"
    assert len(result["signals"]) == 3
    assert result["signals"][0]["is_carousel_aggregate"] is True
    assert result["signals"][0]["hook_strength_score"] == pytest.approx(0.55)
    assert [signal["slide_index"] for signal in result["signals"][1:]] == [1, 2]

@pytest.mark.parametrize(
    "private_ip",
    ["127.0.0.1", "10.0.0.4", "100.64.0.1", "169.254.169.254", "::1"],
)
def test_download_vision_media_rejects_private_initial_host(monkeypatch, private_ip: str) -> None:
    url = "https://private.example/image.jpg"
    client = _mock_vision_network(
        monkeypatch,
        dns={"private.example": [private_ip]},
        routes={},
    )

    with pytest.raises(ValueError, match="public HTTP or HTTPS"):
        ai_analysis_service._download_vision_media(url)

    assert client.calls == []


def test_download_vision_media_rejects_mixed_public_private_dns(monkeypatch) -> None:
    url = "https://mixed.example/image.jpg"
    client = _mock_vision_network(
        monkeypatch,
        dns={"mixed.example": [_PUBLIC_TEST_IP, "10.0.0.4"]},
        routes={},
    )

    with pytest.raises(ValueError, match="public HTTP or HTTPS"):
        ai_analysis_service._download_vision_media(url)

    assert client.calls == []


def test_download_vision_media_rejects_private_redirect_before_request(monkeypatch) -> None:
    start = "https://instagram.example/post.jpg"
    private_target = "http://metadata.internal/latest/meta-data/"
    client = _mock_vision_network(
        monkeypatch,
        dns={
            "instagram.example": [_PUBLIC_TEST_IP],
            "metadata.internal": ["169.254.169.254"],
        },
        routes={start: _VisionResponse(302, location=private_target)},
    )

    with pytest.raises(ValueError, match="public HTTP or HTTPS"):
        ai_analysis_service._download_vision_media(start)

    assert client.calls == [start]


def test_download_vision_media_rejects_missing_location_and_redirect_overflow(monkeypatch) -> None:
    missing = "https://cdn.example/missing.jpg"
    client = _mock_vision_network(
        monkeypatch,
        dns={"cdn.example": [_PUBLIC_TEST_IP]},
        routes={missing: _VisionResponse(302, location=None)},
    )
    with pytest.raises(ValueError, match="missing a Location"):
        ai_analysis_service._download_vision_media(missing)

    urls = [f"https://cdn.example/{index}.jpg" for index in range(5)]
    client.routes = {
        urls[index]: _VisionResponse(302, location=urls[index + 1])
        for index in range(4)
    }
    client.calls.clear()
    with pytest.raises(ValueError, match="exceeded 3 redirects"):
        ai_analysis_service._download_vision_media(urls[0])
    assert client.calls == urls[:4]


def test_download_vision_media_preserves_type_and_size_limits(monkeypatch) -> None:
    oversized = "https://cdn.example/large.jpg"
    wrong_type = "https://cdn.example/not-image.jpg"
    _mock_vision_network(
        monkeypatch,
        dns={"cdn.example": [_PUBLIC_TEST_IP]},
        routes={
            oversized: _VisionResponse(chunks=(b"1234", b"5678")),
            wrong_type: _VisionResponse(content_type="text/html"),
        },
    )
    monkeypatch.setattr(ai_analysis_service, "MAX_VISION_MEDIA_BYTES", 6)

    with pytest.raises(ValueError, match="15 MB limit"):
        ai_analysis_service._download_vision_media(oversized)
    with pytest.raises(ValueError, match="Unsupported vision media type"):
        ai_analysis_service._download_vision_media(wrong_type)


def test_run_vision_analysis_routes_reels_to_video_engine(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_analysis_service,
        "run_reel_gemini_analysis",
        lambda media_url: {
            "status": "ok",
            "signals": {
                "hook_frame_score": 0.82,
                "retention_signal": 0.7,
                "objects": ["creator", "product"],
                "scene_description": "Creator demonstrates a product.",
                "visual_style": "tutorial",
            },
        },
    )
    post = _build_post("m_reel", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.mp4")
    post.media_type = "REEL"

    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert result["status"] == "ok"
    assert result["signals"][0]["objects"] == ["creator", "product"]
    assert result["signals"][0]["hook_strength_score"] == 0.82


def test_run_vision_analysis_reel_times_out_instead_of_hanging(monkeypatch) -> None:
    """Regression: the reel vision call previously had no timeout at all --
    a slow/stuck Gemini call (e.g. a 429 backoff storm) could hang a
    synchronous /post-analysis request for several minutes."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_analysis_service, "REEL_VISION_TIMEOUT_SECONDS", 0.05)

    def _slow_reel_analysis(media_url: str):
        import time as _time
        _time.sleep(0.3)
        return {"status": "ok", "signals": {"hook_frame_score": 0.5}}

    monkeypatch.setattr(ai_analysis_service, "run_reel_gemini_analysis", _slow_reel_analysis)
    post = _build_post("m_reel_timeout", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.mp4")
    post.media_type = "REEL"

    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert result["status"] == "error"
    assert "timed out" in result["error_reason"]


def test_run_vision_analysis_reel_scales_virality_and_preserves_raw_signals(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_analysis_service,
        "run_reel_gemini_analysis",
        lambda media_url: {
            "status": "ok",
            "signals": {
                "hook_frame_score": 0.82,
                "retention_signal": 0.7,
                "pacing_label": "fast",
                "objects": ["creator", "product"],
                "scene_description": "Creator demonstrates a product.",
                "visual_style": "tutorial",
            },
        },
    )
    post = _build_post("m_reel_raw", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.mp4")
    post.media_type = "REEL"

    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    # retention_signal is 0..1; virality_potential is a 0..10 scale field.
    assert result["signals"][0]["virality_potential"] == 7.0
    assert result["raw_reel_signals"]["pacing_label"] == "fast"
    assert result["raw_reel_signals"]["retention_signal"] == 0.7


def test_analyze_single_post_ai_populates_reel_analysis_for_reel(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    monkeypatch.setenv("AI_EXTERNAL_CALLS_ENABLED", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    async def _unexpected_call(*_args, **_kwargs):
        raise AssertionError("external AI call should not run when disabled")

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", _unexpected_call)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", _unexpected_call)
    monkeypatch.setattr(ai_analysis_service, "analyze_content_clarity_via_llm", _unexpected_call)
    monkeypatch.setattr(ai_analysis_service, "analyze_audience_relevance_via_llm", _unexpected_call)

    post = _build_post("m_reel_analysis", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.mp4")
    post.media_type = "REEL"
    post.audio_name = "Trending Beat"

    asyncio.run(ai_analysis_service.analyze_single_post_ai(post))

    assert post.reel_analysis is not None
    assert post.reel_analysis.total is not None
    # AI_EXTERNAL_CALLS_ENABLED=0 short-circuits vision to a disabled VisionAnalysis
    # whose `status` field is hardcoded "error" (pre-existing behavior); reel_analysis
    # reflects that literal status string, not the outer vision_status variable.
    assert post.reel_analysis.reel_vision_status == "error"


def test_fallback_reason_distinguishes_post_too_new(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    post = _build_post("m_too_new", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.jpg")
    post.published_at = datetime.now(timezone.utc)

    result = asyncio.run(ai_analysis_service.analyze_single_post_ai(post))

    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "post_too_new"


def test_fallback_reason_distinguishes_vision_and_coaching_disabled(monkeypatch) -> None:
    ai_analysis_service._ANALYSIS_CACHE.clear()
    monkeypatch.setenv("AI_EXTERNAL_CALLS_ENABLED", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    async def _unexpected_call(*_args, **_kwargs):
        raise AssertionError("external AI call should not run when disabled")

    monkeypatch.setattr(ai_analysis_service, "run_vision_analysis", _unexpected_call)
    monkeypatch.setattr(ai_analysis_service, "_call_llm_async", _unexpected_call)
    monkeypatch.setattr(ai_analysis_service, "analyze_content_clarity_via_llm", _unexpected_call)
    monkeypatch.setattr(ai_analysis_service, "analyze_audience_relevance_via_llm", _unexpected_call)

    post = _build_post("m_disabled_reason", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.jpg")
    result = asyncio.run(ai_analysis_service.analyze_single_post_ai(post))

    assert result["fallback_reason"] == "coaching_disabled,vision_disabled"


def test_cringe_constants_are_single_sourced() -> None:
    """post_models must import (not redefine) cringe thresholds to avoid drift."""
    from backend.app.ai import cringe_analysis
    from backend.app.domain import post_models

    assert post_models.CRINGE_DETECTION_THRESHOLD is cringe_analysis.CRINGE_DETECTION_THRESHOLD
    assert post_models.CRINGE_NOT_CRINGE_MAX is cringe_analysis.CRINGE_NOT_CRINGE_MAX
    assert post_models.CRINGE_UNCERTAIN_MAX is cringe_analysis.CRINGE_UNCERTAIN_MAX


def test_fallback_recommendations_are_present_when_coaching_llm_fails() -> None:
    recommendations = ai_analysis_service._fallback_recommendations(
        VisualQualityScore(total=20.0),
        CaptionEffectivenessScore(total_0_50=20.0),
        ContentClarityScore(total=20.0),
    )

    assert len(recommendations) == 3
    assert {item["category"] for item in recommendations} == {"VISUAL", "CAPTION"}


def test_run_vision_analysis_recovers_malformed_output_with_simplified_prompt(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-visible")
    calls: list[str] = []

    async def fake_generate_gemini_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
        assert api_key == "test-key-visible"
        assert media_url == "https://example.com/post.jpg"
        calls.append(instruction)
        if len(calls) == 1:
            return "scene_description Person presenting\n  broken indentation"
        assert instruction == ai_analysis_service._SIMPLIFIED_GEMINI_VISION_PROMPT
        return json.dumps(
            {
                "visual_quality_score": 6,
                "primary_objects": ["person"],
                "detected_text": None,
                "hook_strength_score": 0.75,
                "lighting_feedback": "Light is a little flat",
                "composition_feedback": "Center framing feels static",
                "aesthetic_fixes": ["Add contrast", "Reframe slightly off-center"],
                "is_cringe": True,
                "adult_content_detected": False,
            }
        )

    monkeypatch.setattr(ai_analysis_service, "_generate_gemini_vision_json", fake_generate_gemini_vision_json)

    post = _build_post("m_repair", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.jpg")
    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert len(calls) == 2
    assert result["status"] == "ok"
    assert result["signals"][0]["primary_objects"] == ["person"]
    assert result["signals"][0]["technical_flaws"] == [
        "Light is a little flat",
        "Center framing feels static",
    ]
    assert result["signals"][0]["is_cringe"] is True


def test_run_vision_analysis_recovers_malformed_openai_output_with_simplified_prompt(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    calls: list[str] = []

    async def fake_generate_openai_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
        assert api_key == "openai-test-key"
        assert media_url == "https://example.com/post.jpg"
        calls.append(instruction)
        if len(calls) == 1:
            return "scene_description Person presenting\n  broken indentation"
        assert instruction == ai_analysis_service._SIMPLIFIED_GEMINI_VISION_PROMPT
        return json.dumps(
            {
                "visual_quality_score": 8,
                "primary_objects": ["person", "laptop"],
                "detected_text": "Build in public",
                "hook_strength_score": 0.8,
                "lighting_feedback": "Clean lighting",
                "composition_feedback": "Balanced framing",
                "aesthetic_fixes": ["Tighten crop"],
                "is_cringe": False,
                "adult_content_detected": False,
            }
        )

    monkeypatch.setattr(ai_analysis_service, "_generate_openai_vision_json", fake_generate_openai_vision_json)

    post = _build_post("m_openai_repair", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.jpg")
    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert len(calls) == 2
    assert result["provider"] == "openai"
    assert result["status"] == "ok"
    assert result["signals"][0]["primary_objects"] == ["person", "laptop"]
    assert result["signals"][0]["technical_flaws"] == ["Clean lighting", "Balanced framing"]
    assert result["signals"][0]["aesthetic_fixes"] == ["Tighten crop"]


def test_run_vision_analysis_uses_azure_as_image_fallback(monkeypatch) -> None:
    """Azure-only deployments must not lose vision fallback coverage."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-test-key")

    async def fake_generate_openai_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
        assert api_key == "azure-test-key"
        return json.dumps({"visual_quality_score": 8, "primary_objects": ["person"]})

    monkeypatch.setattr(ai_analysis_service, "_generate_openai_vision_json", fake_generate_openai_vision_json)

    post = _build_post("m_azure_fallback", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.jpg")
    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert result["provider"] == "openai"
    assert result["status"] == "ok"
    assert result["signals"][0]["primary_objects"] == ["person"]


def test_run_vision_analysis_retries_with_simplified_prompt(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-visible")
    calls: list[str] = []

    async def fake_generate_gemini_vision_json(*, api_key: str, instruction: str, media_url: str) -> str:
        assert api_key == "test-key-visible"
        assert media_url == "https://example.com/post.jpg"
        calls.append(instruction)
        if len(calls) == 1:
            return ""
        assert instruction == ai_analysis_service._SIMPLIFIED_GEMINI_VISION_PROMPT
        return json.dumps(
            {
                "visual_quality_score": 5,
                "primary_objects": ["person"],
                "detected_text": None,
                "hook_strength_score": 0.55,
                "lighting_feedback": "Acceptable lighting but slightly dim",
                "composition_feedback": "Subject is clear but framing is generic",
                "aesthetic_fixes": [],
                "is_cringe": False,
                "adult_content_detected": False,
            }
        )

    monkeypatch.setattr(ai_analysis_service, "_generate_gemini_vision_json", fake_generate_gemini_vision_json)

    post = _build_post("m_retry", reach=1000, engagement_rate=0.05, media_url="https://example.com/post.jpg")
    result = asyncio.run(ai_analysis_service.run_vision_analysis(post))

    assert result["status"] == "ok"
    assert result["signals"][0]["visual_quality_score"]["lighting"] == 5.0
    assert len(calls) == 2
