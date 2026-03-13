from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.app.ai.schemas import CreatorPostAIInput


HASHTAG_RE = re.compile(r"#\w+")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_int_or_none(value: Any) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_hashtags(caption_text: str) -> list[str]:
    if not caption_text:
        return []
    return HASHTAG_RE.findall(caption_text)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _resolve_post_id(item: dict[str, Any]) -> str:
    candidates = [
        _optional_str(item.get("post_id")),
        _optional_str(item.get("shortcode")),
    ]
    raw = item.get("raw")
    if isinstance(raw, dict):
        candidates.extend(
            [
                _optional_str(raw.get("id")),
                _optional_str(raw.get("shortcode")),
            ]
        )
    for candidate in candidates:
        if candidate:
            return candidate

    fallback_payload = json.dumps(item, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha1(fallback_payload.encode("utf-8")).hexdigest()[:16]


def _extract_posted_at(item: dict[str, Any]) -> datetime | None:
    for key in ("posted_at", "timestamp"):
        parsed = _parse_datetime(item.get(key))
        if parsed is not None:
            return parsed
    raw = item.get("raw")
    if isinstance(raw, dict):
        for key in ("timestamp", "taken_at_timestamp", "taken_at"):
            parsed = _parse_datetime(raw.get(key))
            if parsed is not None:
                return parsed
    return None


def build_creator_post_ai_input_from_fixture(item: dict) -> CreatorPostAIInput:
    """Convert one raw fixture item to CreatorPostAIInput with safe defaults."""
    fixture_item = item if isinstance(item, dict) else {}
    caption_text = str(fixture_item.get("caption_text", "") or "")
    post_type = "REEL" if str(fixture_item.get("post_type", "")).upper() == "REEL" else "IMAGE"
    media_url = _optional_str(fixture_item.get("media_url")) or ""
    thumbnail_url = _optional_str(fixture_item.get("thumbnail_url")) or ""

    creator_post = CreatorPostAIInput(
        post_id=_resolve_post_id(fixture_item),
        creator_id=_optional_str(fixture_item.get("username")) or "",
        platform="instagram",
        post_type=post_type,
        media_url=media_url,
        thumbnail_url=thumbnail_url,
        caption_text=caption_text,
        hashtags=_extract_hashtags(caption_text),
        likes=_safe_int(fixture_item.get("like_count"), default=0),
        comments=_safe_int(fixture_item.get("comment_count"), default=0),
        views=_safe_int_or_none(fixture_item.get("view_count")),
        audio_name=None,
        posted_at=_extract_posted_at(fixture_item),
    )

    return creator_post
