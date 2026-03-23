"""Simple API key authentication dependencies."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    """Validate the incoming static API key."""
    expected_api_key = os.getenv("BRAND_API_KEY")
    if not x_api_key or not expected_api_key or x_api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return x_api_key
