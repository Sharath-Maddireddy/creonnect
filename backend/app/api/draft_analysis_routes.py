"""API routes for pre-post draft optimization."""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.app.analytics.draft_optimizer_engine import optimize_draft_post
from backend.app.api.auth import verify_api_key
from backend.app.domain.draft_models import DraftPostAnalysisRequest, DraftPostOptimizationResponse
from backend.app.services.draft_history_service import load_draft_history_context
from backend.app.utils.logger import logger


router = APIRouter(prefix="/api/v1", tags=["Draft Optimization"])


def _require_draft_api_key_if_configured(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str | None:
    env = (os.getenv("ENV") or "").strip().lower()
    if env != "production":
        return None

    expected_api_key = (os.getenv("BRAND_API_KEY") or "").strip()
    if not expected_api_key:
        return None
    return verify_api_key(x_api_key)


@router.post(
    "/draft-optimize",
    response_model=DraftPostOptimizationResponse,
    dependencies=[Depends(_require_draft_api_key_if_configured)],
)
async def draft_optimize(request: DraftPostAnalysisRequest) -> DraftPostOptimizationResponse:
    """Optimize a draft caption and optional media using historical account performance."""
    try:
        history_context = await asyncio.to_thread(load_draft_history_context, request.account_id)
    except Exception as exc:
        logger.exception("[DraftOptimize] Failed loading history for account_id=%s", request.account_id)
        raise HTTPException(status_code=500, detail="Failed to load historical post context.") from exc

    if not history_context.historical_posts:
        raise HTTPException(
            status_code=404,
            detail=(
                "No historical posts found for this account_id. "
                "Run account analysis first so the optimizer has performance context."
            ),
        )

    try:
        response = await optimize_draft_post(
            draft_caption=request.draft_caption,
            post_type=request.post_type,
            media_url=request.media_url,
            account_data={
                **history_context.account_data,
                "account_id": request.account_id,
            },
            historical_posts=history_context.historical_posts,
        )
        return response
    except Exception as exc:
        logger.exception("[DraftOptimize] Failed optimization for account_id=%s", request.account_id)
        raise HTTPException(status_code=500, detail="Failed to optimize draft post.") from exc
