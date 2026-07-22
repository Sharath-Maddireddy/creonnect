"""
Dev-only login bypass route.

Provides a single endpoint GET /api/dev/login that sets the Instagram session
cookie to a configured test account so that trend & analytics endpoints can be
tested without going through the full Instagram OAuth flow.

WARNING: This router is only registered when ENV != production.
         Never expose this in a production deployment.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.get("/login")
async def dev_login(request: Request) -> JSONResponse:
    """
    Inject a test session so protected endpoints work without OAuth.

    Sets request.session["instagram_user_id"] and ["instagram_username"]
    to the values of TEST_ACCOUNT_ID / TEST_ACCOUNT_USERNAME from .env.

    Returns the account details so the frontend can store user_id in localStorage.
    """
    account_id = (os.getenv("TEST_ACCOUNT_ID") or "").strip()
    username   = (os.getenv("TEST_ACCOUNT_USERNAME") or "test_user").strip()

    if not account_id:
        return JSONResponse(
            status_code=500,
            content={"error": "TEST_ACCOUNT_ID is not set in .env"},
        )

    request.session["instagram_user_id"] = account_id
    request.session["instagram_username"] = username

    return JSONResponse({
        "status":     "logged_in",
        "account_id": account_id,
        "username":   username,
        "message":    "Dev session set. Use this account_id in the Trend Recommendations UI.",
    })


@router.get("/session")
async def dev_session(request: Request) -> JSONResponse:
    """Return the current session state (dev only)."""
    return JSONResponse({
        "instagram_user_id": request.session.get("instagram_user_id"),
        "instagram_username": request.session.get("instagram_username"),
    })


@router.delete("/logout")
async def dev_logout(request: Request) -> JSONResponse:
    """Clear the dev session."""
    request.session.clear()
    return JSONResponse({"status": "logged_out"})
