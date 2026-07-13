"""Tests for the shared account source layer."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.app.account_sources.factory import materialize_account_source_payload


def test_materialize_fixture_source_returns_normalized_posts(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "username": "fixture_user",
                "biography": "Fixture bio",
                "followers": 3210,
                "items": [
                    {
                        "post_id": "p_1",
                        "post_type": "REEL",
                        "media_url": "https://cdn.example/video.mp4",
                        "thumbnail_url": "https://cdn.example/thumb.jpg",
                        "caption_text": "hello #fitness",
                        "like_count": 10,
                        "comment_count": 2,
                        "view_count": 120,
                        "follower_count": 3210,
                        "raw": {"timestamp": "2026-01-01T10:00:00Z"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = asyncio.run(
        materialize_account_source_payload(
            {
                "source": "fixture",
                "fixture_path": str(fixture_path),
                "post_limit": 5,
            },
            post_limit=5,
        )
    )

    assert result["source"] == "fixture"
    assert result["account_id"] == "fixture_user"
    assert result["username"] == "fixture_user"
    assert result["bio"] == "Fixture bio"
    assert result["follower_count"] == 3210
    assert len(result["posts"]) == 1
    assert result["posts"][0]["media_id"] == "p_1"
    assert result["posts"][0]["media_type"] == "REEL"
    assert result["posts"][0]["core_metrics"]["likes"] == 10


def test_materialize_creonnect_bd_source_pages_posts(monkeypatch) -> None:
    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN002, ANN003
            return None

        async def get_creator_profile(self) -> dict[str, Any]:
            return {"creator": {"niches": ["fitness", "lifestyle"]}}

        async def list_connections(self, *, platform: str = "instagram", include_disconnected: bool = False):
            assert platform == "instagram"
            assert include_disconnected is False
            return [
                {
                    "id": "conn_1",
                    "platformUserId": "ig_123",
                    "platformUsername": "creator_one",
                    "platformProfile": {"followers_count": 1234},
                }
            ]

        async def list_posts_page(self, *, platform: str = "instagram", connection_id: str, page: int, limit: int):
            assert platform == "instagram"
            assert connection_id == "conn_1"
            assert limit == 2
            if page == 1:
                return {
                    "posts": [
                        {
                            "platformPostId": "post_1",
                            "postType": "reel",
                            "mediaType": "VIDEO",
                            "storagePublicUrl": "https://cdn.example/storage_post_1.mp4",
                            "sourceMediaUrl": "https://cdn.example/source_post_1.mp4",
                            "thumbnailUrl": "https://cdn.example/post_1.jpg",
                            "caption": "one",
                            "postedAt": "2026-01-01T10:00:00Z",
                            "latestPostMetrics": {"metrics_core": {"likes": 11, "comments": 1, "views": 101}},
                        },
                        {
                            "platformPostId": "post_2",
                            "postType": "post",
                            "mediaType": "IMAGE",
                            "sourceMediaUrl": "https://cdn.example/source_post_2.jpg",
                            "caption": "two",
                            "postedAt": "2026-01-02T10:00:00Z",
                            "latestPostMetrics": {"metrics_core": {"likes": 22, "comments": 2, "reach": 202}},
                        },
                    ],
                    "pagination": {"hasNext": True},
                }
            return {
                "posts": [
                    {
                        "platformPostId": "post_3",
                        "postType": "post",
                        "mediaType": "IMAGE",
                        "mediaUrl": "https://cdn.example/post_3.jpg",
                        "caption": "three",
                        "postedAt": "2026-01-03T10:00:00Z",
                        "latestPostMetrics": {"metrics_core": {"likes": 33, "comments": 3, "reach": 303}},
                    }
                ],
                "pagination": {"hasNext": False},
            }

    monkeypatch.setattr(
        "backend.app.account_sources.creonnect_bd_source.CreonnectBDClient",
        _FakeClient,
    )

    payload = asyncio.run(
        materialize_account_source_payload(
            {
                "source": "creonnect_bd",
                "connection_id": "conn_1",
                "bd_base_url": "http://bd.local",
                "post_limit": 2,
            },
            post_limit=2,
        )
    )

    assert payload["source"] == "creonnect_bd"
    assert payload["account_id"] == "ig_123"
    assert payload["username"] == "creator_one"
    assert payload["follower_count"] == 1234
    assert len(payload["posts"]) == 2
    assert payload["posts"][0]["media_id"] == "post_1"
    assert payload["posts"][0]["media_url"] == "https://cdn.example/storage_post_1.mp4"
    assert payload["posts"][0]["media_type"] == "REEL"
    assert payload["posts"][1]["media_url"] == "https://cdn.example/source_post_2.jpg"
    assert payload["posts"][1]["core_metrics"]["reach"] == 202
