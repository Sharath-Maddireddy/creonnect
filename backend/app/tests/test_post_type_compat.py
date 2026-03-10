"""Backward-compatibility tests for post_type values."""

from __future__ import annotations

from backend.app.api.post_analysis_routes import PostAnalysisRequest
from backend.app.ingestion.instagram_mapper import map_instagram_posts, map_instagram_posts_legacy


def test_instagram_mapper_normalizes_lowercase_media_type() -> None:
    posts = map_instagram_posts(
        [
            {
                "id": "p1",
                "username": "creator",
                "media_type": "video",
                "video_url": "https://cdn.example/video.mp4",
                "thumbnail_url": "https://cdn.example/thumb.jpg",
            }
        ]
    )
    assert len(posts) == 1
    assert posts[0].post_type == "REEL"


def test_instagram_mapper_legacy_output_uses_lowercase_post_type() -> None:
    legacy = map_instagram_posts_legacy(
        [
            {
                "id": "p_reel",
                "username": "creator",
                "media_type": "REEL",
                "video_url": "https://cdn.example/video.mp4",
            },
            {
                "id": "p_image",
                "username": "creator",
                "media_type": "IMAGE",
                "media_url": "https://cdn.example/image.jpg",
            },
        ]
    )
    assert [item["post_type"] for item in legacy] == ["reel", "post"]


def test_post_analysis_request_accepts_legacy_post_type_values() -> None:
    reel_request = PostAnalysisRequest.model_validate(
        {
            "post_type": "reel",
            "media_url": "https://example.com/reel.mp4",
        }
    )
    post_request = PostAnalysisRequest.model_validate(
        {
            "post_type": "post",
            "media_url": "https://example.com/post.jpg",
        }
    )
    assert reel_request.post_type == "REEL"
    assert post_request.post_type == "IMAGE"
