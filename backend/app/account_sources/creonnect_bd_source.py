"""creonnect-bd-backed account source."""

from __future__ import annotations

from typing import Any

from backend.app.account_sources.base import AccountSource
from backend.app.account_sources.creonnect_bd_client import CreonnectBDClient
from backend.app.account_sources.mappers import build_seed_post_from_creonnect_bd_post, safe_int_or_none
from backend.app.account_sources.models import AccountSourceRequest, AccountSourceType, NormalizedAccountPayload


def _strip_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _select_connection(
    connections: list[dict[str, Any]],
    *,
    connection_id: str | None,
    username: str | None,
) -> dict[str, Any]:
    if connection_id:
        for connection in connections:
            if _strip_text(connection.get("id")) == connection_id:
                return connection
        raise ValueError(f"creonnect-bd connection not found: {connection_id}")

    if username:
        normalized_username = username.lower()
        matches = [
            connection
            for connection in connections
            if _strip_text(connection.get("platformUsername"))
            and str(connection.get("platformUsername")).strip().lower() == normalized_username
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Multiple creonnect-bd connections matched username '{username}'. Provide connection_id.")

    if len(connections) == 1:
        return connections[0]

    if not connections:
        raise ValueError("No active creonnect-bd Instagram connections were returned.")
    raise ValueError("Multiple creonnect-bd connections found. Provide connection_id or username.")


class CreonnectBDAccountSource(AccountSource):
    """Load normalized account payloads from creonnect-bd APIs."""

    async def load(self, request: AccountSourceRequest) -> NormalizedAccountPayload:
        client = CreonnectBDClient(
            base_url=request.bd_base_url,
            timeout_seconds=request.bd_timeout_seconds,
            actor_user_id=request.actor_user_id,
            actor_user_email=request.actor_user_email,
        )
        creator_niche_tags: list[str] = []
        
        creator_payload = await client.get_creator_profile()
        creator = creator_payload.get("creator")
        creator = creator if isinstance(creator, dict) else {}
        niches = creator.get("niches")
        if isinstance(niches, list):
            creator_niche_tags = [
                str(niche).strip()
                for niche in niches
                if isinstance(niche, str) and niche.strip()
            ]
        connections = await client.list_connections(platform="instagram", include_disconnected=False)
        connection = _select_connection(connections, connection_id=request.connection_id, username=request.username)
        resolved_connection_id = _strip_text(connection.get("id"))
        if not resolved_connection_id:
            raise ValueError("creonnect-bd connection payload is missing id")

        platform_user_id = _strip_text(connection.get("platformUserId"))
        platform_username = _strip_text(connection.get("platformUsername"))
        platform_profile = connection.get("platformProfile")
        platform_profile = platform_profile if isinstance(platform_profile, dict) else {}
        account_id = request.account_id or platform_user_id or platform_username or resolved_connection_id
        if not account_id:
            raise ValueError("Unable to derive account_id from creonnect-bd connection payload.")

        follower_count = request.follower_count
        if follower_count is None:
            follower_count = safe_int_or_none(platform_profile.get("followers_count"))
        if follower_count is None:
            metrics = connection.get("metrics")
            metrics = metrics if isinstance(metrics, dict) else {}
            follower_count = safe_int_or_none(metrics.get("followers_count"))

        posts: list[dict[str, Any]] = []
        page = 1
        page_size = min(100, request.post_limit)
        while len(posts) < request.post_limit:
            page_payload = await client.list_posts_page(
                platform="instagram",
                connection_id=resolved_connection_id,
                page=page,
                limit=page_size,
            )
            page_posts = page_payload.get("posts")
            page_posts = page_posts if isinstance(page_posts, list) else []
            posts.extend(item for item in page_posts if isinstance(item, dict))

            pagination = page_payload.get("pagination")
            pagination = pagination if isinstance(pagination, dict) else {}
            if not pagination.get("hasNext"):
                break
            page += 1

        normalized_posts = [
            build_seed_post_from_creonnect_bd_post(
                post_payload,
                account_id=account_id,
                follower_count=follower_count,
                creator_dominant_category=request.creator_dominant_category,
            )
            for post_payload in posts[: request.post_limit]
        ]

        return NormalizedAccountPayload(
            source_type=AccountSourceType.CREONNECT_BD,
            source_ref=resolved_connection_id,
            source_meta={
                "connection_id": resolved_connection_id,
                "platform": "instagram",
                "platform_user_id": platform_user_id,
                "platform_username": platform_username,
            },
            account_id=account_id,
            username=request.username or platform_username,
            bio=request.bio or _strip_text(platform_profile.get("biography")) or _strip_text(platform_profile.get("bio")),
            follower_count=follower_count,
            creator_dominant_category=request.creator_dominant_category,
            niche_tags=list(request.niche_tags or creator_niche_tags),
            posts=normalized_posts,
        )
