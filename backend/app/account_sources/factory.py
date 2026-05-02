"""Factory helpers for shared account-source loading."""

from __future__ import annotations

from typing import Any

from backend.app.account_sources.base import AccountSource
from backend.app.account_sources.creonnect_bd_source import CreonnectBDAccountSource
from backend.app.account_sources.fixture_source import FixtureAccountSource
from backend.app.account_sources.models import AccountSourceRequest, AccountSourceType


def _coerce_source_type(value: Any) -> AccountSourceType | None:
    if isinstance(value, AccountSourceType):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    for source_type in AccountSourceType:
        if source_type.value == normalized:
            return source_type
    raise ValueError(f"Unsupported account source '{value}'.")


def resolve_account_source_type(payload: dict[str, Any]) -> AccountSourceType | None:
    """Infer the source type from a request payload."""
    explicit = _coerce_source_type(payload.get("source"))
    if explicit is not None:
        return explicit
    if isinstance(payload.get("posts"), list):
        return AccountSourceType.PRECOMPUTED
    if payload.get("fixture_path"):
        return AccountSourceType.FIXTURE
    if payload.get("connection_id") or payload.get("bd_base_url"):
        return AccountSourceType.CREONNECT_BD
    return None


def get_account_source(source_type: AccountSourceType) -> AccountSource:
    """Return the concrete source loader for a source type."""
    if source_type == AccountSourceType.FIXTURE:
        return FixtureAccountSource()
    if source_type == AccountSourceType.CREONNECT_BD:
        return CreonnectBDAccountSource()
    raise ValueError(f"Unsupported account source '{source_type.value}'.")


async def materialize_account_source_payload(payload: dict[str, Any], *, post_limit: int) -> dict[str, Any]:
    """Load one normalized payload from the shared source layer."""
    source_type = resolve_account_source_type(payload)
    sanitized_payload = dict(payload)
    sanitized_payload.pop("access_token", None)

    if source_type in {None, AccountSourceType.PRECOMPUTED}:
        return sanitized_payload

    request = AccountSourceRequest.model_validate(
        {
            **payload,
            "post_limit": post_limit,
            "source": source_type.value,
        }
    )
    source_loader = get_account_source(source_type)
    normalized = await source_loader.load(request)

    sanitized_payload["source"] = normalized.source_type.value
    sanitized_payload["source_ref"] = normalized.source_ref
    sanitized_payload["source_meta"] = normalized.source_meta
    sanitized_payload["account_id"] = normalized.account_id
    sanitized_payload["username"] = normalized.username
    sanitized_payload["bio"] = normalized.bio
    sanitized_payload["follower_count"] = normalized.follower_count
    if normalized.creator_dominant_category and not sanitized_payload.get("creator_dominant_category"):
        sanitized_payload["creator_dominant_category"] = normalized.creator_dominant_category
    if normalized.niche_tags and not sanitized_payload.get("niche_tags"):
        sanitized_payload["niche_tags"] = list(normalized.niche_tags)
    sanitized_payload["posts"] = [post.model_dump(mode="python") for post in normalized.posts[:post_limit]]
    return sanitized_payload
