"""Tests for vector configuration guardrails."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.ai.llm_client import LLMClient, LLMClientError
from backend.app.infra.models import CREATOR_EMBEDDING_MODEL_NAME, EMBEDDING_DIMENSION
from backend.app.services.creator_pool_service import _get_hnsw_ef_search


def test_hnsw_ef_search_defaults_to_100(monkeypatch) -> None:
    monkeypatch.delenv("PGVECTOR_HNSW_EF_SEARCH", raising=False)
    assert _get_hnsw_ef_search() == 100


def test_hnsw_ef_search_invalid_value_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("PGVECTOR_HNSW_EF_SEARCH", "invalid")
    assert _get_hnsw_ef_search() == 100


def test_embed_rejects_dimension_mismatch() -> None:
    client = LLMClient()

    class _EmbeddingsAPI:
        @staticmethod
        def create(*, input: str, model: str):  # noqa: ARG004
            assert model == CREATOR_EMBEDDING_MODEL_NAME
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])

    client._client = SimpleNamespace(embeddings=_EmbeddingsAPI())

    with pytest.raises(LLMClientError, match="Embedding dimension mismatch"):
        client.embed("creator profile text")


def test_embed_raises_client_error_on_provider_failure() -> None:
    client = LLMClient()

    class _EmbeddingsAPI:
        @staticmethod
        def create(*, input: str, model: str):  # noqa: ARG004
            raise TimeoutError("embedding timeout")

    client._client = SimpleNamespace(embeddings=_EmbeddingsAPI())

    with pytest.raises(LLMClientError, match="embedding timeout"):
        client.embed("creator profile text")


def test_embed_accepts_expected_dimension() -> None:
    client = LLMClient()
    expected_embedding = [0.01] * EMBEDDING_DIMENSION

    class _EmbeddingsAPI:
        @staticmethod
        def create(*, input: str, model: str):  # noqa: ARG004
            assert model == CREATOR_EMBEDDING_MODEL_NAME
            return SimpleNamespace(data=[SimpleNamespace(embedding=expected_embedding)])

    client._client = SimpleNamespace(embeddings=_EmbeddingsAPI())

    assert client.embed("creator profile text") == expected_embedding
