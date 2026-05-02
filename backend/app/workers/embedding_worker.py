"""Background jobs for creator discovery embedding ingestion."""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from backend.app.ai.llm_client import LLMClient
from backend.app.analytics.audience_quality import calculate_authenticity_score
from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.job_queue import (
    EMBEDDING_INGESTION_JOB_NAME,
    EMBEDDING_INGESTION_QUEUE_NAME,
    enqueue_callable,
)
from backend.app.infra.models import CreatorDiscoveryMeta, CreatorVector, EMBEDDING_DIMENSION
from backend.app.utils.logger import logger


def _zero_embedding() -> list[float]:
    return [0.0] * EMBEDDING_DIMENSION


def _build_source_text(meta: CreatorDiscoveryMeta) -> str:
    category = (meta.creator_dominant_category or "").strip()
    niche_tags = " ".join(str(tag).strip() for tag in (meta.niche_tags or []) if str(tag).strip())
    bio = (meta.bio or "").strip()
    return " ".join(part for part in (category, niche_tags, bio) if part)


def generate_creator_embedding(account_id: str) -> None:
    """Generate and persist a creator embedding, then refresh authenticity score."""
    session_factory = get_sync_sessionmaker()
    try:
        with session_factory() as session:
            meta = session.get(CreatorDiscoveryMeta, account_id)
            if meta is None:
                logger.warning("[EmbeddingWorker] Creator metadata not found for account_id=%s", account_id)
                return

            source_text = _build_source_text(meta)
            embedding = LLMClient().embed(source_text) if source_text else None
            if embedding is None:
                logger.warning("[EmbeddingWorker] Embed returned no vector for account_id=%s; skipping.", account_id)
                return

            vector_row = session.get(CreatorVector, account_id)
            if vector_row is None:
                vector_row = CreatorVector(
                    account_id=account_id,
                    embedding=embedding,
                    source_text=source_text,
                )
                session.add(vector_row)
            else:
                vector_row.embedding = embedding
                vector_row.source_text = source_text

            meta.authenticity_score = calculate_authenticity_score(
                follower_count=int(meta.follower_count or 0),
                avg_views=int(meta.avg_views or 0),
                avg_likes=int(meta.avg_likes or 0),
                avg_comments=int(meta.avg_comments or 0),
            )
            session.commit()
            logger.info("[EmbeddingWorker] Stored embedding for account_id=%s", account_id)
    except SQLAlchemyError as exc:
        logger.warning("[EmbeddingWorker] Database write failed for account_id=%s: %s", account_id, exc)


def upsert_creator(creator_data: dict) -> None:
    """Upsert creator metadata and enqueue embedding generation.

    Only the metadata row is created here.  The vector row with the
    real embedding is created/updated by ``generate_creator_embedding``
    so that zero-vector placeholders never pollute similarity searches.
    """
    account_id = str(creator_data.get("account_id") or "").strip()
    if not account_id:
        logger.warning("[EmbeddingWorker] Skipping creator upsert without account_id.")
        return

    session_factory = get_sync_sessionmaker()
    try:
        with session_factory() as session:
            # Ensure a vector row exists so the FK is satisfied.
            vector_row = session.get(CreatorVector, account_id)
            if vector_row is None:
                vector_row = CreatorVector(
                    account_id=account_id,
                    embedding=creator_data.get("embedding") or _zero_embedding(),
                    source_text=None,
                )
                session.add(vector_row)
                session.flush()  # guarantee FK parent exists before child insert

            meta = session.get(CreatorDiscoveryMeta, account_id)
            if meta is None:
                meta = CreatorDiscoveryMeta(account_id=account_id)
                session.add(meta)

            meta.username = creator_data.get("username")
            meta.follower_count = creator_data.get("follower_count")
            meta.creator_dominant_category = creator_data.get("creator_dominant_category")
            meta.niche_tags = list(creator_data.get("niche_tags") or [])
            meta.bio = creator_data.get("bio")
            meta.authenticity_score = creator_data.get("authenticity_score")
            meta.ahs_score = creator_data.get("ahs_score")
            meta.predicted_engagement_rate = creator_data.get("predicted_engagement_rate")
            meta.avg_visual_quality_score = creator_data.get("avg_visual_quality_score")
            meta.avg_brand_safety_score = creator_data.get("avg_brand_safety_score")
            meta.adult_content_detected = creator_data.get("adult_content_detected")
            meta.avg_views = creator_data.get("avg_views")
            meta.avg_likes = creator_data.get("avg_likes")
            meta.avg_comments = creator_data.get("avg_comments")
            meta.posts_per_week = creator_data.get("posts_per_week")

            session.commit()
    except SQLAlchemyError as exc:
        logger.warning("[EmbeddingWorker] Creator upsert failed for account_id=%s: %s", account_id, exc)
        return

    try:
        enqueue_callable(
            queue_name=EMBEDDING_INGESTION_QUEUE_NAME,
            job_name=EMBEDDING_INGESTION_JOB_NAME,
            func=generate_creator_embedding,
            payload=account_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[EmbeddingWorker] Failed to enqueue embedding job for account_id=%s: %s", account_id, exc)
