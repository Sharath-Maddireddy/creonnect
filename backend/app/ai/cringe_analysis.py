"""Shared cringe analysis helpers for Gemini vision payloads."""

from __future__ import annotations

import re
from typing import Any


_STRONG_SIGNAL_RE = re.compile(
    r"awkward|cringe|forced|overexaggerated|nonsens|confus|chaotic|low production|poor quality",
    re.IGNORECASE,
)
CRINGE_DETECTION_THRESHOLD = 45
CRINGE_NOT_CRINGE_MAX = 30
CRINGE_UNCERTAIN_MAX = 59


def _clamp_score(value: int | float | str | None) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(max(0.0, min(100.0, round(numeric))))


def _normalize_text_list(value: list[Any] | Any, limit: int = 3) -> list[str]:
    values = value if isinstance(value, list) else [value]
    sanitized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        sanitized.append(text[:160])
        if len(sanitized) >= limit:
            break
    return sanitized


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y"}:
            return True
        if text in {"0", "false", "no", "n"}:
            return False
    return default


def _normalize_production_level(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text not in {"low", "medium", "high"}:
        return None
    return text


def enforce_cringe_floor(cringe_score: int, cringe_signals: list[str]) -> int:
    """
    Port of enforceCringeFloor from Cringe-detector-main/server.js.
    - 3+ signals with strong keywords -> score >= 70
    - 2 signals with strong keywords -> score >= 60
    - Cap at 100, floor at 0.
    Strong signal keywords: awkward, cringe, forced, overexaggerated, nonsens, confus, chaotic,
    low production, poor quality
    """
    score = int(max(0, min(100, round(cringe_score))))
    signals = [item for item in cringe_signals if isinstance(item, str)]
    signal_text = " ".join(signals).lower()
    strong_signal = bool(_STRONG_SIGNAL_RE.search(signal_text))

    if len(signals) >= 3 and strong_signal:
        score = max(score, 70)
    elif len(signals) >= 2 and strong_signal:
        score = max(score, 60)

    return int(max(0, min(100, score)))


def derive_cringe_label(cringe_score: int | None) -> str | None:
    """Severity classification: 0-30 not_cringe, 31-59 uncertain, 60-100 cringe."""
    if cringe_score is None:
        return None
    if cringe_score <= CRINGE_NOT_CRINGE_MAX:
        return "not_cringe"
    if cringe_score <= CRINGE_UNCERTAIN_MAX:
        return "uncertain"
    return "cringe"


def is_cringe_detected(cringe_score: int | None) -> bool:
    """Safety-oriented cringe detection threshold independent of severity label."""
    return bool(cringe_score is not None and cringe_score >= CRINGE_DETECTION_THRESHOLD)


def build_cringe_section_for_brand_safety(vision_analysis: dict) -> dict:
    """
    Extract cringe data from vision_analysis dict and return a summary dict:
    {
      "cringe_score": int | None,
      "cringe_label": str | None,
      "is_cringe": bool,
      "cringe_signals": list[str],
      "production_level": str | None,
      "adult_content_detected": bool,
    }
    Used by S6 brand safety scoring.
    """
    if not isinstance(vision_analysis, dict):
        return {
            "cringe_score": None,
            "cringe_label": None,
            "is_cringe": False,
            "cringe_signals": [],
            "production_level": None,
            "adult_content_detected": False,
        }

    signal: dict[str, Any] = {}
    signals = vision_analysis.get("signals")
    if isinstance(signals, list) and signals and isinstance(signals[0], dict):
        signal = signals[0]
    elif isinstance(vision_analysis, dict):
        signal = vision_analysis

    raw_score = _clamp_score(signal.get("cringe_score"))
    cringe_signals = _normalize_text_list(signal.get("cringe_signals"), limit=3)
    cringe_label = signal.get("cringe_label") if isinstance(signal.get("cringe_label"), str) else None
    if isinstance(cringe_label, str):
        cringe_label = cringe_label.strip().lower()
    if cringe_label not in {"not_cringe", "uncertain", "cringe"}:
        cringe_label = derive_cringe_label(raw_score)
    production_level = _normalize_production_level(signal.get("production_level"))
    adult_content_detected = _normalize_bool(signal.get("adult_content_detected"), default=False)

    return {
        "cringe_score": raw_score,
        "cringe_label": cringe_label,
        "is_cringe": is_cringe_detected(raw_score),
        "cringe_signals": cringe_signals,
        "production_level": production_level,
        "adult_content_detected": adult_content_detected,
    }
