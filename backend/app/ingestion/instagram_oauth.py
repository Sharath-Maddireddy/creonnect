import os
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.app.utils.logger import logger


FACEBOOK_OAUTH_URL = "https://www.facebook.com/dialog/oauth"
GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
HTTP_TIMEOUT_SECONDS = 30.0


INSTAGRAM_APP_ID = os.getenv("INSTAGRAM_APP_ID")
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET")
INSTAGRAM_REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI")


def _require_env(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _raise_for_api_error(status_code: int, payload: dict[str, Any] | None) -> None:
    if status_code != 200:
        raise RuntimeError(f"Instagram API error: HTTP {status_code}")
    if payload and isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"Instagram API error: {payload['error']}")


def get_oauth_url(state: str) -> str:
    client_id = _require_env("INSTAGRAM_APP_ID", INSTAGRAM_APP_ID)
    redirect_uri = _require_env("INSTAGRAM_REDIRECT_URI", INSTAGRAM_REDIRECT_URI)

    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "instagram_basic,instagram_manage_insights",
            "response_type": "code",
            "state": state,
        }
    )
    return f"{FACEBOOK_OAUTH_URL}?{query}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    client_id = _require_env("INSTAGRAM_APP_ID", INSTAGRAM_APP_ID)
    client_secret = _require_env("INSTAGRAM_APP_SECRET", INSTAGRAM_APP_SECRET)
    redirect_uri = _require_env("INSTAGRAM_REDIRECT_URI", INSTAGRAM_REDIRECT_URI)

    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{GRAPH_API_BASE}/oauth/access_token", data=params)
    payload = response.json()
    _raise_for_api_error(response.status_code, payload)
    return payload


async def exchange_short_for_long_lived_token(short_token: str) -> dict[str, Any]:
    client_id = _require_env("INSTAGRAM_APP_ID", INSTAGRAM_APP_ID)
    client_secret = _require_env("INSTAGRAM_APP_SECRET", INSTAGRAM_APP_SECRET)

    params = {
        "grant_type": "fb_exchange_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "fb_exchange_token": short_token,
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{GRAPH_API_BASE}/oauth/access_token", params=params)
    payload = response.json()
    _raise_for_api_error(response.status_code, payload)
    return payload


async def fetch_instagram_profile(access_token: str) -> dict[str, Any]:
    params = {
        "fields": "id,username,biography,followers_count,follows_count,media_count",
        "access_token": access_token,
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{GRAPH_API_BASE}/me", params=params)
    payload = response.json()
    _raise_for_api_error(response.status_code, payload)
    return payload


async def fetch_instagram_media(access_token: str, limit: int = 30) -> list[dict[str, Any]]:
    params = {
        "fields": (
            "id,media_type,caption,like_count,comments_count,"
            "timestamp,media_url,thumbnail_url,permalink"
        ),
        "limit": limit,
        "access_token": access_token,
    }

    media: list[dict[str, Any]] = []
    after: str | None = None

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        while True:
            if after:
                params["after"] = after
            response = await client.get(f"{GRAPH_API_BASE}/me/media", params=params)
            payload = response.json()
            _raise_for_api_error(response.status_code, payload)

            batch = payload.get("data", [])
            if not isinstance(batch, list):
                raise RuntimeError("Instagram API error: Unexpected media response format")
            media.extend(batch)

            if len(media) >= limit:
                return media[:limit]

            after = (
                payload.get("paging", {})
                .get("cursors", {})
                .get("after")
            )
            if not after:
                break

    logger.info("Fetched %s Instagram media items", len(media))
    return media
