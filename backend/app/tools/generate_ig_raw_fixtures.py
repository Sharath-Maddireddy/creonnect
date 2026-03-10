from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from backend/ or project root before any env reads
load_dotenv(Path(__file__).resolve().parents[3] / "backend" / ".env", override=False)
load_dotenv(override=False)  # fallback to project root .env

from backend.app.dev_scraper import fetch_instagram_profile


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, str) and not value.strip():
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
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
        if text.isdigit():
            try:
                return datetime.fromtimestamp(float(text), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _item_timestamp(item: dict[str, Any]) -> datetime | None:
    for key in ("timestamp", "taken_at_timestamp", "taken_at", "posted_at"):
        parsed = _parse_timestamp(item.get(key))
        if parsed is not None:
            return parsed
    raw = item.get("raw")
    if isinstance(raw, dict):
        for key in ("timestamp", "taken_at_timestamp", "taken_at", "posted_at"):
            parsed = _parse_timestamp(raw.get(key))
            if parsed is not None:
                return parsed
    return None


def _is_reel(item: dict[str, Any]) -> bool:
    item_type = _optional_str(item.get("type"))
    return (item_type or "").lower() == "reel" or item.get("is_video") is True


def build_fixture_item(item: dict[str, Any], follower_count: int | None) -> dict[str, Any]:
    is_reel = _is_reel(item)
    post_type = "REEL" if is_reel else "IMAGE"
    display_url = _optional_str(item.get("display_url"))
    video_url = _optional_str(item.get("video_url"))

    if post_type == "REEL" and video_url:
        media_url = video_url
        thumbnail_url = display_url
    else:
        media_url = display_url or video_url or ""
        thumbnail_url = None

    post_id = _optional_str(item.get("id")) or _optional_str(item.get("shortcode")) or ""

    return {
        "platform": "instagram",
        "post_id": post_id,
        "shortcode": _optional_str(item.get("shortcode")),
        "post_type": post_type,
        "media_url": media_url,
        "thumbnail_url": thumbnail_url,
        "caption_text": str(item.get("caption", "") or ""),
        "like_count": _safe_int_or_none(item.get("likes")),
        "comment_count": _safe_int_or_none(item.get("comments")),
        "view_count": _safe_int_or_none(item.get("video_views")),
        "follower_count": follower_count,
        "raw": deepcopy(item),
    }


def _select_items(posts: list[dict[str, Any]], reels: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    combined = list(posts) + list(reels)
    indexed: list[tuple[int, datetime | None, dict[str, Any]]] = [
        (index, _item_timestamp(item), item) for index, item in enumerate(combined)
    ]
    has_timestamp = any(timestamp is not None for _, timestamp, _ in indexed)
    if has_timestamp:
        indexed.sort(
            key=lambda row: (
                1 if row[1] is None else 0,
                0.0 if row[1] is None else -row[1].timestamp(),
                row[0],
            )
        )
    selected = [item for _, _, item in indexed]
    return selected[:limit]


async def _build_fixture_payload(username: str, limit: int) -> dict[str, Any]:
    profile_data = await fetch_instagram_profile(username)
    followers = _safe_int_or_none(profile_data.get("followers"))
    posts = profile_data.get("posts") if isinstance(profile_data.get("posts"), list) else []
    reels = profile_data.get("reels") if isinstance(profile_data.get("reels"), list) else []
    selected = _select_items(posts=posts, reels=reels, limit=limit)
    items = [build_fixture_item(item, follower_count=followers) for item in selected]
    return {
        "source": "scraper",
        "username": username,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "followers": followers,
        "limit": limit,
        "items": items,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Instagram raw fixtures from dev scraper.")
    parser.add_argument("--username", required=True, help="Instagram username to fetch.")
    parser.add_argument("--limit", type=int, default=30, help="Max number of combined posts+reels in output.")
    parser.add_argument("--out", required=True, help="Output JSON path, e.g. fixtures/ig_name_raw.json")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    limit = max(1, int(args.limit))
    try:
        payload = asyncio.run(_build_fixture_payload(username=args.username, limit=limit))
    except RuntimeError as exc:
        if str(exc) == "Set INSTAGRAM_SESSION_ID to run fixture generator.":
            raise SystemExit(str(exc))
        raise

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, ensure_ascii=True, sort_keys=True)
        fp.write("\n")

    print(f"Wrote fixture: {out_path} ({len(payload['items'])} items)")


if __name__ == "__main__":
    main()
