"""Gemini File API video analysis for Instagram Reels."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from backend.app.ai.prompts import REEL_VISION_EVALUATION_PROMPT
from backend.app.ai.toon import loads as toon_loads
from backend.app.utils.logger import logger


REEL_DOWNLOAD_TIMEOUT_SEC = 30.0
MAX_VIDEO_BYTES = 100 * 1024 * 1024
GEMINI_FILE_POLL_MAX_ATTEMPTS = 20
GEMINI_FILE_POLL_INTERVAL_SEC = 2.0


def _download_reel(media_url: str) -> bytes | None:
    """Download reel bytes with a strict max-size cap."""
    try:
        with httpx.Client(timeout=REEL_DOWNLOAD_TIMEOUT_SEC, follow_redirects=True) as client:
            with client.stream("GET", media_url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total_bytes = 0
                for chunk in response.iter_bytes(65536):
                    chunks.append(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > MAX_VIDEO_BYTES:
                        logger.warning("[ReelGemini] Video exceeds size cap, aborting download.")
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


def _upload_and_analyse(api_key: str, video_bytes: bytes) -> dict[str, Any]:
    """Upload video to Gemini File API (new google-genai SDK), poll until ACTIVE, then analyse."""
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=api_key)
    tmp_path: Path | None = None
    uploaded_file_name: str | None = None

    # Write video to temp file — close handle before upload to avoid Windows locking
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = Path(tmp.name)
    # File handle is now closed — safe to read on Windows

    try:
        logger.info("[ReelGemini] Uploading video to Gemini File API (%d bytes).", len(video_bytes))
        with open(tmp_path, "rb") as video_file:
            uploaded = client.files.upload(
                file=video_file,
                config=genai_types.UploadFileConfig(mime_type="video/mp4"),
            )
        uploaded_file_name = getattr(uploaded, "name", None)

        # Poll until ACTIVE
        for attempt in range(GEMINI_FILE_POLL_MAX_ATTEMPTS):
            file_status = client.files.get(name=uploaded_file_name)
            state = str(getattr(file_status, "state", "")).upper()
            if "ACTIVE" in state:
                break
            if "FAILED" in state:
                raise RuntimeError("Gemini file processing FAILED.")
            logger.debug("[ReelGemini] File state=%s, waiting... (attempt %d)", state, attempt + 1)
            time.sleep(GEMINI_FILE_POLL_INTERVAL_SEC)
        else:
            raise TimeoutError("Gemini file never reached ACTIVE state.")

        # Run analysis — retry once on 429 rate-limit with 30s backoff
        _MODELS_TO_TRY = ["gemini-2.0-flash-lite", "gemini-flash-lite-latest"]
        last_exc: Exception | None = None
        response = None
        for model_name in _MODELS_TO_TRY:
            for attempt in range(2):  # 1 retry per model
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[REEL_VISION_EVALUATION_PROMPT, file_status],
                    )
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc)
                    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                        logger.warning("[ReelGemini] 429 on %s, waiting 35s before retry...", model_name)
                        time.sleep(35)
                    else:
                        break  # Non-rate-limit error — move to next model
            if last_exc is None:
                break  # Success

        if last_exc is not None or response is None:
            raise last_exc or RuntimeError("No response from Gemini.")

        raw_text = getattr(response, "text", None)
        if not isinstance(raw_text, str):
            raise ValueError("Gemini returned no text.")

        payload = toon_loads(_strip_markdown_fences(raw_text))
        if not isinstance(payload, dict):
            raise ValueError("Gemini output is not a TOON object.")
        return payload

    finally:
        # Clean up temp file — wrap for Windows where OS may briefly hold handle
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        # Best-effort: delete Gemini-hosted file to stay within quota
        if uploaded_file_name:
            try:
                client.files.delete(name=uploaded_file_name)
            except Exception:
                pass


def run_reel_gemini_analysis(media_url: str) -> dict[str, Any]:
    """
    Run reel analysis through Gemini File API.

    Returns:
    - {"status": "ok", "signals": {...}} on success
    - {"status": "error", "signals": {...}} on failure
    - {"status": "disabled", "signals": {...}} when GEMINI_API_KEY is missing
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
        signals = _upload_and_analyse(api_key=api_key, video_bytes=video_bytes)
        return {"status": "ok", "signals": signals}
    except Exception as exc:
        logger.error("[ReelGemini] Analysis failed: %s", exc)
        return {"status": "error", "signals": {}, "error": str(exc)}
