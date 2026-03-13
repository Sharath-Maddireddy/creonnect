"""DEV ONLY: for fixture generation/testing. Not used in production."""

from __future__ import annotations

import asyncio
import math
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx


SESSION_ENV_VAR = "INSTAGRAM_SESSION_ID"
SESSION_ERROR_MESSAGE = "Set INSTAGRAM_SESSION_ID to run fixture generator."


class InstaScraper:
    """Minimal Instagram profile scraper vendored for local fixture generation."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id.strip()
        self.base_headers = {
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-ig-app-id": "936619743392459",
            "x-asbd-id": "129477",
            "x-ig-www-claim": "0",
            "x-requested-with": "XMLHttpRequest",
        }

    @staticmethod
    def _sanitize_stat(value: Any) -> int:
        try:
            if value is None or (isinstance(value, float) and math.isnan(value)):
                return 0
            if isinstance(value, str):
                raw = value.strip().lower()
                if raw in {"", "nan", "none", "null"}:
                    return 0
                return int(float(raw.replace(",", "")))
            return int(value)
        except Exception:
            return 0

    @staticmethod
    def _normalize_timestamp(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                if float(value) <= 0:
                    return None
                return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
            except Exception:
                return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return datetime.fromtimestamp(float(text), tz=timezone.utc).isoformat()
            except Exception:
                pass
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        return None

    async def get_profile(self, username: str, max_posts: int = 200) -> dict[str, Any]:
        cookies = {"sessionid": self.session_id}
        headers = {**self.base_headers, "referer": f"https://www.instagram.com/{username}/"}
        api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={quote(username, safe='')}"

        async with httpx.AsyncClient(http2=True, follow_redirects=True, timeout=60.0) as client:
            profile_response = await client.get(api_url, headers=headers, cookies=cookies)
            if profile_response.status_code != 200:
                raise RuntimeError(
                    f"Instagram API Error (HTTP {profile_response.status_code}). Check your Session ID."
                )

            payload = profile_response.json().get("data", {}).get("user")
            if not payload:
                raise RuntimeError("Profile not found or restricted.")

            user_id = payload.get("id")
            all_media: list[dict[str, Any]] = []

            timeline = payload.get("edge_owner_to_timeline_media", {})
            clips = payload.get("edge_owner_to_clips_media", {})
            all_media.extend(timeline.get("edges", []))
            all_media.extend(clips.get("edges", []))

            page_info = timeline.get("page_info", {})
            retries = 0
            while page_info.get("has_next_page") and len(all_media) < max_posts and retries < 3:
                end_cursor = page_info.get("end_cursor")
                if not end_cursor or not user_id:
                    break

                await asyncio.sleep(1.5)
                feed_url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/?count=50&max_id={end_cursor}"
                try:
                    feed_response = await client.get(feed_url, headers=headers, cookies=cookies)
                    if feed_response.status_code == 200:
                        feed_data = feed_response.json()
                        items = feed_data.get("items", [])
                        all_media.extend(self._convert_feed_items(items))
                        if feed_data.get("more_available") and feed_data.get("next_max_id"):
                            page_info = {"has_next_page": True, "end_cursor": feed_data.get("next_max_id")}
                            retries = 0
                        else:
                            break
                        continue
                    if feed_response.status_code == 401:
                        break
                    retries += 1
                    await asyncio.sleep(3)
                except Exception:
                    retries += 1
                    await asyncio.sleep(2)

        return self._parse_consolidated_data(payload, all_media, username)

    def _convert_feed_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for item in items:
            converted.append(
                {
                    "node": {
                        "id": item.get("pk") or item.get("id"),
                        "shortcode": item.get("code"),
                        "display_url": (
                            item.get("image_versions2", {}).get("candidates", [{}])[0].get("url")
                            or item.get("thumbnail_url")
                        ),
                        "edge_liked_by": {"count": item.get("like_count", 0)},
                        "edge_media_to_comment": {"count": item.get("comment_count", 0)},
                        "is_video": item.get("media_type") == 2 or item.get("is_video", False),
                        "video_view_count": item.get("play_count", item.get("view_count", 0)),
                        "video_url": (
                            item.get("video_versions", [{}])[0].get("url")
                            if item.get("video_versions")
                            else item.get("video_url")
                        ),
                        "edge_media_to_caption": {
                            "edges": [{"node": {"text": item.get("caption", {}).get("text", "") if item.get("caption") else ""}}]
                        },
                        "product_type": item.get("product_type", ""),
                        "taken_at_timestamp": item.get("taken_at"),
                    }
                }
            )
        return converted

    def _parse_consolidated_data(
        self,
        profile_data: dict[str, Any],
        all_edges: list[dict[str, Any]],
        username: str,
    ) -> dict[str, Any]:
        profile_followers = self._sanitize_stat(profile_data.get("edge_followed_by", {}).get("count", 0))
        seen_ids: set[str] = set()
        posts_list: list[dict[str, Any]] = []
        reels_list: list[dict[str, Any]] = []

        for edge in all_edges:
            node = edge.get("node", {})
            node_id = str(node.get("id") or node.get("pk") or "").strip()
            if not node_id or node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            caption = ""
            if node.get("edge_media_to_caption"):
                caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
                if caption_edges:
                    caption = str(caption_edges[0].get("node", {}).get("text", "") or "")
            elif node.get("caption"):
                raw_caption = node.get("caption")
                if isinstance(raw_caption, dict):
                    caption = str(raw_caption.get("text", "") or "")
                else:
                    caption = str(raw_caption or "")

            image_url = node.get("display_url") or node.get("thumbnail_url")
            if not image_url and node.get("image_versions2"):
                candidates = node.get("image_versions2", {}).get("candidates", [])
                if candidates:
                    image_url = candidates[0].get("url")
            if not image_url and node.get("thumbnail_src"):
                image_url = node.get("thumbnail_src")
            if not image_url:
                continue

            is_video = bool(node.get("is_video") or node.get("video_view_count") or node.get("media_type") == 2)
            is_reel = node.get("product_type") in {"clips", "reels"}
            video_url = node.get("video_url")
            if not video_url and node.get("video_versions"):
                versions = node.get("video_versions", [])
                if versions:
                    video_url = versions[0].get("url")
            if not video_url and node.get("video_resources"):
                resources = node.get("video_resources", [])
                if resources:
                    video_url = resources[-1].get("src")

            timestamp = self._normalize_timestamp(
                node.get("taken_at_timestamp") or node.get("taken_at") or node.get("timestamp")
            )
            item = {
                "id": node_id,
                "shortcode": node.get("shortcode") or node.get("code"),
                "display_url": image_url,
                "likes": self._sanitize_stat(node.get("edge_liked_by", {}).get("count") or node.get("like_count", 0)),
                "comments": self._sanitize_stat(
                    node.get("edge_media_to_comment", {}).get("count") or node.get("comment_count", 0)
                ),
                "is_video": is_video,
                "caption": caption,
                "video_views": self._sanitize_stat(node.get("video_view_count") or node.get("play_count", 0)),
                "video_url": video_url,
                "type": "reel" if is_reel or is_video else "post",
                "timestamp": timestamp,
            }

            if item["type"] == "reel":
                reels_list.append(item)
            else:
                posts_list.append(item)

        total_sample = len(posts_list) + len(reels_list)
        total_likes = sum(int(i["likes"]) for i in posts_list + reels_list)
        total_comments = sum(int(i["comments"]) for i in posts_list + reels_list)
        total_reel_views = sum(int(i["video_views"]) for i in reels_list)

        avg_likes = total_likes / total_sample if total_sample else 0.0
        avg_comments = total_comments / total_sample if total_sample else 0.0
        engagement_rate = ((avg_likes + avg_comments) / profile_followers * 100) if profile_followers > 0 else 0.0

        return {
            "username": username,
            "full_name": profile_data.get("full_name", ""),
            "biography": profile_data.get("biography", ""),
            "followers": profile_followers,
            "following": self._sanitize_stat(profile_data.get("edge_follow", {}).get("count", 0)),
            "posts_count": self._sanitize_stat(profile_data.get("edge_owner_to_timeline_media", {}).get("count", 0)),
            "profile_pic_url": profile_data.get("profile_pic_url_hd", profile_data.get("profile_pic_url", "")),
            "is_private": bool(profile_data.get("is_private")),
            "is_verified": bool(profile_data.get("is_verified")),
            "posts": posts_list,
            "reels": reels_list,
            "insights": {
                "total_likes": total_likes,
                "total_comments": total_comments,
                "total_reel_views": total_reel_views,
                "avg_likes": f"{avg_likes:,.0f}",
                "avg_comments": f"{avg_comments:,.0f}",
                "engagement_rate": f"{engagement_rate:.2f}%",
                "sample_size": total_sample,
            },
        }


def _resolve_session_id(session_id: str | None = None) -> str:
    resolved = (session_id or os.getenv(SESSION_ENV_VAR, "")).strip()
    if not resolved:
        raise RuntimeError(SESSION_ERROR_MESSAGE)
    return resolved


async def fetch_instagram_profile(username: str, session_id: str | None = None) -> dict[str, Any]:
    """Fetch profile payload containing posts and reels for fixture generation."""
    scraper = InstaScraper(_resolve_session_id(session_id))
    return await scraper.get_profile(username=username)
