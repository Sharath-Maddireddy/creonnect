"""Test verifying that account analysis runs upsert_creator properly."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from backend.app.services.account_analysis_jobs import run_account_analysis_job
from backend.app.domain.account_models import AccountHealthScore, PillarScore


class MockJob:
    id = "test-job-id"


@patch("backend.app.services.account_analysis_jobs.analyze_account_health")
@patch("backend.app.services.account_analysis_jobs.upsert_creator")
@patch("backend.app.services.account_analysis_jobs._fetch_posts_from_source")
@patch("backend.app.services.account_analysis_jobs.get_current_job", return_value=MockJob())
@patch("backend.app.services.account_analysis_jobs._write_dedupe_job_id")
@patch("backend.app.services.account_analysis_jobs._update_status")
@patch("backend.app.services.account_analysis_jobs.asyncio.run")
def test_run_account_analysis_job_triggers_upsert_creator(
    mock_asyncio_run,
    mock_update_status,
    mock_write_dedupe,
    mock_get_current_job,
    mock_fetch_posts,
    mock_upsert_creator,
    mock_analyze_health,
) -> None:
    # Setup mocks
    mock_fetch_posts.return_value = []
    
    mock_asyncio_run.return_value = {
        "posts": [],
        "notes_by_post_id": {},
        "warnings": [],
        "per_post_warnings_count": {},
        "vision_error_count": 0,
        "ai_fallback_count": 0,
    }

    mock_analyze_health.return_value = AccountHealthScore(
        ahs_score=85.0,
        pillars={
            "content_quality": PillarScore(score=80.0),
            "engagement_quality": PillarScore(score=90.0),
            "brand_safety": PillarScore(score=100.0)
        }
    )

    payload = {
        "job_id": "test-job-id",
        "account_id": "test_account",
        "username": "testuser",
        "bio": "test bio",
        "follower_count": 10000,
        "creator_dominant_category": "tech",
        "niche_tags": ["coding"],
        "post_limit": 10
    }

    # Execute
    run_account_analysis_job(payload)

    # Verify upsert_creator was called with mapped metadata
    mock_upsert_creator.assert_called_once()
    called_args = mock_upsert_creator.call_args[0][0]
    assert called_args["account_id"] == "test_account"
    assert called_args["username"] == "testuser"
    assert called_args["bio"] == "test bio"
    assert called_args["follower_count"] == 10000
    assert called_args["creator_dominant_category"] == "tech"
    assert called_args["niche_tags"] == ["coding"]
    assert called_args["ahs_score"] == 85.0
    assert called_args["avg_visual_quality_score"] == 80.0
    assert called_args["predicted_engagement_rate"] == 90.0
    assert called_args["avg_brand_safety_score"] == 100.0
