from __future__ import annotations

from unittest.mock import patch

from backend.app.analytics.creator_scoring_engine import _score_three_band, generate_creator_score
from backend.app.domain.account_models import AIFeaturePredictions
from backend.app.domain.post_models import CoreMetrics, DerivedMetrics, SinglePostInsights


def _post(
    media_type: str,
    followers: int | None = 1000,
    reach: int | None = 500,
    likes: int | None = 20,
    comments: int | None = 5,
    shares: int | None = 3,
    saves: int | None = 4,
) -> SinglePostInsights:
    return SinglePostInsights(
        media_type=media_type,
        follower_count=followers,
        core_metrics=CoreMetrics(
            reach=reach,
            likes=likes,
            comments=comments,
            shares=shares,
            saves=saves,
        ),
        derived_metrics=DerivedMetrics(),
    )


@patch("backend.app.analytics.creator_scoring_engine.generate_ai_feature_predictions_sync")
def test_creator_score_empty_posts_coverage_and_confidence(mock_ai_features) -> None:
    mock_ai_features.return_value = AIFeaturePredictions(prediction_status="ok")

    result = generate_creator_score([], {"follower_count": 1000})

    assert result.coverage is not None
    assert result.coverage.posts_considered == 0
    assert result.coverage.zero_denominator_events == 0
    assert result.confidence is not None
    assert result.confidence.status == "degraded"
    assert "low_post_volume" in result.confidence.reasons


@patch("backend.app.analytics.creator_scoring_engine.generate_ai_feature_predictions_sync")
def test_creator_score_zero_denominator_tracking(mock_ai_features) -> None:
    mock_ai_features.return_value = AIFeaturePredictions(prediction_status="ok")

    posts = [_post(media_type="REEL", followers=0, reach=0)]
    result = generate_creator_score(posts, {"follower_count": 0})

    assert result.coverage is not None
    assert result.coverage.zero_denominator_events > 0
    assert result.confidence is not None
    assert "zero_denominator_inputs" in result.confidence.reasons


@patch("backend.app.analytics.creator_scoring_engine.generate_ai_feature_predictions_sync")
def test_creator_score_mixed_media_story_signal_and_ai_degraded(mock_ai_features) -> None:
    mock_ai_features.return_value = AIFeaturePredictions(prediction_status="degraded", degraded_reason="llm_prediction_failed")

    posts = [
        _post(media_type="REEL", reach=700),
        _post(media_type="STORY", reach=20),
        _post(media_type="IMAGE", reach=400),
    ]
    result = generate_creator_score(posts, {"follower_count": 1000})

    assert result.fake_follower_signals.inactive_followers is True
    assert result.coverage is not None
    assert result.coverage.posts_considered == 3
    assert result.confidence is not None
    assert "ai_predictions_degraded" in result.confidence.reasons


@patch("backend.app.analytics.creator_scoring_engine.generate_ai_feature_predictions_sync")
def test_creator_score_uses_positive_growth_signals(mock_ai_features) -> None:
    mock_ai_features.return_value = AIFeaturePredictions(prediction_status="ok")

    result = generate_creator_score(
        [_post(media_type="REEL", reach=700) for _ in range(5)],
        {
            "follower_count": 10_000,
            "previous_follower_count": 9_500,
            "followers_lost": 50,
            "daily_follower_deltas": [12, 14, 13, 15, 14],
        },
    )

    assert result.growth_metrics.follower_growth_flag == "Steady"
    assert result.growth_metrics.net_growth_flag == "Positive"
    assert result.growth_metrics.growth_velocity_flag == "Consistent"
    assert result.growth_metrics.unfollow_rate_flag == "Healthy"
    assert "missing_growth_metrics" not in result.confidence.reasons


@patch("backend.app.analytics.creator_scoring_engine.generate_ai_feature_predictions_sync")
def test_creator_score_flags_spiky_growth_and_unfollows(mock_ai_features) -> None:
    mock_ai_features.return_value = AIFeaturePredictions(prediction_status="ok")

    result = generate_creator_score(
        [_post(media_type="REEL", reach=700) for _ in range(5)],
        {
            "follower_count": 10_000,
            "previous_follower_count": 7_000,
            "followers_lost": 700,
            "daily_follower_deltas": [5, 6, 800, 4, 7],
        },
    )

    assert result.growth_metrics.follower_growth_flag == "Huge Spikes"
    assert result.growth_metrics.net_growth_flag == "Positive"
    assert result.growth_metrics.growth_velocity_flag == "Sudden Jumps"
    assert result.growth_metrics.unfollow_rate_flag == "Bad Signal"
    assert result.fake_follower_signals.possible_bought_followers is True


def test_three_band_score_preserves_partial_excellence() -> None:
    assert _score_three_band(["Good", "Good", "Good", "Neutral"], "Good", "Bad") == 87.5
