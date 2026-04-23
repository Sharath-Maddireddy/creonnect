"""Tests for the database-backed creator pool service."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.analytics.audience_quality import calculate_authenticity_score
from backend.app.infra.database import get_sync_db, get_sync_engine, get_sync_sessionmaker, reset_database_engines
from backend.app.infra.models import Base, CreatorDiscoveryMeta, CreatorVector, EMBEDDING_DIMENSION
from backend.app.services.creator_pool_service import find_lookalikes, get_all_creators, query_creator_pool
from backend.app.workers import embedding_worker


class _DummyQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[object, tuple, dict]] = []

    def enqueue(self, func, *args, **kwargs):  # noqa: ANN001
        self.calls.append((func, args, kwargs))


def _creator(
    account_id: str,
    username: str,
    category: str,
    followers: int,
) -> dict:
    return {
        "account_id": account_id,
        "username": username,
        "creator_dominant_category": category,
        "follower_count": followers,
        "ahs_score": 80.0,
        "predicted_engagement_rate": 0.04,
        "avg_visual_quality_score": 42.0,
        "avg_brand_safety_score": 46.0,
        "adult_content_detected": False,
        "bio": f"{username} bio",
        "avg_views": 10000,
        "avg_likes": 900,
        "avg_comments": 120,
        "posts_per_week": 3.5,
        "niche_tags": [category, "creator"],
    }


def _embedding(*values: float) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    for index, value in enumerate(values):
        vector[index] = value
    return vector


@pytest.fixture
def db_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _DummyQueue:
    db_path = tmp_path / "creator_pool.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    reset_database_engines()
    Base.metadata.create_all(bind=get_sync_engine())

    queue = _DummyQueue()
    monkeypatch.setattr(embedding_worker, "get_queue", lambda name="embedding-ingestion": queue)

    yield queue

    reset_database_engines()


def test_upsert_creator_inserts_creator_into_database(db_setup: _DummyQueue) -> None:
    creator = _creator("creator_1", "fit_one", "fitness", 125000)

    embedding_worker.upsert_creator(creator)

    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        meta = session.get(CreatorDiscoveryMeta, "creator_1")
        vector = session.get(CreatorVector, "creator_1")

    assert meta is not None
    assert meta.username == "fit_one"
    assert meta.creator_dominant_category == "fitness"
    assert vector is not None
    assert len(vector.embedding) == EMBEDDING_DIMENSION
    assert db_setup.calls[0][0] is embedding_worker.generate_creator_embedding


def test_generate_creator_embedding_stores_embedding(monkeypatch: pytest.MonkeyPatch, db_setup: _DummyQueue) -> None:
    creator = _creator("creator_2", "fit_two", "fitness", 250000)
    embedding_worker.upsert_creator(creator)
    mocked_embedding = _embedding(0.25, 0.75, 0.5)

    monkeypatch.setattr(embedding_worker.LLMClient, "embed", lambda self, text: mocked_embedding)

    embedding_worker.generate_creator_embedding("creator_2")

    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        meta = session.get(CreatorDiscoveryMeta, "creator_2")
        vector = session.get(CreatorVector, "creator_2")

    assert meta is not None
    assert vector is not None
    assert vector.embedding == mocked_embedding
    assert vector.source_text == "fitness fitness creator fit_two bio"
    assert meta.authenticity_score == calculate_authenticity_score(
        follower_count=250000,
        avg_views=10000,
        avg_likes=900,
        avg_comments=120,
    )


def test_query_creator_pool_filters_by_niche(db_setup: _DummyQueue) -> None:
    embedding_worker.upsert_creator(_creator("fitness_1", "fit_a", "fitness", 120000))
    embedding_worker.upsert_creator(_creator("fitness_2", "fit_b", "fitness", 220000))
    embedding_worker.upsert_creator(_creator("tech_1", "tech_a", "tech", 180000))

    creators = query_creator_pool(niche="fitness")

    assert {creator["account_id"] for creator in creators} == {"fitness_1", "fitness_2"}


def test_query_creator_pool_filters_by_min_followers(db_setup: _DummyQueue) -> None:
    embedding_worker.upsert_creator(_creator("micro_1", "micro", "fitness", 50000))
    embedding_worker.upsert_creator(_creator("macro_1", "macro", "fitness", 150000))

    creators = query_creator_pool(min_followers=100000)

    assert [creator["account_id"] for creator in creators] == ["macro_1"]


def test_find_lookalikes_returns_top_k_similar_creators(db_setup: _DummyQueue) -> None:
    embedding_worker.upsert_creator(_creator("target", "target_user", "fitness", 200000))
    embedding_worker.upsert_creator(_creator("close", "close_user", "fitness", 190000))
    embedding_worker.upsert_creator(_creator("mid", "mid_user", "fitness", 180000))
    embedding_worker.upsert_creator(_creator("far", "far_user", "tech", 170000))

    session_factory = get_sync_sessionmaker()
    with session_factory() as session:
        session.get(CreatorVector, "target").embedding = _embedding(1.0, 0.0, 0.0)
        session.get(CreatorVector, "close").embedding = _embedding(0.95, 0.05, 0.0)
        session.get(CreatorVector, "mid").embedding = _embedding(0.7, 0.3, 0.0)
        session.get(CreatorVector, "far").embedding = _embedding(0.0, 1.0, 0.0)
        session.commit()

    lookalikes = find_lookalikes("target", k=2)

    assert lookalikes is not None
    assert [creator["account_id"] for creator in lookalikes] == ["close", "mid"]


def test_get_all_creators_returns_all_rows(db_setup: _DummyQueue) -> None:
    embedding_worker.upsert_creator(_creator("creator_a", "alpha", "fitness", 100000))
    embedding_worker.upsert_creator(_creator("creator_b", "beta", "tech", 150000))
    embedding_worker.upsert_creator(_creator("creator_c", "gamma", "travel", 90000))

    creators = get_all_creators()

    assert len(creators) == 3
    assert {creator["account_id"] for creator in creators} == {"creator_a", "creator_b", "creator_c"}


def test_get_sync_db_rolls_back_on_consumer_exception(db_setup: _DummyQueue) -> None:
    generator = get_sync_db()
    session = next(generator)
    session.add(CreatorVector(account_id="rollback_case", embedding=_embedding(0.1), source_text="rollback"))
    session.add(CreatorDiscoveryMeta(account_id="rollback_case", username="rollback", niche_tags=["fitness"]))

    with pytest.raises(RuntimeError, match="boom"):
        generator.throw(RuntimeError("boom"))

    session_factory = get_sync_sessionmaker()
    with session_factory() as verification_session:
        assert verification_session.get(CreatorDiscoveryMeta, "rollback_case") is None
        assert verification_session.get(CreatorVector, "rollback_case") is None
