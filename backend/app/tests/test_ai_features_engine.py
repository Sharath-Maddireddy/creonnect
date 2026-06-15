import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from backend.app.analytics.ai_features_engine import (
    _build_prompt_payload,
    generate_ai_feature_predictions,
    generate_ai_feature_predictions_sync,
)
from backend.app.domain.account_models import AIFeaturePredictions
from backend.app.domain.post_models import SinglePostInsights

@pytest.fixture
def mock_posts():
    return [
        SinglePostInsights.model_construct(
            media_id="p1", 
            media_type="REEL", 
            follower_count=1000,
            caption_text="Test caption"
        )
    ]

@pytest.fixture
def mock_account_data():
    return {"follower_count": 1000, "username": "testuser", "draft_caption": "My draft caption"}

@patch("backend.app.analytics.ai_features_engine.LLMClient")
def test_generate_ai_feature_predictions_success(mock_llm_client_cls, mock_posts, mock_account_data):
    # Setup mock LLM
    mock_llm = MagicMock()
    mock_llm.generate.return_value = """
optimized_caption_options
  - Start with the surprising result, then invite people to save this for later.
  - Ask a direct question up front, then close with a clear comment CTA.
predicted_reach_band High
optimal_posting_times
  - Tuesdays 4:00 PM - 6:00 PM
  - Thursdays 9:00 AM - 11:00 AM
safety_flags
  - Shadowban risk: repetitive use of giveaway language
content_format_recommendation Turn this into a 7-second Reel for maximum reach
tone_alignment_warning
"""
    mock_llm_client_cls.return_value = mock_llm

    result = asyncio.run(generate_ai_feature_predictions(mock_posts, mock_account_data))

    assert isinstance(result, AIFeaturePredictions)
    assert len(result.optimized_caption_options) == 2
    assert result.predicted_reach_band == "High"
    assert result.optimal_posting_times == [
        "Tuesdays 4:00 PM - 6:00 PM",
        "Thursdays 9:00 AM - 11:00 AM",
    ]
    assert result.safety_flags == ["Shadowban risk: repetitive use of giveaway language"]
    assert result.content_format_recommendation == "Turn this into a 7-second Reel for maximum reach"
    assert result.tone_alignment_warning == ""
    assert result.campaign_roi_prediction == "High"
    assert result.best_posting_time == result.optimal_posting_times
    mock_llm.generate.assert_called_once()

@patch("backend.app.analytics.ai_features_engine.LLMClient")
def test_generate_ai_feature_predictions_fallback_on_error(mock_llm_client_cls, mock_posts, mock_account_data):
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = Exception("LLM went down")
    mock_llm_client_cls.return_value = mock_llm

    result = asyncio.run(generate_ai_feature_predictions(mock_posts, mock_account_data))

    assert isinstance(result, AIFeaturePredictions)
    assert result.predicted_reach_band == "Average"
    assert result.optimized_caption_options == []
    assert result.campaign_roi_prediction == "Unknown"
    assert result.audience_authenticity_score == 50.0

def test_build_prompt_payload(mock_posts, mock_account_data):
    payload = _build_prompt_payload(mock_posts, mock_account_data)
    assert payload["account"]["username"] == "testuser"
    assert payload["draft_caption"] == "My draft caption"
    assert payload["historical_post_count"] == 1
    assert len(payload["historical_posts"]) == 1
    assert payload["recent_captions"] == ["Test caption"]


@patch("backend.app.analytics.ai_features_engine.generate_ai_feature_predictions", new_callable=AsyncMock)
def test_generate_ai_feature_predictions_sync_inside_running_loop(
    mock_async_predictions, mock_posts, mock_account_data
):
    expected = AIFeaturePredictions(
        optimized_caption_options=["Caption option 1", "Caption option 2"],
        predicted_reach_band="Average",
        optimal_posting_times=["Tuesday 4:00 PM - 6:00 PM"],
        safety_flags=[],
        content_format_recommendation="Keep it as a feed post.",
        tone_alignment_warning="",
    )
    mock_async_predictions.return_value = expected

    async def _invoke_sync_wrapper() -> AIFeaturePredictions:
        return generate_ai_feature_predictions_sync(mock_posts, mock_account_data)

    result = asyncio.run(_invoke_sync_wrapper())

    assert isinstance(result, AIFeaturePredictions)
    assert result == expected


@patch("backend.app.analytics.ai_features_engine.generate_ai_feature_predictions", new_callable=AsyncMock)
def test_generate_ai_feature_predictions_sync_cache_depends_on_draft_caption(
    mock_async_predictions, mock_posts
):
    mock_async_predictions.side_effect = [
        AIFeaturePredictions(predicted_reach_band="Low"),
        AIFeaturePredictions(predicted_reach_band="High"),
    ]

    first = generate_ai_feature_predictions_sync(
        mock_posts,
        {"account_id": "acct_1", "follower_count": 1000, "draft_caption": "First draft"},
    )
    second = generate_ai_feature_predictions_sync(
        mock_posts,
        {"account_id": "acct_1", "follower_count": 1000, "draft_caption": "Second draft"},
    )

    assert first.predicted_reach_band == "Low"
    assert second.predicted_reach_band == "High"
    assert mock_async_predictions.await_count == 2
