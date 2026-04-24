from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.services import dashboard_service


def _fake_profile() -> SimpleNamespace:
    return SimpleNamespace(
        username="creator_name",
        followers_count=10_000,
        avg_views=2_000,
        avg_likes=300,
        avg_comments=25,
    )


def _fake_post() -> SimpleNamespace:
    return SimpleNamespace(
        post_id="post-1",
        post_type="IMAGE",
        media_url="https://example.com/post.jpg",
        thumbnail_url="https://example.com/post-thumb.jpg",
        caption_text="Caption",
        hashtags=["test"],
        likes=100,
        comments=10,
        views=1000,
        audio_name=None,
        posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _patch_dashboard_dependencies(monkeypatch, profile: SimpleNamespace, posts: list[SimpleNamespace]) -> None:
    monkeypatch.setattr(dashboard_service, "detect_creator_niche", lambda *_args, **_kwargs: {"primary_niche": "fitness"})
    monkeypatch.setattr(
        dashboard_service,
        "compute_growth_score",
        lambda *_args, **_kwargs: {
            "growth_score": 72.0,
            "metrics": {
                "avg_views": 2000,
                "avg_engagement_rate_by_views": 0.15,
                "views_to_followers_ratio": 0.2,
                "posts_per_week": 3.0,
            },
        },
    )
    monkeypatch.setattr(
        dashboard_service,
        "analyze_posts",
        lambda *_args, **_kwargs: [
            {
                "engagement_rate_by_views": 0.15,
                "like_rate": 0.1,
                "comment_rate": 0.01,
                "total_interactions": 110,
            }
        ],
    )
    monkeypatch.setattr(dashboard_service, "calculate_momentum", lambda _snapshots: {"label": "steady"})
    monkeypatch.setattr(dashboard_service, "get_best_posting_hours", lambda _posts: {"hours": [9, 18]})
    monkeypatch.setattr(dashboard_service, "retrieve", lambda *_args, **_kwargs: ["tip"])
    monkeypatch.setattr(dashboard_service, "generate_action_plan", lambda **_kwargs: {"actions": ["post consistently"]})
    monkeypatch.setattr(dashboard_service, "build_creator_snapshot", lambda *_args, **_kwargs: {"ok": True})


def test_build_creator_dashboard_marks_demo_authenticity_unavailable(monkeypatch) -> None:
    profile = _fake_profile()
    posts = [_fake_post()]
    monkeypatch.setattr(dashboard_service, "load_synthetic", lambda: (profile, posts))
    _patch_dashboard_dependencies(monkeypatch, profile, posts)

    result = dashboard_service.build_creator_dashboard("demo")

    assert result["authenticity_analysis"]["available"] is False
    assert result["authenticity_analysis"]["score"] is None
    assert result["authenticity_analysis"]["band"] == "unavailable"
    assert "synthetic" in result["authenticity_analysis"]["note"].lower()


def test_build_creator_dashboard_keeps_real_authenticity_for_oauth_data(monkeypatch) -> None:
    profile = _fake_profile()
    posts = [_fake_post()]

    async def _fake_fetch_profile(_token: str) -> dict:
        return {"id": "123"}

    async def _fake_fetch_media(_token: str, limit: int = 30) -> list[dict]:
        return [{"id": "media-1", "limit": limit}]

    monkeypatch.setattr(dashboard_service, "fetch_instagram_profile", _fake_fetch_profile)
    monkeypatch.setattr(dashboard_service, "fetch_instagram_media", _fake_fetch_media)
    monkeypatch.setattr(dashboard_service, "map_instagram_to_ai_inputs", lambda *_args, **_kwargs: (profile, posts))
    monkeypatch.setattr(dashboard_service, "calculate_authenticity_score", lambda **_kwargs: 88.0)
    _patch_dashboard_dependencies(monkeypatch, profile, posts)

    result = dashboard_service.build_creator_dashboard("demo", access_token="token")

    assert result["authenticity_analysis"]["available"] is True
    assert result["authenticity_analysis"]["score"] == 88.0
    assert result["authenticity_analysis"]["band"] == "high"
