"""Deterministic S6 brand safety scoring."""

from __future__ import annotations

import re
from typing import Any

from backend.app.ai.cringe_analysis import build_cringe_section_for_brand_safety
from backend.app.domain.post_models import BrandSafetyPenalty, BrandSafetyScore, VisionSignal
from backend.app.utils.logger import logger


_PROFANITY_RE = re.compile(
    r"\b("
    r"fuck|fucking|shit|bitch|asshole|bastard|damn|crap|dick|piss|"
    r"motherfucker|bullshit|slut|whore|nigga|nigger"
    r")\b",
    re.IGNORECASE,
)
_ALCOHOL_TOBACCO_KEYWORDS = {
    "alcohol",
    "beer",
    "wine",
    "vodka",
    "whisky",
    "whiskey",
    "rum",
    "tequila",
    "cigarette",
    "cigarettes",
    "smoking",
    "tobacco",
    "vape",
    "vaping",
    "cigar",
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_text(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def _normalize_objects(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = _normalize_text(value)
        if text:
            normalized.append(text)
    return normalized


def _extract_signal(vision: VisionSignal | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(vision, VisionSignal):
        return vision.model_dump(mode="python")
    if not isinstance(vision, dict):
        return {}
    signals = vision.get("signals")
    if isinstance(signals, list) and signals and isinstance(signals[0], dict):
        return signals[0]
    return vision


def _extract_objects(vision: VisionSignal | dict[str, Any] | None) -> list[str]:
    signal = _extract_signal(vision)
    primary_objects = signal.get("primary_objects")
    objects = primary_objects if isinstance(primary_objects, list) else signal.get("objects")
    if not isinstance(objects, list):
        return []
    return _normalize_objects(objects)


def _extract_bool_flag(extra_flags: dict[str, Any], key: str) -> bool:
    value = extra_flags.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "y"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _extract_competitor_keywords(extra_flags: dict[str, Any]) -> set[str]:
    raw = extra_flags.get("competitor_brands")
    if not isinstance(raw, list):
        return set()
    keywords: set[str] = set()
    for value in raw:
        if not isinstance(value, str):
            continue
        normalized = _normalize_text(value)
        if normalized:
            keywords.add(normalized)
    return keywords


def _has_competitor_mention(
    extracted_brand_mentions: list[str] | None,
    extra_flags: dict[str, Any],
) -> bool:
    if _extract_bool_flag(extra_flags, "competitor_brand_mention"):
        return True
    mentions = extracted_brand_mentions if isinstance(extracted_brand_mentions, list) else []
    normalized_mentions = {_normalize_text(value) for value in mentions if isinstance(value, str)}
    normalized_mentions = {value for value in normalized_mentions if value}
    if not normalized_mentions:
        return False
    competitor_keywords = _extract_competitor_keywords(extra_flags)
    if not competitor_keywords:
        return False
    return any(
        mention == competitor or competitor in mention or mention in competitor
        for mention in normalized_mentions
        for competitor in competitor_keywords
    )


def compute_s6_brand_safety(
    caption_text: str,
    vision: VisionSignal | dict[str, Any] | None,
    s1_total_0_50: float | None,
    extracted_brand_mentions: list[str] | None,
    extra_flags: dict[str, Any] | None,
) -> BrandSafetyScore:
    """Compute deterministic S6 brand safety score.

    Supported deterministic penalties:
    - profanity in caption: -25
    - low image quality (S1 < 15/50): -15
    - competitor brand mention: -20 (when explicit flag or competitor list match exists)
    - alcohol/tobacco content in visual objects: -35

    Optional upstream flags (currently note-only, no penalty):
    - controversial_topic
    - misinformation_flag
    """

    notes: list[str] = []
    penalties: list[BrandSafetyPenalty] = []
    flags_payload = extra_flags if isinstance(extra_flags, dict) else {}
    objects = _extract_objects(vision)
    caption = caption_text if isinstance(caption_text, str) else ""

    profanity_detected = bool(_PROFANITY_RE.search(caption))
    low_image_quality = False
    if isinstance(s1_total_0_50, (int, float)):
        low_image_quality = float(s1_total_0_50) < 15.0
    competitor_brand_mention = _has_competitor_mention(extracted_brand_mentions, flags_payload)
    alcohol_tobacco_detected = any(
        keyword in obj
        for obj in objects
        for keyword in _ALCOHOL_TOBACCO_KEYWORDS
    )
    controversial_topic = _extract_bool_flag(flags_payload, "controversial_topic")
    misinformation_flag = _extract_bool_flag(flags_payload, "misinformation_flag")

    raw_score = 100.0

    if profanity_detected:
        raw_score -= 25.0
        penalties.append(
            BrandSafetyPenalty(
                key="caption_profanity",
                penalty=25,
                reason="Profanity detected in caption text.",
            )
        )
        notes.append("Caption includes profanity.")

    if low_image_quality:
        raw_score -= 15.0
        penalties.append(
            BrandSafetyPenalty(
                key="low_image_quality",
                penalty=15,
                reason="S1 visual quality is below 15/50 threshold.",
            )
        )
        notes.append("Low visual quality reduces brand safety.")

    if competitor_brand_mention:
        raw_score -= 20.0
        penalties.append(
            BrandSafetyPenalty(
                key="competitor_brand_mention",
                penalty=20,
                reason="Competitor brand mention detected by deterministic rules.",
            )
        )
        notes.append("Competitor brand mention penalized.")

    if alcohol_tobacco_detected:
        raw_score -= 35.0
        penalties.append(
            BrandSafetyPenalty(
                key="alcohol_tobacco_content",
                penalty=35,
                reason="Alcohol/tobacco keyword detected in visual objects.",
            )
        )
        notes.append("Alcohol/tobacco visual content detected.")

    vision_payload: dict[str, Any]
    if isinstance(vision, VisionSignal):
        vision_payload = vision.model_dump(mode="python")
    elif isinstance(vision, dict):
        vision_payload = vision
    else:
        vision_payload = {}
    cringe_section = build_cringe_section_for_brand_safety(vision_payload)
    cringe_score = cringe_section.get("cringe_score")
    production_level = cringe_section.get("production_level")
    adult_content_detected = bool(cringe_section.get("adult_content_detected", False))
    normalized_cringe_score: float | None = None
    if isinstance(cringe_score, (int, float)) and not isinstance(cringe_score, bool):
        normalized_cringe_score = _clamp(float(cringe_score), 0.0, 100.0)

    if normalized_cringe_score is not None:
        if normalized_cringe_score >= 80:
            raw_score -= 25.0
            penalties.append(
                BrandSafetyPenalty(
                    key="extreme_cringe",
                    penalty=25,
                    reason="Extreme cringe score detected from vision analysis.",
                )
            )
            notes.append("Extreme cringe signal reduced brand safety.")
            logger.info("[Cringe] Applied S6 penalty key=extreme_cringe score=%.1f", normalized_cringe_score)
        elif normalized_cringe_score >= 60:
            raw_score -= 15.0
            penalties.append(
                BrandSafetyPenalty(
                    key="high_cringe",
                    penalty=15,
                    reason="High cringe score detected from vision analysis.",
                )
            )
            notes.append("High cringe signal reduced brand safety.")
            logger.info("[Cringe] Applied S6 penalty key=high_cringe score=%.1f", normalized_cringe_score)
        elif normalized_cringe_score >= 45:
            raw_score -= 8.0
            penalties.append(
                BrandSafetyPenalty(
                    key="moderate_cringe",
                    penalty=8,
                    reason="Moderate cringe score detected from vision analysis.",
                )
            )
            notes.append("Moderate cringe signal reduced brand safety.")
            logger.info("[Cringe] Applied S6 penalty key=moderate_cringe score=%.1f", normalized_cringe_score)

    if adult_content_detected:
        raw_score -= 30.0
        penalties.append(
            BrandSafetyPenalty(
                key="adult_content",
                penalty=30,
                reason="Adult content was detected by vision analysis.",
            )
        )
        notes.append("Adult content signal reduced brand safety.")
        logger.info("[Cringe] Applied S6 penalty key=adult_content")

    if production_level == "low":
        raw_score -= 5.0
        penalties.append(
            BrandSafetyPenalty(
                key="low_production",
                penalty=5,
                reason="Low production level detected in vision analysis.",
            )
        )
        notes.append("Low production level reduced brand safety.")
        logger.info("[Cringe] Applied S6 penalty key=low_production")

    if controversial_topic:
        notes.append("Upstream flag set: controversial_topic.")
    if misinformation_flag:
        notes.append("Upstream flag set: misinformation_flag.")

    raw_score = _clamp(raw_score, 0.0, 100.0)
    total_0_50 = round(raw_score / 2.0, 1)

    flags: dict[str, bool] = {
        "profanity_detected": profanity_detected,
        "low_image_quality": low_image_quality,
        "competitor_brand_mention": competitor_brand_mention,
        "alcohol_tobacco_detected": alcohol_tobacco_detected,
        "cringe_detected": bool(normalized_cringe_score is not None and normalized_cringe_score >= 45.0),
        "adult_content_detected": adult_content_detected,
        "low_production": production_level == "low",
        "controversial_topic": controversial_topic,
        "misinformation_flag": misinformation_flag,
    }

    return BrandSafetyScore(
        s6_raw_0_100=int(round(raw_score)),
        total_0_50=total_0_50,
        penalties=penalties,
        flags=flags,
        notes=notes,
    )
