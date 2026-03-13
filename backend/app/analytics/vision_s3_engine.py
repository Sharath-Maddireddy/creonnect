"""Deterministic S3 (Content Clarity) scoring from vision signals and caption text."""

from __future__ import annotations

import re
from typing import Any

from backend.app.domain.post_models import ContentClarityScore, VisionSignal


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HASHTAG_RE = re.compile(r"#\w+")
_CTA_RE = re.compile(
    r"\b(comment|save|share|link in bio|follow|dm|tag|what do you think|thoughts|agree)\b",
    re.IGNORECASE,
)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "my",
    "our",
    "you",
    "your",
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def normalize_text(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def word_count(value: str) -> int:
    normalized = normalize_text(value)
    return len(normalized.split()) if normalized else 0


def has_cta(caption: str) -> bool:
    if not isinstance(caption, str):
        return False
    return bool(_CTA_RE.search(caption))


def hashtags_count(caption: str) -> int:
    return _hashtags_count(caption)


def _caption_tokens(caption: str) -> list[str]:
    if not isinstance(caption, str):
        return []
    normalized = normalize_text(caption)
    if not normalized:
        return []

    stripped = re.sub(r"[^a-z0-9#\s]", " ", normalized)
    tokens: list[str] = []
    for token in stripped.split():
        if token.startswith("#"):
            continue
        if len(token) < 3:
            continue
        if token in _STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _hashtags_count(caption: str) -> int:
    if not isinstance(caption, str):
        return 0
    normalized = normalize_text(caption)
    if not normalized:
        return 0
    stripped = re.sub(r"[^a-z0-9#\s]", " ", normalized)
    return sum(1 for token in stripped.split() if token.startswith("#") and len(token) > 1)


def _caption_uniqueness_ratio(caption: str) -> float:
    tokens = _caption_tokens(caption)
    if len(tokens) < 2:
        return 1.0
    return len(set(tokens)) / len(tokens)


def _non_hashtag_token_ratio(caption: str) -> float:
    if not isinstance(caption, str):
        return 0.0
    normalized = normalize_text(caption)
    if not normalized:
        return 0.0
    stripped = re.sub(r"[^a-z0-9#\s]", " ", normalized)
    all_tokens = [token for token in stripped.split() if token]
    if not all_tokens:
        return 0.0
    non_hashtag_count = sum(1 for token in all_tokens if not token.startswith("#"))
    return non_hashtag_count / len(all_tokens)


def _extract_signal(vision: VisionSignal | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(vision, VisionSignal):
        return vision.model_dump(mode="python")

    if not isinstance(vision, dict):
        return {}

    signals = vision.get("signals")
    if isinstance(signals, list) and signals and isinstance(signals[0], dict):
        return signals[0]
    return vision


def get_dominant_focus(signal: dict[str, Any]) -> str | None:
    dominant_focus = signal.get("dominant_focus")
    if isinstance(dominant_focus, str) and dominant_focus.strip():
        return dominant_focus.strip()

    dominant_object = signal.get("dominant_object")
    if isinstance(dominant_object, str) and dominant_object.strip():
        return dominant_object.strip()

    return None


def _get_primary_objects(signal: dict[str, Any]) -> list[str]:
    primary_objects = signal.get("primary_objects")
    objects = primary_objects if isinstance(primary_objects, list) else signal.get("objects")
    if not isinstance(objects, list):
        return []
    return [item.strip().lower() for item in objects if isinstance(item, str) and item.strip()]


def get_primary_objects_count(signal: dict[str, Any]) -> int:
    return len(_get_primary_objects(signal))


def detected_text_stats(signal: dict[str, Any]) -> tuple[str, int, int]:
    detected_text = signal.get("detected_text")
    if isinstance(detected_text, str):
        normalized = normalize_text(detected_text)
    elif isinstance(detected_text, list):
        normalized = normalize_text(" ".join(item for item in detected_text if isinstance(item, str)))
    else:
        normalized = ""

    return normalized, len(normalized), word_count(normalized)


def _tokenize_for_overlap(text: str) -> set[str]:
    tokens = set(_TOKEN_RE.findall(normalize_text(text)))
    return {token for token in tokens if len(token) >= 4 and token not in _STOPWORDS}


def _mentions_focus_or_object(caption: str, dominant_focus: str | None, objects: list[str]) -> bool:
    caption_tokens = _tokenize_for_overlap(caption)
    if not caption_tokens:
        return False

    if isinstance(dominant_focus, str):
        focus_tokens = _tokenize_for_overlap(dominant_focus)
        if focus_tokens & caption_tokens:
            return True

    for obj in objects:
        obj_tokens = _tokenize_for_overlap(obj)
        if obj_tokens & caption_tokens:
            return True
    return False


def compute_s3_content_clarity(
    vision: VisionSignal | dict[str, Any] | None,
    caption_text: str,
) -> ContentClarityScore:
    """Compute deterministic S3 content clarity score."""
    signal = _extract_signal(vision)
    caption = caption_text if isinstance(caption_text, str) else ""
    normalized_caption = normalize_text(caption)
    caption_words = word_count(caption)
    hashtag_total = _hashtags_count(caption)
    caption_token_count = len(_caption_tokens(caption))
    caption_uniqueness = _caption_uniqueness_ratio(caption)
    non_hashtag_ratio = _non_hashtag_token_ratio(caption)
    objects = _get_primary_objects(signal)
    objects_count = get_primary_objects_count(signal)
    dominant_focus = get_dominant_focus(signal)
    scene_type = signal.get("scene_type")
    scene_description = signal.get("scene_description")
    detected_text, detected_text_chars, detected_text_words = detected_text_stats(signal)
    detected_text_heavy = detected_text_words >= 16 or detected_text_chars >= 80

    notes: list[str] = []

    message_singularity = 6.0
    if dominant_focus is not None:
        message_singularity += 2.0
    else:
        notes.append("No dominant focus detected.")
    if 1 <= objects_count <= 2:
        message_singularity += 1.0
    if objects_count >= 6:
        message_singularity -= 2.0
        notes.append("High object clutter.")
    if detected_text_heavy:
        message_singularity -= 2.0
        notes.append("Heavy text overlay.")
    message_singularity = _clamp(message_singularity, 0.0, 10.0)

    context_clarity = 6.0
    has_scene_type = isinstance(scene_type, str) and bool(scene_type.strip())
    has_scene_description = isinstance(scene_description, str) and bool(scene_description.strip())
    if has_scene_type or has_scene_description:
        context_clarity += 2.0
    if not has_scene_type and not has_scene_description and dominant_focus is None:
        context_clarity -= 2.0
    if 5 <= caption_words <= 60:
        context_clarity += 1.0
    if caption_words > 120:
        context_clarity -= 1.0
        notes.append("Caption is overly long.")
    if hashtag_total >= 10 and non_hashtag_ratio < 0.35:
        context_clarity -= 2.0
        notes.append("Hashtag-heavy caption weakens context clarity.")
    context_clarity = _clamp(context_clarity, 0.0, 10.0)

    caption_alignment = 5.0
    if detected_text:
        overlap = _tokenize_for_overlap(detected_text) & _tokenize_for_overlap(normalized_caption)
        if overlap:
            caption_alignment += 2.0
            notes.append("Caption reinforces overlay text.")
    if _mentions_focus_or_object(caption, dominant_focus, objects):
        caption_alignment += 1.0
    if not normalized_caption and not detected_text:
        caption_alignment -= 1.0
    if caption_token_count >= 6 and caption_uniqueness < 0.45:
        caption_alignment -= 2.0
        notes.append("Repetitive caption reduces alignment quality.")
    if caption_token_count >= 10 and caption_uniqueness < 0.35:
        caption_alignment -= 1.0
    if hashtag_total >= 10:
        caption_alignment -= 1.0
    if hashtag_total >= 20:
        caption_alignment -= 1.0
        notes.append("Hashtag spam reduces caption clarity.")
    caption_alignment = _clamp(caption_alignment, 0.0, 10.0)

    visual_message_support = 5.0
    if detected_text:
        visual_message_support += 2.0
    if dominant_focus is not None:
        visual_message_support += 2.0
    if detected_text_heavy and dominant_focus is None:
        visual_message_support -= 2.0
    visual_message_support = _clamp(visual_message_support, 0.0, 10.0)

    overload_points = 0.0
    if objects_count >= 6:
        overload_points += 2.0
    if detected_text_heavy:
        overload_points += 2.0
    if caption_words > 120:
        overload_points += 1.0
    if hashtag_total >= 10:
        overload_points += 1.0
    if hashtag_total >= 20:
        overload_points += 1.0
    if caption_token_count >= 10 and caption_uniqueness < 0.30:
        overload_points += 2.0
    if hashtag_total >= 10 and non_hashtag_ratio < 0.35:
        overload_points += 1.0
    cognitive_load = _clamp(10.0 - overload_points, 0.0, 10.0)

    total = (
        message_singularity * 0.25
        + context_clarity * 0.20
        + caption_alignment * 0.20
        + visual_message_support * 0.20
        + cognitive_load * 0.15
    ) * 5.0
    total = _clamp(total, 0.0, 50.0)

    if has_cta(caption):
        notes.append("Caption contains CTA language.")

    return ContentClarityScore(
        message_singularity=message_singularity,
        context_clarity=context_clarity,
        caption_alignment=caption_alignment,
        visual_message_support=visual_message_support,
        cognitive_load=cognitive_load,
        total=total,
        notes=notes,
    )
