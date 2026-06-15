from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.app.analytics.draft_optimizer_engine import optimize_draft_post
from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights


def _history_post(media_id: str = "p1") -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_1",
        media_id=media_id,
        media_type="REEL",
        media_url="https://example.com/post.jpg",
        caption_text="Historical caption",
        follower_count=1000,
        core_metrics=CoreMetrics(reach=1200, likes=80, comments=12, shares=6, saves=10),
        derived_metrics=DerivedMetrics(engagement_rate=8.0, save_rate=1.2, share_rate=0.8),
        benchmark_metrics=BenchmarkMetrics(),
    )


@patch("backend.app.analytics.draft_optimizer_engine.LLMClient")
def test_optimize_draft_post_success(mock_llm_client_cls) -> None:
    mock_llm = MagicMock()
    mock_llm.generate.return_value = """
optimized_caption_options
  - Lead with the before-and-after result, then ask people to save this workflow.
  - Start with a bold question, then invite followers to comment with their current process.
predicted_reach_band High
optimal_posting_times
  - Tuesdays 4:00 PM - 6:00 PM
  - Thursdays 9:00 AM - 11:00 AM
safety_flags
  - Avoid repeating giveaway-style trigger words
content_format_recommendation Turn this into a Reel because your recent Reels outperform static posts
tone_alignment_warning
""".strip()
    mock_llm_client_cls.return_value = mock_llm

    result = asyncio.run(
        optimize_draft_post(
            draft_caption="my draft",
            post_type="REEL",
            media_url=None,
            account_data={"account_id": "acct_1", "username": "creator"},
            historical_posts=[_history_post()],
        )
    )

    assert len(result.optimized_caption_options) == 2
    assert result.predicted_reach_band == "High"
    assert result.optimal_posting_times == [
        "Tuesdays 4:00 PM - 6:00 PM",
        "Thursdays 9:00 AM - 11:00 AM",
    ]
    assert result.visual_analysis is None


@patch("backend.app.analytics.draft_optimizer_engine.LLMClient")
def test_optimize_draft_post_fallback_on_error(mock_llm_client_cls) -> None:
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("llm down")
    mock_llm_client_cls.return_value = mock_llm

    result = asyncio.run(
        optimize_draft_post(
            draft_caption="my draft",
            post_type="IMAGE",
            media_url=None,
            account_data={"account_id": "acct_1"},
            historical_posts=[_history_post()],
        )
    )

    assert result.predicted_reach_band == "Average"
    assert result.optimized_caption_options == []
    assert result.content_format_recommendation


@patch("backend.app.analytics.draft_optimizer_engine.LLMClient")
@patch("backend.app.analytics.draft_optimizer_engine.run_vision_analysis")
def test_optimize_draft_post_includes_visual_analysis(mock_run_vision_analysis, mock_llm_client_cls) -> None:
    mock_llm = MagicMock()
    mock_llm.generate.return_value = """
optimized_caption_options
  - Keep the hook direct and ask viewers to save this.
  - Open with the payoff, then ask a quick comment question.
predicted_reach_band Average
optimal_posting_times
  - Wednesdays 1:00 PM - 3:00 PM
  - Fridays 10:00 AM - 12:00 PM
safety_flags
  - None
content_format_recommendation Keep it as a Reel
tone_alignment_warning
""".strip()
    mock_llm_client_cls.return_value = mock_llm
    mock_run_vision_analysis.return_value = {
        "signals": [
            {
                "visual_quality_score": {"composition": 8.0, "lighting": 7.0, "subject_clarity": 8.0, "aesthetic_quality": 7.0},
                "hook_strength_score": 0.71,
                "primary_objects": ["creator", "laptop"],
                "detected_text": "3 editing mistakes",
                "lighting_feedback": "Lighting is slightly flat",
                "composition_feedback": "Subject is clear but the frame is busy",
                "aesthetic_fixes": ["Increase contrast", "Crop tighter"],
                "is_cringe": False,
                "adult_content_detected": False,
            }
        ]
    }

    result = asyncio.run(
        optimize_draft_post(
            draft_caption="my draft",
            post_type="REEL",
            media_url="https://example.com/draft.jpg",
            account_data={"account_id": "acct_1", "follower_count": 1000},
            historical_posts=[_history_post()],
        )
    )

    assert result.visual_analysis is not None
    assert result.visual_analysis.visual_quality_score == 8
    assert result.visual_analysis.primary_objects == ["creator", "laptop"]


@patch("backend.app.analytics.draft_optimizer_engine.LLMClient")
@patch("backend.app.analytics.draft_optimizer_engine.run_vision_analysis")
def test_optimize_draft_post_normalizes_boolean_visual_flags(mock_run_vision_analysis, mock_llm_client_cls) -> None:
    mock_llm = MagicMock()
    mock_llm.generate.return_value = """
optimized_caption_options
  - Keep the hook direct and ask viewers to save this.
predicted_reach_band Average
optimal_posting_times
  - Wednesdays 1:00 PM - 3:00 PM
safety_flags
  - None
content_format_recommendation Keep it as a Reel
tone_alignment_warning
""".strip()
    mock_llm_client_cls.return_value = mock_llm
    mock_run_vision_analysis.return_value = {
        "signals": [
            {
                "visual_quality_score": {"composition": 8.0, "lighting": 7.0, "subject_clarity": 8.0, "aesthetic_quality": 7.0},
                "hook_strength_score": 0.71,
                "primary_objects": ["creator", "laptop"],
                "detected_text": "3 editing mistakes",
                "lighting_feedback": "Lighting is slightly flat",
                "composition_feedback": "Subject is clear but the frame is busy",
                "aesthetic_fixes": ["Increase contrast", "Crop tighter"],
                "is_cringe": "false",
                "adult_content_detected": "true",
            }
        ]
    }

    result = asyncio.run(
        optimize_draft_post(
            draft_caption="my draft",
            post_type="REEL",
            media_url="https://example.com/draft.jpg",
            account_data={"account_id": "acct_1", "follower_count": 1000},
            historical_posts=[_history_post()],
        )
    )

    assert result.visual_analysis is not None
    assert result.visual_analysis.is_cringe is False
    assert result.visual_analysis.adult_content_detected is True
