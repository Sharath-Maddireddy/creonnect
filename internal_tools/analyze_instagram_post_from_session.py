from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / "backend" / ".env", override=False)
load_dotenv(REPO_ROOT / ".env", override=False)

from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.dev_scraper.instagram_profile import InstaScraper
from backend.app.services.post_insights_service import build_single_post_insights
from backend.app.tools.generate_ig_raw_fixtures import build_fixture_item


_SHORTCODE_RE = re.compile(r"instagram\.com/(?:p|reel|tv)/(?P<shortcode>[A-Za-z0-9_-]+)")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, str) and not value.strip():
            return 0
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, TypeError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        except (OSError, TypeError, ValueError):
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _extract_shortcode(post_url: str | None, shortcode: str | None) -> str:
    explicit = _optional_str(shortcode)
    if explicit:
        return explicit
    url = _optional_str(post_url)
    if not url:
        raise ValueError("Provide --post-url or --shortcode.")
    match = _SHORTCODE_RE.search(url)
    if not match:
        raise ValueError("Could not extract Instagram shortcode from --post-url.")
    return match.group("shortcode")


def _caption_text(item: dict[str, Any]) -> str:
    caption = item.get("caption")
    if isinstance(caption, dict):
        return str(caption.get("text") or "")
    if isinstance(caption, str):
        return caption
    edges = item.get("edge_media_to_caption", {}).get("edges", [])
    if isinstance(edges, list) and edges:
        return str(edges[0].get("node", {}).get("text") or "")
    return ""


def _first_image_url(item: dict[str, Any]) -> str | None:
    image_versions = item.get("image_versions2")
    if isinstance(image_versions, dict):
        candidates = image_versions.get("candidates")
        if isinstance(candidates, list) and candidates:
            return _optional_str(candidates[0].get("url"))
    carousel_media = item.get("carousel_media")
    if isinstance(carousel_media, list) and carousel_media:
        return _first_image_url(carousel_media[0])
    return _optional_str(item.get("display_url") or item.get("thumbnail_url") or item.get("thumbnail_src"))


def _first_video_url(item: dict[str, Any]) -> str | None:
    video_versions = item.get("video_versions")
    if isinstance(video_versions, list) and video_versions:
        return _optional_str(video_versions[0].get("url"))
    carousel_media = item.get("carousel_media")
    if isinstance(carousel_media, list):
        for child in carousel_media:
            video_url = _first_video_url(child)
            if video_url:
                return video_url
    return _optional_str(item.get("video_url"))


def _normalize_shortcode_item(item: dict[str, Any]) -> dict[str, Any]:
    is_video = bool(item.get("is_video") or item.get("media_type") == 2 or item.get("product_type") in {"clips", "reels"})
    display_url = _first_image_url(item)
    video_url = _first_video_url(item)
    return {
        "id": _optional_str(item.get("id") or item.get("pk")) or _optional_str(item.get("code")) or "",
        "shortcode": _optional_str(item.get("code") or item.get("shortcode")),
        "display_url": display_url,
        "likes": _safe_int(item.get("like_count") or item.get("edge_liked_by", {}).get("count")),
        "comments": _safe_int(item.get("comment_count") or item.get("edge_media_to_comment", {}).get("count")),
        "is_video": is_video,
        "caption": _caption_text(item),
        "video_views": _safe_int(item.get("play_count") or item.get("view_count") or item.get("video_view_count")),
        "video_url": video_url,
        "type": "reel" if is_video else "post",
        "timestamp": item.get("taken_at") or item.get("taken_at_timestamp") or item.get("timestamp"),
    }


async def _fetch_post_by_shortcode(
    session_id: str, shortcode: str, username: str | None = None
) -> tuple[dict[str, Any], int | None]:
    """Fetch a single post by shortcode. Returns (item_dict, follower_count)."""
    scraper = InstaScraper(session_id)
    follower_count: int | None = None
    if username:
        try:
            profile = await scraper.get_profile(username)
            # Extract follower count for tier comparison
            raw_fc = (
                profile.get("follower_count")
                or profile.get("edge_followed_by", {}).get("count")
            )
            if isinstance(raw_fc, (int, float)) and raw_fc > 0:
                follower_count = int(raw_fc)
            all_media = profile.get("posts", []) + profile.get("reels", [])
            for item in all_media:
                if item.get("shortcode") == shortcode or item.get("code") == shortcode:
                    return _normalize_shortcode_item(item), follower_count
        except Exception as e:
            print(f"Warning: Failed to fetch profile {username}: {e}")

    cookies = {"sessionid": session_id}
    headers = {
        **scraper.base_headers,
        "referer": f"https://www.instagram.com/p/{shortcode}/",
    }
    urls = [
        f"https://www.instagram.com/api/v1/media/shortcode/{shortcode}/",
        f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis",
    ]
    async with httpx.AsyncClient(http2=True, follow_redirects=True, timeout=60.0) as client:
        errors: list[str] = []
        for url in urls:
            try:
                response = await client.get(url, headers=headers, cookies=cookies)
            except httpx.RequestError as exc:
                errors.append(f"{url} -> request failed: {exc}")
                continue
            if response.status_code != 200:
                errors.append(f"{url} -> HTTP {response.status_code}")
                continue
            payload = response.json()
            item = payload.get("items", [None])[0] if isinstance(payload.get("items"), list) else None
            if not isinstance(item, dict):
                item = payload.get("graphql", {}).get("shortcode_media")
            if isinstance(item, dict):
                # Try to extract follower count from embedded user object
                _user = item.get("user") or item.get("owner") or {}
                if isinstance(_user, dict):
                    raw_fc = _user.get("follower_count") or _user.get("edge_followed_by", {}).get("count")
                    if isinstance(raw_fc, (int, float)) and raw_fc > 0:
                        follower_count = int(raw_fc)
                return _normalize_shortcode_item(item), follower_count
            errors.append(f"{url} -> no media item in response")
    raise RuntimeError("; ".join(errors) or "Instagram shortcode lookup failed.")



def _to_creator_post(item: dict[str, Any], *, username: str | None, follower_count: int | None) -> CreatorPostAIInput:
    fixture_item = build_fixture_item(item, follower_count=follower_count)
    raw = fixture_item.get("raw") if isinstance(fixture_item.get("raw"), dict) else {}
    return CreatorPostAIInput(
        post_id=str(fixture_item.get("post_id") or fixture_item.get("shortcode") or "instagram_post"),
        creator_id=username or "instagram_session_user",
        platform="instagram",
        post_type=str(fixture_item.get("post_type") or "IMAGE"),
        media_url=str(fixture_item.get("media_url") or ""),
        thumbnail_url=str(fixture_item.get("thumbnail_url") or ""),
        caption_text=str(fixture_item.get("caption_text") or ""),
        hashtags=[],
        likes=_safe_int(fixture_item.get("like_count")),
        comments=_safe_int(fixture_item.get("comment_count")),
        views=fixture_item.get("view_count"),
        posted_at=_parse_datetime(raw.get("timestamp")),
    )


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    session_id = _optional_str(args.session_id) or _optional_str(os.getenv("INSTAGRAM_SESSION_ID"))
    if not session_id:
        raise RuntimeError("Provide --session-id or set INSTAGRAM_SESSION_ID.")
    import urllib.parse
    session_id = urllib.parse.unquote(session_id)

    if args.external_ai is not None:
        os.environ["AI_EXTERNAL_CALLS_ENABLED"] = "1" if args.external_ai else "0"

    shortcode = _extract_shortcode(args.post_url, args.shortcode)
    username = _optional_str(args.username)
    raw_item, follower_count = await _fetch_post_by_shortcode(session_id, shortcode, username=username)

    target_post = _to_creator_post(raw_item, username=username, follower_count=follower_count)
    if not target_post.media_url:
        raise RuntimeError("Instagram post was fetched, but no media_url was found.")

    result = await build_single_post_insights(
        target_post=target_post,
        historical_posts=[],
        run_ai=True,
    )
    out_path = Path(args.out)
    artifact = {
        "source": "instagram_session_shortcode",
        "shortcode": shortcode,
        "post_url": args.post_url,
        "username": username,
        "external_ai_enabled": os.getenv("AI_EXTERNAL_CALLS_ENABLED"),
        "out": str(out_path),
        "raw_item": deepcopy(raw_item),
        "analysis": _to_jsonable(result),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=True), encoding="utf-8")
    return artifact


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch one Instagram post with sessionid and run single-post analysis.")
    parser.add_argument("--session-id", help="Instagram sessionid cookie value. Defaults to INSTAGRAM_SESSION_ID.")
    parser.add_argument("--post-url", help="Instagram post/reel URL, e.g. https://www.instagram.com/reel/SHORTCODE/")
    parser.add_argument("--shortcode", help="Instagram shortcode if you do not want to pass a full URL.")
    parser.add_argument("--username", help="Optional creator username for the analysis payload.")
    parser.add_argument(
        "--external-ai",
        type=int,
        choices=[0, 1],
        default=None,
        help="Set AI_EXTERNAL_CALLS_ENABLED for this run. Use 0 for deterministic fallback only.",
    )
    parser.add_argument(
        "--out",
        default=str(ARTIFACTS_DIR / "instagram_session_post_analysis.json"),
        help="Output artifact path.",
    )
    return parser.parse_args()


def main() -> None:
    artifact = asyncio.run(_run(_parse_args()))
    analysis = artifact["analysis"]
    ai_analysis = analysis.get("ai_analysis") if isinstance(analysis, dict) else {}
    post = analysis.get("post") if isinstance(analysis, dict) else {}
    print("Analysis complete")
    print(f"shortcode={artifact['shortcode']}")
    print(f"media_id={post.get('media_id') if isinstance(post, dict) else None}")
    print(f"vision_status={ai_analysis.get('vision_status') if isinstance(ai_analysis, dict) else None}")
    print(f"fallback_used={ai_analysis.get('fallback_used') if isinstance(ai_analysis, dict) else None}")
    print(f"out={artifact.get('out')}")


if __name__ == "__main__":
    main()
