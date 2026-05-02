"""Sarvam AI speech-to-text transcription for Instagram Reels audio.

Uses the Sarvam saaras:v3 model which auto-detects Indian languages and English.
This is a best-effort transcription — failures return None without crashing the pipeline.

API endpoint: POST https://api.sarvam.ai/speech-to-text
Auth header:  api-subscription-key: <SARVAM_API_KEY>
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx

from backend.app.utils.logger import logger


SARVAM_STT_ENDPOINT = "https://api.sarvam.ai/speech-to-text"
SARVAM_MODEL = "saaras:v3"
SARVAM_MODE = "transcribe"   # standard transcription in original language
SARVAM_LANGUAGE = "unknown"  # auto-detect: works for Hindi, English, Tamil, etc.

AUDIO_DOWNLOAD_TIMEOUT_SEC = 30.0
SARVAM_REQUEST_TIMEOUT_SEC = 60.0
MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB safety cap


def _download_audio(audio_url: str) -> bytes | None:
    """Download reel audio bytes with size cap."""
    try:
        with httpx.Client(timeout=AUDIO_DOWNLOAD_TIMEOUT_SEC, follow_redirects=True) as client:
            with client.stream("GET", audio_url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes(65536):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > MAX_AUDIO_BYTES:
                        logger.warning("[SarvamSTT] Audio exceeds size cap, aborting download.")
                        return None
                return b"".join(chunks)
    except Exception as exc:
        logger.warning("[SarvamSTT] Audio download failed: %s", exc)
        return None


def _call_sarvam_stt(api_key: str, audio_bytes: bytes, suffix: str = ".mp4") -> str | None:
    """Upload audio bytes to Sarvam STT and return the transcript string."""
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        with open(tmp_path, "rb") as audio_file:
            response = httpx.post(
                SARVAM_STT_ENDPOINT,
                headers={"api-subscription-key": api_key},
                files={"file": (tmp_path.name, audio_file, "audio/mp4")},
                data={
                    "model": SARVAM_MODEL,
                    "mode": SARVAM_MODE,
                    "language_code": SARVAM_LANGUAGE,
                    "with_timestamps": "false",
                },
                timeout=SARVAM_REQUEST_TIMEOUT_SEC,
            )

        if response.status_code != 200:
            logger.warning(
                "[SarvamSTT] API returned %d: %s",
                response.status_code,
                response.text[:200],
            )
            return None

        payload = response.json()
        transcript = payload.get("transcript")
        lang = payload.get("language_code", "unknown")
        if isinstance(transcript, str) and transcript.strip():
            logger.info(
                "[SarvamSTT] Transcription success — lang=%s chars=%d",
                lang,
                len(transcript),
            )
            return transcript.strip()
        return None

    except Exception as exc:
        logger.warning("[SarvamSTT] Transcription failed: %s", exc)
        return None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def transcribe_reel_audio(media_url: str) -> str | None:
    """Transcribe a reel's spoken audio via Sarvam AI saaras:v3.

    Returns:
        The transcript string if successful, None if disabled or failed.
        Never raises — designed to be a best-effort, non-blocking step.
    """
    api_key = os.getenv("SARVAM_API_KEY", "").strip()
    if not api_key:
        logger.debug("[SarvamSTT] SARVAM_API_KEY not set — transcription disabled.")
        return None

    if not media_url or not media_url.strip():
        return None

    audio_bytes = _download_audio(media_url.strip())
    if not audio_bytes:
        logger.warning("[SarvamSTT] Could not download audio from %s", media_url[:80])
        return None

    return _call_sarvam_stt(api_key=api_key, audio_bytes=audio_bytes)
