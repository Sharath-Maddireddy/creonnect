"""
Dashboard API Router

Exposes creator metrics in a frontend-friendly format for charts and graphs.
All computations are done server-side - frontend only plots.
"""

import os

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.app.api.auth import verify_api_key
from backend.app.infra.token_store import get_token
from backend.app.services.dashboard_service import build_creator_analytics_async, build_creator_dashboard_async
from backend.app.services.script_service import generate_creator_script_service
from backend.app.services.snapshot_service import build_creator_snapshot_service


router = APIRouter(prefix="/api", tags=["Dashboard"])


def _require_dashboard_api_key_if_configured(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str | None:
    env = (os.getenv("ENV") or "").strip().lower()
    if env != "production":
        return None

    expected_api_key = (os.getenv("BRAND_API_KEY") or "").strip()
    if not expected_api_key:
        return None
    return verify_api_key(x_api_key)


@router.get("/creator/dashboard", dependencies=[Depends(_require_dashboard_api_key_if_configured)])
async def creator_dashboard(user_id: str | None = None):
    """
    Get complete creator dashboard data including:
    - Summary metrics
    - Post insights
    - Time-series data for charts
    Notes:
    - When user_id is provided, real Instagram data is fetched via OAuth.
    - When user_id is omitted, demo mode is used.
    """
    try:
        if user_id:
            token = get_token(user_id)
            if not token or not token.get("access_token"):
                raise HTTPException(status_code=401, detail="Not authenticated")
            return await build_creator_dashboard_async("demo", access_token=token["access_token"])
        return await build_creator_dashboard_async("demo")
    except ValueError:
        raise HTTPException(status_code=404, detail="Creator not found")


@router.get("/creator/analytics", dependencies=[Depends(_require_dashboard_api_key_if_configured)])
async def creator_analytics(user_id: str | None = None):
    """
    Get enriched creator analytics including dashboard, account health,
    and content-type breakdown.
    Notes:
    - When user_id is provided, real Instagram data is fetched via OAuth.
    - When user_id is omitted, demo mode is used.
    """
    try:
        if user_id:
            token = get_token(user_id)
            if not token or not token.get("access_token"):
                raise HTTPException(status_code=401, detail="Not authenticated")
            return await build_creator_analytics_async("demo", access_token=token["access_token"])
        return await build_creator_analytics_async("demo")
    except ValueError:
        raise HTTPException(status_code=404, detail="Creator not found")


@router.get("/creators/{creator_id}/snapshot", dependencies=[Depends(_require_dashboard_api_key_if_configured)])
def get_creator_snapshot(creator_id: str):
    """
    Get daily snapshot for a creator.

    Returns current metrics snapshot including:
    - Follower count
    - Engagement metrics
    - Growth score
    """
    try:
        return build_creator_snapshot_service(creator_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Creator '{creator_id}' not found")


@router.post("/creators/{creator_id}/generate-script", dependencies=[Depends(_require_dashboard_api_key_if_configured)])
def generate_script(creator_id: str):
    """
    Generate a reel script for a creator.

    Returns:
        Script dict with hook, body, cta tailored to creator's niche
    """
    try:
        return generate_creator_script_service(creator_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Creator '{creator_id}' not found")

