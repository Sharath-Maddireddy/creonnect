"""SQLAlchemy models for creator discovery."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - exercised when dependency is absent locally
    Vector = None


EMBEDDING_DIMENSION = 1536


class Base(DeclarativeBase):
    """Base declarative model."""


class EmbeddingType(TypeDecorator):
    """Use pgvector on PostgreSQL and JSON elsewhere."""

    cache_ok = True

    impl = JSON

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and Vector is not None:
            return dialect.type_descriptor(Vector(EMBEDDING_DIMENSION))
        return dialect.type_descriptor(JSON())


class JsonListType(TypeDecorator):
    """Use JSONB on PostgreSQL and JSON elsewhere."""

    cache_ok = True

    impl = JSON

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return []
        return value

    def process_result_value(self, value: Any, dialect) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
                return decoded if isinstance(decoded, list) else []
            except json.JSONDecodeError:
                return []
        return value if isinstance(value, list) else []


class CreatorVector(Base):
    """Stores creator embeddings for similarity search."""

    __tablename__ = "creator_vectors"
    __table_args__ = (
        Index(
            "ix_creator_vectors_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingType(), nullable=False)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CreatorDiscoveryMeta(Base):
    """Stores creator discovery metadata used for filtering and ranking."""

    __tablename__ = "creator_discovery_meta"
    __table_args__ = (
        Index("ix_creator_discovery_meta_category", "creator_dominant_category"),
        Index("ix_creator_discovery_meta_followers", "follower_count"),
    )

    account_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("creator_vectors.account_id"),
        primary_key=True,
    )
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    follower_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creator_dominant_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    niche_tags: Mapped[list[str]] = mapped_column(JsonListType(), nullable=False, default=list)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    authenticity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ahs_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_engagement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_visual_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_brand_safety_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    adult_content_detected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    avg_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posts_per_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
