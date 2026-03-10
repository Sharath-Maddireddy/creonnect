"""Deterministic S1 (Visual Quality) scoring from vision signals."""

from __future__ import annotations

from typing import Any

from backend.app.domain.post_models import VisualQualityScore


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (TypeError, ValueError):
            return None
    return None


def _normalize_hook_strength(value: Any) -> float:
    numeric = _as_float(value)
    if numeric is None:
        return 0.5
    return _clamp(numeric, 0.0, 1.0)


def _first_signal(vision_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(vision_payload, dict):
        return {}
    signals = vision_payload.get("signals")
    if isinstance(signals, list) and signals and isinstance(signals[0], dict):
        return signals[0]
    return vision_payload if isinstance(vision_payload, dict) else {}


def _normalize_objects(signal: dict[str, Any]) -> list[str]:
    primary_objects = signal.get("primary_objects")
    objects = primary_objects if isinstance(primary_objects, list) else signal.get("objects")
    if not isinstance(objects, list):
        return []
    return [item.strip().lower() for item in objects if isinstance(item, str) and item.strip()]


def _resolve_focus(signal: dict[str, Any]) -> str | None:
    for key in ("dominant_focus", "dominant_object"):
        value = signal.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _map_quality_signal_to_subscore(value: Any, baseline: float) -> float:
    numeric = _as_float(value)
    if numeric is not None:
        # 0..1 input is treated as normalized quality; larger numbers are treated as direct 0..10.
        if 0.0 <= numeric <= 1.0:
            return _clamp(numeric * 10.0, 0.0, 10.0)
        return _clamp(numeric, 0.0, 10.0)

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"excellent", "high", "strong"}:
            return 8.5
        if lowered in {"medium", "moderate", "average"}:
            return 6.0
        if lowered in {"low", "poor", "weak"}:
            return 3.5
    return baseline


def _normalize_detected_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    if isinstance(value, list):
        parts = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return " ".join(parts).strip()
    return ""


def _text_overlay_penalty(value: Any) -> float:
    normalized_text = _normalize_detected_text(value)
    if not normalized_text:
        return 0.0

    char_count = len(normalized_text)
    word_count = len(normalized_text.split())

    if char_count >= 80 or word_count >= 16:
        return -3.0
    if char_count >= 40 or word_count >= 8:
        return -1.5
    return 0.0


def _is_text_heavy(value: Any) -> bool:
    return _text_overlay_penalty(value) <= -1.5


def compute_visual_quality_score(vision_payload: dict[str, Any] | None) -> VisualQualityScore:
    """Compute deterministic S1 visual quality from normalized vision payload."""
    signal = _first_signal(vision_payload)
    objects = _normalize_objects(signal)
    dominant_focus = _resolve_focus(signal)
    hook_strength_score = _normalize_hook_strength(signal.get("hook_strength_score"))

    notes: list[str] = []

    composition = 3.5
    if dominant_focus is not None:
        composition += 4.0
        notes.append("Dominant focus detected, improving composition score.")
    if 1 <= len(objects) <= 2:
        composition += 3.0
        notes.append("Primary object count is focused (1-2 objects).")
    if hook_strength_score > 0.7:
        composition += 3.0
        notes.append("Strong visual hook boosts composition.")
    if len(objects) > 5:
        composition -= 2.0
        notes.append("Object clutter penalizes composition.")
    composition = _clamp(composition, 0.0, 10.0)

    lighting = _map_quality_signal_to_subscore(signal.get("lighting_quality"), baseline=6.0)
    if hook_strength_score > 0.6:
        lighting += 2.0
        notes.append("Hook strength suggests stronger visual lighting impact.")
    if dominant_focus is None:
        lighting -= 2.0
        notes.append("Missing dominant focus lowers perceived lighting quality.")
    lighting = _clamp(lighting, 0.0, 10.0)

    subject_clarity = _map_quality_signal_to_subscore(signal.get("subject_clarity"), baseline=4.0)
    if dominant_focus is not None:
        subject_clarity += 5.0
        notes.append("Clear dominant focus improves subject clarity.")
    if any(obj == "person" for obj in objects):
        subject_clarity += 3.0
        notes.append("Human subject improves clarity signal.")
    if len(objects) > 5:
        subject_clarity -= 2.0
        notes.append("High object count lowers clarity.")
    subject_clarity = _clamp(subject_clarity, 0.0, 10.0)

    explicit_aesthetic = signal.get("aesthetic_quality")
    if explicit_aesthetic is not None:
        aesthetic_quality = _map_quality_signal_to_subscore(explicit_aesthetic, baseline=hook_strength_score * 10.0)
    else:
        aesthetic_quality = hook_strength_score * 10.0
    text_penalty = _text_overlay_penalty(signal.get("detected_text"))
    aesthetic_quality += text_penalty
    if text_penalty <= -3.0:
        notes.append("High text density strongly penalizes aesthetic quality.")
    elif text_penalty <= -1.5:
        notes.append("Moderate text density mildly penalizes aesthetic quality.")
    if any(obj == "person" for obj in objects):
        aesthetic_quality += 1.0
        notes.append("Human subject adds slight aesthetic uplift.")
    aesthetic_quality = _clamp(aesthetic_quality, 0.0, 10.0)

    total = (composition * 0.30 + lighting * 0.20 + subject_clarity * 0.30 + aesthetic_quality * 0.20) * 5.0

    if not signal:
        notes.append("Vision signal missing; using safe deterministic defaults.")

    return VisualQualityScore(
        composition=composition,
        lighting=lighting,
        subject_clarity=subject_clarity,
        aesthetic_quality=aesthetic_quality,
        total=total,
        notes=notes,
    )
