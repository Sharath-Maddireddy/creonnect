"""
Instagram OAuth API Router

Provides endpoints for initiating and completing the Instagram OAuth flow.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.ingestion.instagram_oauth import (
    exchange_code_for_token,
    exchange_short_for_long_lived_token,
    fetch_instagram_profile,
    get_oauth_url,
)
from backend.app.infra.token_store import delete_token, get_token, save_token
from backend.app.utils.logger import logger


router = APIRouter(prefix="/api/auth", tags=["Instagram Auth"])


@router.get("/instagram/login")
def instagram_login():
    try:
        return {"oauth_url": get_oauth_url()}
    except RuntimeError as exc:
        logger.exception("Failed to build Instagram OAuth URL")
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/instagram/callback")
async def instagram_callback(code: str, state: str | None = None):
    _ = state
    try:
        short_response = await exchange_code_for_token(code)
        short_token = short_response.get("access_token")
        if not short_token:
            raise RuntimeError("Instagram API error: Missing short-lived access token")

        long_response = await exchange_short_for_long_lived_token(short_token)
        long_token = long_response.get("access_token")
        if not long_token:
            raise RuntimeError("Instagram API error: Missing long-lived access token")

        profile = await fetch_instagram_profile(long_token)
        instagram_user_id = profile.get("id")
        username = profile.get("username")
        if not instagram_user_id or not username:
            raise RuntimeError("Instagram API error: Missing id or username in profile response")

        token_data = {
            "access_token": long_token,
            "expires_in": long_response.get("expires_in"),
            "username": username,
            "instagram_user_id": instagram_user_id,
        }
        save_token(user_id=str(instagram_user_id), token_data=token_data)
        return {"user_id": instagram_user_id, "username": username, "status": "connected"}
    except RuntimeError as exc:
        logger.exception("Instagram OAuth callback failed")
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/me")
async def instagram_me(user_id: str):
    token = get_token(user_id)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    access_token = token.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return await fetch_instagram_profile(access_token)
    except RuntimeError as exc:
        logger.exception("Failed to fetch Instagram profile")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/logout")
def instagram_logout(user_id: str):
    delete_token(user_id)
    return {"status": "logged_out"}
