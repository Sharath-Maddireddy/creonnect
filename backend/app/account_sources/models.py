"""Shared models for account-source loading."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain.post_models import SinglePostInsights


class AccountSourceType(str, Enum):
    """Supported upstream account sources."""

    FIXTURE = "fixture"
    CREONNECT_BD = "creonnect_bd"
    PRECOMPUTED = "precomputed"


class AccountSourceRequest(BaseModel):
    """Normalized request for source materialization."""

    model_config = ConfigDict(extra="ignore")

    source: AccountSourceType
    account_id: str | None = None
    username: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    creator_dominant_category: str | None = None
    niche_tags: list[str] | None = None
    post_limit: int = Field(default=30, ge=1, le=30)
    fixture_path: str | None = None
    connection_id: str | None = None
    bd_base_url: str | None = None
    bd_timeout_seconds: float | None = None
    actor_user_id: str | None = None
    actor_user_email: str | None = None

    @field_validator(
        "account_id",
        "username",
        "bio",
        "fixture_path",
        "connection_id",
        "bd_base_url",
        "actor_user_id",
        "actor_user_email",
    )
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class NormalizedAccountPayload(BaseModel):
    """Canonical payload shape returned by every source loader."""

    model_config = ConfigDict(extra="forbid")

    source_type: AccountSourceType
    source_ref: str | None = None
    source_meta: dict[str, Any] = Field(default_factory=dict)
    account_id: str
    username: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    creator_dominant_category: str | None = None
    niche_tags: list[str] = Field(default_factory=list)
    posts: list[SinglePostInsights] = Field(default_factory=list)
