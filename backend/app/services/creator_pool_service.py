"""Database-backed service for managing and querying the creator pool."""

from __future__ import annotations

import os

from sqlalchemy import Select, select, text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import CreatorDiscoveryMeta, CreatorVector
from backend.app.utils.logger import logger
from backend.app.utils.vector_math import cosine_similarity


class LookalikeEmbeddingError(RuntimeError):
    """Raised when lookalike search cannot compute required embeddings."""


def _get_hnsw_ef_search() -> int:
    raw_value = (os.getenv("PGVECTOR_HNSW_EF_SEARCH") or "").strip()
    if not raw_value:
        return 100
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid PGVECTOR_HNSW_EF_SEARCH=%r; falling back to 100", raw_value)
        return 100


def _normalize_embedding(value: object) -> list[float] | None:
    if value is None:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _creator_to_dict(meta: CreatorDiscoveryMeta, vector: CreatorVector | None) -> dict:
    return {
        "account_id": meta.account_id,
        "username": meta.username,
        "creator_dominant_category": meta.creator_dominant_category,
        "follower_count": meta.follower_count,
        "ahs_score": meta.ahs_score,
        "predicted_engagement_rate": meta.predicted_engagement_rate,
        "avg_visual_quality_score": meta.avg_visual_quality_score,
        "avg_brand_safety_score": meta.avg_brand_safety_score,
        "adult_content_detected": meta.adult_content_detected,
        "bio": meta.bio,
        "avg_views": meta.avg_views,
        "avg_likes": meta.avg_likes,
        "avg_comments": meta.avg_comments,
        "posts_per_week": meta.posts_per_week,
        "niche_tags": meta.niche_tags or [],
        "embedding": _normalize_embedding(vector.embedding) if vector is not None else None,
    }


def _base_creator_query() -> Select:
    return select(CreatorDiscoveryMeta, CreatorVector).join(
        CreatorVector,
        CreatorVector.account_id == CreatorDiscoveryMeta.account_id,
        isouter=True,
    )


def _run_creator_query(statement: Select) -> list[dict]:
    session_factory = get_sync_sessionmaker()
    try:
        with session_factory() as session:
            rows = session.execute(statement).all()
            return [_creator_to_dict(meta, vector) for meta, vector in rows]
    except SQLAlchemyError as exc:
        logger.warning("[CreatorPoolService] Database query failed: %s", exc)
        return []


def reload_creator_pool() -> None:
    """No-op retained for backward compatibility."""
    logger.info("[CreatorPoolService] reload_creator_pool() called; no cache is maintained.")


def get_all_creators() -> list[dict]:
    """Return every creator from the discovery tables."""
    statement = _base_creator_query().order_by(CreatorDiscoveryMeta.username.asc())
    return _run_creator_query(statement)


def query_creator_pool(
    niche: str | None = None,
    min_followers: int | None = None,
    max_followers: int | None = None,
    *,
    limit: int | None = None,
) -> list[dict]:
    """Filter creators via database queries while preserving the legacy return shape."""
    statement = _base_creator_query()

    if niche:
        escaped_niche = niche.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        niche_pattern = f"%{escaped_niche.strip()}%"
        statement = statement.where(
            CreatorDiscoveryMeta.creator_dominant_category.ilike(niche_pattern, escape="\\")
        )
    if min_followers is not None:
        statement = statement.where(CreatorDiscoveryMeta.follower_count >= int(min_followers))
    if max_followers is not None:
        statement = statement.where(CreatorDiscoveryMeta.follower_count <= int(max_followers))

    statement = statement.order_by(CreatorDiscoveryMeta.follower_count.desc())
    if isinstance(limit, int) and limit > 0:
        statement = statement.limit(int(limit))
    return _run_creator_query(statement)


def _get_creators_by_ids(account_ids: list[str]) -> list[dict]:
    if not account_ids:
        return []

    statement = _base_creator_query().where(CreatorDiscoveryMeta.account_id.in_(account_ids))
    creators = _run_creator_query(statement)
    creator_by_id = {creator["account_id"]: creator for creator in creators}
    return [creator_by_id[account_id] for account_id in account_ids if account_id in creator_by_id]


def _get_vector_embeddings_by_account_id() -> dict[str, list[float]]:
    session_factory = get_sync_sessionmaker()
    try:
        with session_factory() as session:
            rows = session.execute(select(CreatorVector.account_id, CreatorVector.embedding)).all()
    except SQLAlchemyError as exc:
        logger.warning("[CreatorPoolService] Failed to load embeddings for sqlite fallback: %s", exc)
        return {}

    normalized: dict[str, list[float]] = {}
    for account_id, raw_embedding in rows:
        embedding = _normalize_embedding(raw_embedding)
        if account_id and embedding:
            normalized[str(account_id)] = embedding
    return normalized


def _find_lookalikes_sqlite_fallback(account_id: str, k: int) -> list[dict] | None:
    embeddings = _get_vector_embeddings_by_account_id()
    target_embedding = embeddings.get(account_id)
    if target_embedding is None:
        return None

    scored_matches: list[tuple[float, str]] = []
    for other_account_id, other_embedding in embeddings.items():
        if other_account_id == account_id:
            continue
        distance = 1.0 - cosine_similarity(target_embedding, other_embedding)
        scored_matches.append((distance, other_account_id))

    scored_matches.sort(key=lambda item: item[0])
    return _get_creators_by_ids([candidate_id for _, candidate_id in scored_matches[:k]])


def find_lookalikes(account_id: str, k: int = 3) -> list[dict] | None:
    """Return top-k vector-nearest creators, or None when the target creator does not exist."""
    session_factory = get_sync_sessionmaker()
    try:
        with session_factory() as session:
            target_exists = session.scalar(
                select(CreatorVector.account_id).where(CreatorVector.account_id == account_id)
            )
            if target_exists is None:
                return None

            if session.bind is None or session.bind.dialect.name != "postgresql":
                return _find_lookalikes_sqlite_fallback(account_id, k)

            target_embedding = session.scalar(
                select(CreatorVector.embedding).where(CreatorVector.account_id == account_id)
            )
            if _normalize_embedding(target_embedding) is None:
                raise LookalikeEmbeddingError(f"Missing embedding for creator '{account_id}'.")

            ef_search = int(_get_hnsw_ef_search())
            session.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))

            result = session.execute(
                text(
                    """
                    SELECT account_id,
                           embedding <=> (
                               SELECT embedding
                               FROM creator_vectors
                               WHERE account_id = :target_id
                           ) AS distance
                    FROM creator_vectors
                    WHERE account_id != :target_id
                    ORDER BY distance ASC
                    LIMIT :limit_value
                    """
                ),
                {"target_id": account_id, "limit_value": int(k)},
            )
            ordered_ids = [row.account_id for row in result]
    except SQLAlchemyError as exc:
        logger.warning("[CreatorPoolService] Lookalike search failed: %s", exc)
        return []

    return _get_creators_by_ids(ordered_ids)
