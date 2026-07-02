"""SQLAlchemy models for creator discovery.

The creator-pool vectors stored here are OpenAI embeddings used for pgvector-
backed similarity search. They intentionally live in a different vector space
from the in-memory RAG engine in ``backend.app.ai.rag``, which uses a local
sentence-transformer model for document retrieval.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

from backend.app.utils.env_numbers import get_int_env

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - exercised when dependency is absent locally
    Vector = None



CREATOR_EMBEDDING_MODEL_NAME = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
HNSW_M = get_int_env("PGVECTOR_HNSW_M", 32)
HNSW_EF_CONSTRUCTION = get_int_env("PGVECTOR_HNSW_EF_CONSTRUCTION", 128)


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
    """Stores creator embeddings for creator-pool similarity search.

    These vectors use ``text-embedding-3-small`` and are not interchangeable
    with the 384-d sentence-transformer embeddings used by the RAG engine.
    """

    __tablename__ = "creator_vectors"
    __table_args__ = (
        Index(
            "ix_creator_vectors_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": HNSW_M, "ef_construction": HNSW_EF_CONSTRUCTION},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_creator_vectors_updated_at", "updated_at"),
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
        Index("ix_creator_discovery_meta_updated_at", "updated_at"),
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


class AccountAnalysisResult(Base):
    """Durably stores account-analysis job outputs."""

    __tablename__ = "account_analysis_results"
    __table_args__ = (
        Index("ix_account_analysis_results_account_id", "account_id"),
        Index("ix_account_analysis_results_status", "status"),
        Index("ix_account_analysis_results_updated_at", "updated_at"),
        Index("ix_account_analysis_results_source_type", "source_type"),
    )

    job_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    request_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    quality_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BackgroundJob(Base):
    """Stores cross-queue job state independently of the transport backend."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        Index("ix_background_jobs_queue_name", "queue_name"),
        Index("ix_background_jobs_status", "status"),
        Index("ix_background_jobs_account_id", "account_id"),
        Index("ix_background_jobs_created_at", "created_at"),
        Index("ix_background_jobs_payload_hash", "payload_hash"),
    )

    job_id: Mapped[str] = mapped_column(Text, primary_key=True)
    queue_name: Mapped[str] = mapped_column(Text, nullable=False)
    job_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    quality_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CreatorTrendResult(Base):
    """Stores the latest trend analysis result per account."""

    __tablename__ = "creator_trend_results"
    __table_args__ = (
        Index("ix_creator_trend_results_updated_at", "updated_at"),
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    niche_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    global_trends_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    recommendations_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

