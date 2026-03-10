from __future__ import annotations

from backend.app.tools.fixture_to_creator_input import build_creator_post_ai_input_from_fixture
from backend.app.tools.generate_ig_raw_fixtures import build_fixture_item


def test_build_fixture_item_reel_prefers_video_url() -> None:
    raw_item = {
        "id": "123",
        "shortcode": "abc",
        "type": "reel",
        "is_video": True,
        "display_url": "https://cdn.example/thumb.jpg",
        "video_url": "https://cdn.example/video.mp4",
        "caption": "new reel",
        "likes": 11,
        "comments": 2,
        "video_views": 99,
    }

    fixture_item = build_fixture_item(raw_item, follower_count=500)

    assert fixture_item["post_type"] == "REEL"
    assert fixture_item["media_url"] == "https://cdn.example/video.mp4"
    assert fixture_item["thumbnail_url"] == "https://cdn.example/thumb.jpg"
    assert fixture_item["caption_text"] == "new reel"
    assert fixture_item["like_count"] == 11
    assert fixture_item["comment_count"] == 2
    assert fixture_item["view_count"] == 99
    assert fixture_item["follower_count"] == 500


def test_build_fixture_item_defaults_caption_and_counts() -> None:
    raw_item = {
        "id": "999",
        "display_url": "https://cdn.example/post.jpg",
        "is_video": False,
    }

    fixture_item = build_fixture_item(raw_item, follower_count=None)

    assert fixture_item["post_type"] == "IMAGE"
    assert fixture_item["caption_text"] == ""
    assert fixture_item["like_count"] is None
    assert fixture_item["comment_count"] is None
    assert fixture_item["view_count"] is None
    assert fixture_item["follower_count"] is None


def test_build_creator_post_ai_input_from_fixture() -> None:
    fixture_item = {
        "post_id": "p_1",
        "shortcode": "short1",
        "post_type": "REEL",
        "media_url": "https://cdn.example/video.mp4",
        "thumbnail_url": "https://cdn.example/thumb.jpg",
        "caption_text": "",
        "like_count": None,
        "comment_count": None,
        "view_count": None,
        "follower_count": 1000,
        "raw": {"timestamp": "2025-01-01T10:00:00Z"},
    }

    post = build_creator_post_ai_input_from_fixture(fixture_item)

    assert post.post_id == "p_1"
    assert post.post_type == "REEL"
    assert post.media_url == "https://cdn.example/video.mp4"
    assert post.thumbnail_url == "https://cdn.example/thumb.jpg"
    assert post.caption_text == ""
    assert post.likes == 0
    assert post.comments == 0
    assert post.views is None
