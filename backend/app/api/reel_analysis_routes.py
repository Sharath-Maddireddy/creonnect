"""API routes for reel analysis background jobs."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from backend.app.api.auth import verify_api_key
from backend.app.services.reel_analysis_jobs import (
    enqueue_reel_analysis_job,
    get_reel_job_status,
)


router = APIRouter(prefix="/api/reel-analysis", tags=["Reel Analysis"])


def _require_reel_analysis_api_key_if_configured(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str | None:
    env = (os.getenv("ENV") or "").strip().lower()
    if env != "production":
        return None

    expected_api_key = (os.getenv("BRAND_API_KEY") or "").strip()
    if not expected_api_key:
        return None
    return verify_api_key(x_api_key)


class ReelEnqueueRequest(BaseModel):
    """Request payload for reel-analysis enqueue endpoint."""

    model_config = ConfigDict(extra="forbid")

    media_url: str
    audio_name: str | None = None
    caption_text: str = ""
    watch_time_pct: float | None = None

    @field_validator("media_url", mode="before")
    @classmethod
    def _validate_url(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("media_url must be non-empty.")
        return value.strip()


@router.post("/enqueue", dependencies=[Depends(_require_reel_analysis_api_key_if_configured)])
def enqueue_reel_analysis(request: ReelEnqueueRequest) -> dict[str, Any]:
    """Enqueue reel analysis and return the job id."""
    try:
        return enqueue_reel_analysis_job(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue: {exc}")


@router.get("/jobs/{job_id}", dependencies=[Depends(_require_reel_analysis_api_key_if_configured)])
def get_reel_job(job_id: str) -> dict[str, Any]:
    """Return reel-analysis job status payload."""
    normalized_job_id = job_id.strip()
    if not normalized_job_id:
        raise HTTPException(status_code=400, detail="job_id must be non-empty.")
    payload = get_reel_job_status(normalized_job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return payload
