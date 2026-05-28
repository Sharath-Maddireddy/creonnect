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
    return {"follower_count": 1000, "username": "testuser"}

@patch("backend.app.analytics.ai_features_engine.LLMClient")
def test_generate_ai_feature_predictions_success(mock_llm_client_cls, mock_posts, mock_account_data):
    # Setup mock LLM
    mock_llm = MagicMock()
    mock_llm.generate.return_value = """
viral_probability 0.8
campaign_roi_prediction High
best_posting_time
  - Morning
  - Evening
audience_authenticity_score 95.0
spam_detected_count 1
sentiment_score 0.5
"""
    mock_llm_client_cls.return_value = mock_llm

    result = asyncio.run(generate_ai_feature_predictions(mock_posts, mock_account_data))

    assert isinstance(result, AIFeaturePredictions)
    assert result.viral_probability == 0.8
    assert result.campaign_roi_prediction == "High"
    assert result.best_posting_time == ["Morning", "Evening"]
    assert result.audience_authenticity_score == 95.0
    assert result.spam_detected_count == 1
    assert result.sentiment_score == 0.5
    mock_llm.generate.assert_called_once()

@patch("backend.app.analytics.ai_features_engine.LLMClient")
def test_generate_ai_feature_predictions_fallback_on_error(mock_llm_client_cls, mock_posts, mock_account_data):
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = Exception("LLM went down")
    mock_llm_client_cls.return_value = mock_llm

    result = asyncio.run(generate_ai_feature_predictions(mock_posts, mock_account_data))

    assert isinstance(result, AIFeaturePredictions)
    # Check fallback values
    assert result.viral_probability == 0.05
    assert result.campaign_roi_prediction == "Unknown"
    assert result.audience_authenticity_score == 50.0

def test_build_prompt_payload(mock_posts, mock_account_data):
    payload = _build_prompt_payload(mock_posts, mock_account_data)
    assert payload["account"]["username"] == "testuser"
    assert payload["post_count"] == 1
    assert len(payload["recent_posts"]) == 1
    assert payload["recent_captions"] == ["Test caption"]


@patch("backend.app.analytics.ai_features_engine.generate_ai_feature_predictions", new_callable=AsyncMock)
def test_generate_ai_feature_predictions_sync_inside_running_loop(
    mock_async_predictions, mock_posts, mock_account_data
):
    expected = AIFeaturePredictions(
        viral_probability=0.42,
        campaign_roi_prediction="2x - 3x",
        best_posting_time=["Tuesday 4:00 PM - 6:00 PM"],
        audience_authenticity_score=88.0,
        spam_detected_count=1,
        sentiment_score=0.3,
    )
    mock_async_predictions.return_value = expected

    async def _invoke_sync_wrapper() -> AIFeaturePredictions:
        return generate_ai_feature_predictions_sync(mock_posts, mock_account_data)

    result = asyncio.run(_invoke_sync_wrapper())

    assert isinstance(result, AIFeaturePredictions)
    assert result == expected
