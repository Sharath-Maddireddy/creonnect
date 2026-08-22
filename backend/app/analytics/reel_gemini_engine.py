"""Gemini video analysis for Instagram Reels, sent inline (no File API)."""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from backend.app.ai.gemini_constants import FALLBACK_GEMINI_MODEL, PRIMARY_GEMINI_MODEL
from backend.app.ai.prompts import REEL_VISION_EVALUATION_PROMPT
from backend.app.ai.toon import loads_object as toon_loads_object
from backend.app.infra.outbound_media import resolve_public_http_url
from backend.app.utils.logger import logger


REEL_DOWNLOAD_TIMEOUT_SEC = 30.0
MAX_VIDEO_BYTES = 100 * 1024 * 1024
PRIMARY_REEL_MODEL = PRIMARY_GEMINI_MODEL
FALLBACK_REEL_MODEL = FALLBACK_GEMINI_MODEL


def _parse_reel_fps(env_key: str, default: float) -> float:
    raw = os.getenv(env_key, "")
    if not isinstance(raw, str) or not raw.strip():
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning("[ReelGemini] Invalid %s value=%r; falling back to default fps=%s", env_key, raw, default)
        return default


# Gemini's File API default is 1fps -- under-samples fast-cut short-form
# video (a typical reel cut happens well under a second). Reels are short
# (<=90s), so a higher fps stays within the inline-request token budget.
REEL_VIDEO_FPS = _parse_reel_fps("GEMINI_REEL_FPS", 3.0)


def _build_genai_adapter():
    """Return a small adapter over the installed Gemini SDK."""
    try:
        from google import genai
        from google.genai import types as genai_types

        class _GoogleGenaiAdapter:
            def __init__(self, api_key: str) -> None:
                self._client = genai.Client(api_key=api_key)

            def generate_content(self, model_name: str, prompt_text: str, video_bytes: bytes, fps: float):
                video_part = genai_types.Part(
                    inline_data=genai_types.Blob(data=video_bytes, mime_type="video/mp4"),
                    video_metadata=genai_types.VideoMetadata(fps=fps),
                )
                return self._client.models.generate_content(
                    model=model_name,
                    contents=[prompt_text, video_part],
                    # Deterministic scoring: without this Gemini's default
                    # temperature (1.0) produces run-to-run swings of 15-20
                    # points on the same video for identical prompts.
                    config=genai_types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                    ),
                )

        return _GoogleGenaiAdapter
    except ImportError:
        import google.generativeai as legacy_genai

        class _LegacyGenaiAdapter:
            def __init__(self, api_key: str) -> None:
                legacy_genai.configure(api_key=api_key)

            def generate_content(self, model_name: str, prompt_text: str, video_bytes: bytes, fps: float):
                # The legacy google-generativeai SDK has no video_metadata/fps
                # equivalent, so fps is best-effort here (falls back to
                # Gemini's default 1fps sampling on this path only).
                generation_config = legacy_genai.types.GenerationConfig(
                    temperature=0,
                    response_mime_type="application/json",
                )
                return legacy_genai.GenerativeModel(model_name).generate_content(
                    [prompt_text, {"mime_type": "video/mp4", "data": video_bytes}],
                    generation_config=generation_config,
                )

        return _LegacyGenaiAdapter


_MAX_REDIRECTS = 3


def _validate_public_reel_url(value: str) -> str:
    """Reject unsafe Reel URLs using the shared outbound-media policy."""
    return resolve_public_http_url(value, field_name="Reel media_url").public_url


def _download_reel(media_url: str) -> bytes | None:
    """Download reel bytes with pre-validated URLs and manual 3-hop redirects.

    httpx is configured with ``follow_redirects=False`` so every redirect
    target is re-validated (scheme + hostname + globally-routable DNS) via
    ``_validate_public_reel_url`` before a second TCP connection is opened.
    Relative ``Location`` headers are resolved with ``urllib.parse.urljoin``.
    Only the five well-defined HTTP redirect codes (301/302/303/307/308)
    trigger a redirect branch; any other 3xx is left to ``raise_for_status``
    so the existing ``download_failed`` contract absorbs it.
    """
    try:
        current_url = media_url
        remaining_hops = _MAX_REDIRECTS
        with httpx.Client(
            timeout=REEL_DOWNLOAD_TIMEOUT_SEC,
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            while True:
                target = resolve_public_http_url(current_url, field_name="Reel media_url")
                current_url = target.public_url
                with client.stream(
                    "GET",
                    target.connect_url,
                    headers=target.request_headers,
                    extensions=target.request_extensions,
                ) as response:
                    # Handle only the five well-defined HTTP redirect codes explicitly.
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if remaining_hops <= 0:
                            logger.warning(
                                "[ReelGemini] Reel download exceeded %d redirect hops.",
                                _MAX_REDIRECTS,
                            )
                            return None
                        location = response.headers.get("Location")
                        if not location:
                            logger.warning(
                                "[ReelGemini] Reel download got redirect %d without Location header.",
                                response.status_code,
                            )
                            return None
                        next_url = urljoin(current_url, location)
                        current_url = next_url
                        remaining_hops -= 1
                        # Exit the stream context immediately (no body drain)
                        # before the next iteration opens a fresh connection.
                        continue
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    total_bytes = 0
                    for chunk in response.iter_bytes(65536):
                        chunks.append(chunk)
                        total_bytes += len(chunk)
                        if total_bytes > MAX_VIDEO_BYTES:
                            logger.warning(
                                "[ReelGemini] Video exceeds size cap, aborting download."
                            )
                            return None
                    return b"".join(chunks)
    except Exception as exc:
        logger.warning("[ReelGemini] Download failed: %s", exc)
        return None


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) <= 1:
        return stripped
    if lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return "\n".join(lines[1:]).strip()


def _analyse_reel_inline(api_key: str, video_bytes: bytes, fps: float) -> dict[str, Any]:
    """Send reel bytes inline to Gemini and parse its analysis.

    No File API upload/poll cycle: the video rides in the same request as
    the prompt, the same way single-post image vision already works. This
    removes the slowest and most fragile part of reel analysis (uploading,
    polling for ACTIVE state, then deleting the hosted file) at the cost of
    re-sending the video bytes on every retry attempt instead of reusing an
    uploaded reference.
    """
    genai_adapter_cls = _build_genai_adapter()
    client = genai_adapter_cls(api_key=api_key)

    # Retry once per model for rate limits and short-lived provider overloads.
    _MODELS_TO_TRY = [PRIMARY_REEL_MODEL, FALLBACK_REEL_MODEL]
    last_exc: Exception | None = None
    response = None
    for model_name in _MODELS_TO_TRY:
        for attempt in range(2):  # 1 retry per model
            try:
                response = client.generate_content(
                    model_name,
                    REEL_VISION_EVALUATION_PROMPT,
                    video_bytes,
                    fps,
                )
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                msg = str(exc).upper()
                is_rate_limit = "429" in msg or "RESOURCE_EXHAUSTED" in msg
                is_temporary_provider_error = any(
                    token in msg
                    for token in ("500", "502", "503", "504", "UNAVAILABLE", "INTERNAL")
                )
                if attempt == 0 and (is_rate_limit or is_temporary_provider_error):
                    retry_delay = 35 if is_rate_limit else 5
                    logger.warning(
                        "[ReelGemini] Retryable error on %s; waiting %ss before retry: %s",
                        model_name,
                        retry_delay,
                        exc,
                    )
                    time.sleep(retry_delay)
                    continue
                break
        if last_exc is None:
            break  # Success

    if last_exc is not None or response is None:
        raise last_exc or RuntimeError("No response from Gemini.")

    raw_text = getattr(response, "text", None)
    if not isinstance(raw_text, str):
        raise ValueError("Gemini returned no text.")

    payload = toon_loads_object(_strip_markdown_fences(raw_text))
    if not isinstance(payload, dict):
        raise ValueError("Gemini output is not a TOON/JSON object.")
    return payload


def run_reel_gemini_analysis(media_url: str) -> dict[str, Any]:
    """
    Run reel analysis via an inline Gemini request (no File API).

    Returns:
    - {"status": "ok", "signals": {...}} on success
    - {"status": "error", "signals": {...}} on failure
    - {"status": "disabled", "signals": {}} when GEMINI_API_KEY is missing
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"status": "disabled", "signals": {}}

    if not media_url or not media_url.strip():
        return {"status": "error", "signals": {}, "error": "empty_media_url"}

    video_bytes = _download_reel(media_url=media_url.strip())
    if not video_bytes:
        return {"status": "error", "signals": {}, "error": "download_failed"}

    try:
        signals = _analyse_reel_inline(api_key=api_key, video_bytes=video_bytes, fps=REEL_VIDEO_FPS)
        return {"status": "ok", "signals": signals}
    except Exception as exc:
        logger.error("[ReelGemini] Analysis failed: %s", exc)
        return {"status": "error", "signals": {}, "error": str(exc)}
