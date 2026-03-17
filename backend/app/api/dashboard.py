"""
Dashboard API Router

Exposes creator metrics in a frontend-friendly format for charts and graphs.
All computations are done server-side - frontend only plots.
"""

from fastapi import APIRouter, HTTPException
from backend.app.services.dashboard_service import build_creator_dashboard
from backend.app.services.snapshot_service import build_creator_snapshot_service
from backend.app.services.script_service import generate_creator_script_service
from backend.app.infra.token_store import get_token


router = APIRouter(prefix="/api", tags=["Dashboard"])


@router.get("/creator/dashboard")
def creator_dashboard(user_id: str | None = None):
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
            return build_creator_dashboard("demo", access_token=token["access_token"])
        return build_creator_dashboard("demo")
    except ValueError:
        raise HTTPException(status_code=404, detail="Creator not found")


@router.get("/creators/{creator_id}/snapshot")
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


@router.post("/creators/{creator_id}/generate-script")
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



