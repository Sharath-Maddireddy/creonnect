"""API routes for account analysis background orchestration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.utils.logger import logger
from backend.app.services.account_analysis_jobs import (
    AccountAnalysisRateLimitError,
    enqueue_account_analysis_job,
    get_account_analysis_job_status,
)


router = APIRouter(prefix="/api", tags=["Account Analysis"])


class AccountAnalysisRequest(BaseModel):
    """Request payload for account analysis enqueue endpoint."""

    model_config = ConfigDict(extra="forbid")

    account_id: str
    post_limit: int = Field(default=30, ge=1, le=30)
    account_avg_engagement_rate: float | None = None
    niche_avg_engagement_rate: float | None = None
    follower_band: str | None = None
    posts: list[dict[str, Any]] | None = None
    include_posts_summary: bool = False
    include_posts_summary_max: int = Field(default=30, ge=1, le=30)


@router.post("/account-analysis")
def enqueue_account_analysis(request: AccountAnalysisRequest) -> dict[str, str]:
    """Enqueue account analysis background job and return job_id."""
    payload = request.model_dump(mode="python")
    try:
        return enqueue_account_analysis_job(payload)
    except AccountAnalysisRateLimitError as exc:
        detail: dict[str, Any] = {"message": exc.message}
        if exc.job_id is not None:
            detail["job_id"] = exc.job_id
        raise HTTPException(status_code=429, detail=detail)
    except Exception as exc:
        logger.exception("[AccountAnalysis] Failed to enqueue account analysis job")
        raise HTTPException(status_code=500, detail="Failed to enqueue account analysis job") from exc


@router.get("/account-analysis/{job_id}")
def get_account_analysis_status(job_id: str) -> dict[str, Any]:
    """Poll account analysis job status/result from Redis."""
    status = get_account_analysis_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    return status
