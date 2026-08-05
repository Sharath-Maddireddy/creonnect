import asyncio
import os
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.app.utils.logger import logger


FACEBOOK_OAUTH_URL = "https://www.facebook.com/dialog/oauth"
GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
HTTP_TIMEOUT_SECONDS = 30.0
_BASE_MEDIA_INSIGHT_METRICS = ("reach", "impressions", "saved", "shares", "profile_visits")
_REEL_INSIGHT_METRICS = (
    "plays",
    "views",
    "ig_reels_avg_watch_time",
    "ig_reels_video_view_total_time",
    "clips_replays_count",
    "reels_skip_rate",
)


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
                media = media[:limit]
                break

            after = (
                payload.get("paging", {})
                .get("cursors", {})
                .get("after")
            )
            if not after:
                break

    media = await enrich_instagram_media_with_insights(access_token, media)
    logger.info("Fetched %s Instagram media items", len(media))
    return media


def _insight_value(metric: dict[str, Any]) -> Any:
    values = metric.get("values")
    if not isinstance(values, list) or not values:
        return None
    latest = values[-1]
    return latest.get("value") if isinstance(latest, dict) else None


async def _fetch_media_insight_group(
    client: httpx.AsyncClient,
    *,
    media_id: str,
    access_token: str,
    metrics: tuple[str, ...],
) -> dict[str, Any]:
    """Fetch a compatible metric group, splitting it when Meta rejects one metric."""
    if not metrics:
        return {}
    response = await client.get(
        f"{GRAPH_API_BASE}/{media_id}/insights",
        params={"metric": ",".join(metrics), "access_token": access_token},
    )
    payload = response.json()
    if response.status_code == 200 and not payload.get("error"):
        data = payload.get("data")
        if not isinstance(data, list):
            return {}
        return {
            str(item.get("name")): _insight_value(item)
            for item in data
            if isinstance(item, dict) and item.get("name") and _insight_value(item) is not None
        }
    if len(metrics) == 1:
        logger.info("Instagram insight unavailable media_id=%s metric=%s", media_id, metrics[0])
        return {}
    midpoint = len(metrics) // 2
    left, right = await asyncio.gather(
        _fetch_media_insight_group(client, media_id=media_id, access_token=access_token, metrics=metrics[:midpoint]),
        _fetch_media_insight_group(client, media_id=media_id, access_token=access_token, metrics=metrics[midpoint:]),
    )
    return {**left, **right}


async def enrich_instagram_media_with_insights(access_token: str, media: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach permitted media insights without failing the base media response."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        async def enrich(item: dict[str, Any]) -> dict[str, Any]:
            media_id = item.get("id")
            if not isinstance(media_id, str) or not media_id:
                return item
            metrics = _BASE_MEDIA_INSIGHT_METRICS
            media_type = str(item.get("media_type") or "").upper()
            if media_type in {"REEL", "VIDEO"}:
                metrics += _REEL_INSIGHT_METRICS
            try:
                insights = await _fetch_media_insight_group(
                    client,
                    media_id=media_id,
                    access_token=access_token,
                    metrics=metrics,
                )
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                logger.info("Instagram insights unavailable media_id=%s: %s", media_id, exc)
                return item
            if not insights:
                return item
            enriched = dict(item)
            enriched["insights"] = insights
            enriched["reach"] = insights.get("reach")
            enriched["impressions"] = insights.get("impressions")
            enriched["saves"] = insights.get("saved")
            enriched["shares"] = insights.get("shares")
            enriched["profile_visits"] = insights.get("profile_visits")
            enriched["views"] = insights.get("views") or insights.get("plays")
            enriched["avg_watch_time"] = insights.get("ig_reels_avg_watch_time")
            enriched["replays"] = insights.get("clips_replays_count")
            enriched["skip_rate"] = insights.get("reels_skip_rate")
            return enriched

        return list(await asyncio.gather(*(enrich(item) for item in media)))
