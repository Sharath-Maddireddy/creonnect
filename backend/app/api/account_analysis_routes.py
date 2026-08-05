"""API routes for account analysis background orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.account_models import AccountHealthScore
from backend.app.domain.creator_intelligence_report_models import CreatorIntelligenceReport
from backend.app.services.creator_intelligence_report_store import get_latest_creator_intelligence_report
from backend.app.utils.logger import logger
from backend.app.services.account_analysis_jobs import (
    AccountAnalysisRateLimitError,
    enqueue_account_analysis_job_async,
    get_account_analysis_job_status,
)
from backend.app.api.instagram_auth_routes import AuthenticatedInstagramUser, get_current_instagram_user
from backend.app.infra.token_store import get_token_async


router = APIRouter(
    prefix="/api",
    tags=["Account Analysis"],
    dependencies=[Depends(get_current_instagram_user)],
)


class AccountAnalysisRequest(BaseModel):
    """Request payload for account analysis enqueue endpoint."""

    model_config = ConfigDict(extra="forbid")

    account_id: str | None = None
    username: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    creator_dominant_category: str | None = None
    niche_tags: list[str] | None = None
    post_limit: int = Field(default=30, ge=1, le=30)
    account_avg_engagement_rate: float | None = None
    niche_avg_engagement_rate: float | None = None
    follower_band: str | None = None
    posts: list[dict[str, Any]] | None = None
    source: str | None = None
    fixture_path: str | None = None
    connection_id: str | None = None
    bd_base_url: str | None = None
    bd_timeout_seconds: float | None = None
    actor_user_id: str | None = None
    actor_user_email: str | None = None
    include_posts_summary: bool = False
    include_posts_summary_max: int = Field(default=30, ge=1, le=30)


class AccountAnalysisEnqueueResponse(BaseModel):
    """Response payload for the enqueue endpoint."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str


class AccountAnalysisProgressResponse(BaseModel):
    """Progress counters for a running account-analysis job."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    done: int
    total: int


class AccountAnalysisErrorResponse(BaseModel):
    """Structured error payload returned for failed jobs."""

    model_config = ConfigDict(extra="forbid")

    type: str
    message: str


class AccountAnalysisWarningResponse(BaseModel):
    """Structured warning emitted during account-analysis execution."""

    model_config = ConfigDict(extra="allow")


class AccountAnalysisQualityResponse(BaseModel):
    """Execution quality metadata returned with account-analysis results."""

    model_config = ConfigDict(extra="allow")


class AccountAnalysisResultResponse(AccountHealthScore):
    """Frontend-facing account health payload returned by the polling endpoint."""

    model_config = ConfigDict(extra="forbid")

    creator_score: dict[str, Any] | None = None
    posts_summary: list[dict[str, Any]] | None = None


class AccountAnalysisStatusResponse(BaseModel):
    """Polling response payload for account-analysis jobs."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: Literal["queued", "started", "succeeded", "failed"]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: AccountAnalysisProgressResponse | None = None
    error: AccountAnalysisErrorResponse | None = None
    result: AccountAnalysisResultResponse | None = None
    warnings: list[AccountAnalysisWarningResponse] = Field(default_factory=list)
    quality: AccountAnalysisQualityResponse | None = None


@router.get("/creator-intelligence/latest", response_model=CreatorIntelligenceReport)
def get_latest_creator_intelligence(
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> CreatorIntelligenceReport:
    """Return the authenticated creator's newest persisted intelligence report."""
    report = get_latest_creator_intelligence_report(current_user.id)
    if report is None:
        raise HTTPException(status_code=404, detail="No Creator Intelligence report is available yet.")
    return report


@router.post("/account-analysis", response_model=AccountAnalysisEnqueueResponse)
async def enqueue_account_analysis(
    request: AccountAnalysisRequest,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> AccountAnalysisEnqueueResponse:
    """Enqueue account analysis background job and return job_id."""
    payload = request.model_dump(mode="python")
    if payload.get("account_id") and str(payload["account_id"]) != current_user.id:
        raise HTTPException(status_code=403, detail="You are not allowed to analyze this account.")
    payload["account_id"] = current_user.id
    if not isinstance(payload.get("posts"), list) and not payload.get("source"):
        token = await get_token_async(current_user.id)
        access_token = token.get("access_token") if isinstance(token, dict) else None
        if isinstance(access_token, str) and access_token:
            payload["source"] = "instagram_oauth"
            payload["access_token"] = access_token
    try:
        response = await enqueue_account_analysis_job_async(payload)
        return AccountAnalysisEnqueueResponse.model_validate(response)
    except AccountAnalysisRateLimitError as exc:
        detail: dict[str, Any] = {"message": exc.message}
        if exc.job_id is not None:
            detail["job_id"] = exc.job_id
        raise HTTPException(status_code=429, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[AccountAnalysis] Failed to enqueue account analysis job")
        raise HTTPException(status_code=500, detail="Failed to enqueue account analysis job") from exc


@router.get("/account-analysis/{job_id}", response_model=AccountAnalysisStatusResponse)
def get_account_analysis_status(
    job_id: str,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> AccountAnalysisStatusResponse:
    """Poll account analysis job status/result from Redis."""
    status = get_account_analysis_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    if str(status.get("account_id") or "") != current_user.id:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    response_payload = dict(status)
    response_payload.pop("account_id", None)
    return AccountAnalysisStatusResponse.model_validate(response_payload)

AccountAnalysisStatusResponse.model_rebuild()
