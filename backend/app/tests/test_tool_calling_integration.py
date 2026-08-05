"""Integration tests for tool-calling brand discovery and orchestration."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api.campaign_routes import rate_limiter
from backend.app.domain.brand_models import CreatorMatchScore
from backend.app.domain.tool_response import ToolResponse, ToolResponseMeta
from backend.app.services.brand_chat_service import BrandChatResponse, brand_chat_discover
from backend.app.services.tool_orchestrator import ToolOrchestrator
from backend.main import app


MOCK_CREATOR = {
    "account_id": "test_creator_001",
    "username": "fitness_guru",
    "creator_dominant_category": "fitness",
    "follower_count": 75000,
    "ahs_score": 85.0,
    "predicted_engagement_rate": 0.045,
    "avg_visual_quality_score": 38.0,
    "avg_brand_safety_score": 42.0,
    "adult_content_detected": False,
    "bio": "Fitness coach & content creator",
    "avg_views": 15000,
    "avg_likes": 3500,
    "avg_comments": 120,
    "posts_per_week": 4.5,
    "niche_tags": ["fitness", "wellness"],
    "embedding": None,
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_campaign_rate_limiter() -> None:
    rate_limiter.reset()


@pytest.fixture
def valid_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("BRAND_API_KEY", "test_key")
    return "test_key"


def _make_llm_response(*, content: str = "", tool_calls: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _make_tool_call(call_id: str, name: str, arguments: dict) -> SimpleNamespace:
    function = SimpleNamespace(name=name, arguments=json.dumps(arguments))
    return SimpleNamespace(id=call_id, function=function)


def test_tool_response_envelope_ok() -> None:
    response = ToolResponse.ok(
        tool="search_creator_pool",
        data=[MOCK_CREATOR],
        message="ok",
        ui={"layout": "card_grid"},
        meta=ToolResponseMeta(latency_ms=12.3, result_count=1),
    )

    assert response.success is True
    assert response.tool == "search_creator_pool"
    assert response.message == "ok"
    assert isinstance(response.data, list)
    assert response.ui == {"layout": "card_grid"}
    assert response.meta is not None
    assert response.meta["latency_ms"] == 12.3
    assert response.meta["result_count"] == 1


def test_tool_response_envelope_error() -> None:
    response = ToolResponse.error(
        tool="score_creator_brand_fit",
        message="invalid params",
        meta=ToolResponseMeta(latency_ms=4.0),
    )

    assert response.success is False
    assert response.tool == "score_creator_brand_fit"
    assert response.message == "invalid params"
    assert response.data is None
    assert response.ui is None
    assert response.meta is not None
    assert response.meta["latency_ms"] == 4.0


def test_orchestrator_search_creator_pool() -> None:
    orchestrator = ToolOrchestrator()

    with patch(
        "backend.app.services.tool_orchestrator.query_creator_pool",
        return_value=[MOCK_CREATOR],
    ) as mock_query:
        response = orchestrator.execute_tool(
            "search_creator_pool",
            {
                "niche": "fitness",
                "min_followers": 10000,
                "max_followers": 100000,
                "limit": 20,
            },
        )

    assert response.success is True
    assert response.tool == "search_creator_pool"
    assert isinstance(response.data, list)
    assert response.data[0]["account_id"] == MOCK_CREATOR["account_id"]
    assert response.ui == {"layout": "card_grid"}
    mock_query.assert_called_once_with(
        niche="fitness",
        min_followers=10000,
        max_followers=100000,
        limit=20,
    )


def test_orchestrator_find_lookalikes() -> None:
    orchestrator = ToolOrchestrator()

    with patch(
        "backend.app.services.tool_orchestrator.find_lookalikes",
        side_effect=[[MOCK_CREATOR], None],
    ):
        found = orchestrator.execute_tool(
            "find_lookalike_creators",
            {"account_id": MOCK_CREATOR["account_id"], "limit": 5},
        )
        missing = orchestrator.execute_tool(
            "find_lookalike_creators",
            {"account_id": "unknown", "limit": 5},
        )

    assert found.success is True
    assert isinstance(found.data, list)
    assert found.data[0]["account_id"] == MOCK_CREATOR["account_id"]

    assert missing.success is False
    assert "not found" in missing.message.lower()


def test_orchestrator_score_brand_fit() -> None:
    orchestrator = ToolOrchestrator()

    score = CreatorMatchScore(
        account_id=MOCK_CREATOR["account_id"],
        total_match_score=86.0,
        niche_fit=18.0,
        engagement_quality=16.0,
        brand_safety_fit=17.0,
        content_quality_fit=17.0,
        audience_size_fit=18.0,
        match_band="EXCELLENT",
        disqualified=False,
        disqualify_reasons=[],
        notes=[],
    )

    with (
        patch.object(orchestrator, "_load_creator_by_account_id", return_value=MOCK_CREATOR),
        patch("backend.app.services.tool_orchestrator.score_creator_against_brand", return_value=score),
    ):
        response = orchestrator.execute_tool(
            "score_creator_brand_fit",
            {
                "account_id": MOCK_CREATOR["account_id"],
                "brand_niche": "fitness",
                "min_followers": 20000,
                "max_followers": 150000,
                "min_engagement_rate": 0.02,
            },
        )

    assert response.success is True
    assert isinstance(response.data, dict)
    assert response.data["account_id"] == MOCK_CREATOR["account_id"]
    assert response.data["total_match_score"] == 86.0
    assert response.ui == {"layout": "score_card"}


def test_orchestrator_unknown_tool() -> None:
    orchestrator = ToolOrchestrator()
    response = orchestrator.execute_tool("does_not_exist", {})

    assert response.success is False
    assert response.tool == "does_not_exist"
    assert "unknown tool" in response.message.lower()


def test_orchestrator_invalid_params() -> None:
    orchestrator = ToolOrchestrator()

    bad_payload = orchestrator.execute_tool("search_creator_pool", {"limit": "not-an-int"})
    bad_args_type = orchestrator.execute_tool("search_creator_pool", [])

    assert bad_payload.success is False
    assert "limit" in bad_payload.message.lower()

    assert bad_args_type.success is False
    assert "invalid arguments payload" in bad_args_type.message.lower()


def test_chat_loop_single_tool_call() -> None:
    tool_call = _make_tool_call(
        call_id="tc-1",
        name="search_creator_pool",
        arguments={"niche": "fitness", "limit": 3},
    )

    llm_responses = [
        _make_llm_response(tool_calls=[tool_call]),
        _make_llm_response(content="Here are the best fitness creators to start with."),
    ]

    with (
        patch("backend.app.services.brand_chat_service.LLMClient") as llm_cls,
        patch("backend.app.services.brand_chat_service.ToolOrchestrator") as orchestrator_cls,
    ):
        llm_instance = llm_cls.return_value
        llm_instance.generate_with_tools.side_effect = llm_responses

        orchestrator_instance = orchestrator_cls.return_value
        orchestrator_instance.execute_tool.return_value = ToolResponse.ok(
            tool="search_creator_pool",
            data=[MOCK_CREATOR],
            message="Found 1 creator(s).",
            ui={"layout": "card_grid"},
            meta=ToolResponseMeta(latency_ms=7.0, result_count=1),
        )

        result = brand_chat_discover("Need fitness creators for a wellness campaign")

    assert isinstance(result, BrandChatResponse)
    assert result.final_response == "Here are the best fitness creators to start with."
    assert len(result.tool_calls_made) == 1
    assert result.tool_calls_made[0]["name"] == "search_creator_pool"
    assert len(result.results) == 1
    assert result.results[0]["account_id"] == MOCK_CREATOR["account_id"]


def test_chat_loop_multi_tool_call() -> None:
    search_call = _make_tool_call(
        call_id="tc-search",
        name="search_creator_pool",
        arguments={"niche": "fitness", "limit": 5},
    )
    score_call = _make_tool_call(
        call_id="tc-score",
        name="score_creator_brand_fit",
        arguments={"account_id": "test_creator_001", "brand_niche": "fitness"},
    )

    llm_responses = [
        _make_llm_response(tool_calls=[search_call]),
        _make_llm_response(tool_calls=[score_call]),
        _make_llm_response(content="Combined search + scoring strategy complete."),
    ]

    with (
        patch("backend.app.services.brand_chat_service.LLMClient") as llm_cls,
        patch("backend.app.services.brand_chat_service.ToolOrchestrator") as orchestrator_cls,
    ):
        llm_instance = llm_cls.return_value
        llm_instance.generate_with_tools.side_effect = llm_responses

        orchestrator_instance = orchestrator_cls.return_value
        orchestrator_instance.execute_tool.side_effect = [
            ToolResponse.ok(
                tool="search_creator_pool",
                data=[
                    {"account_id": "test_creator_001", "follower_count": 75000},
                    {"account_id": "test_creator_002", "follower_count": 90000},
                ],
                message="Found creators.",
                meta=ToolResponseMeta(latency_ms=5.0, result_count=2),
            ),
            ToolResponse.ok(
                tool="score_creator_brand_fit",
                data={
                    "account_id": "test_creator_001",
                    "follower_count": 75000,
                    "total_match_score": 92.0,
                },
                message="Scored creator.",
                meta=ToolResponseMeta(latency_ms=8.0, result_count=1),
            ),
        ]

        result = brand_chat_discover("Find and score fitness creators")

    assert result.final_response == "Combined search + scoring strategy complete."
    assert len(result.tool_calls_made) == 2
    assert len(result.results) == 2
    assert result.results[0]["account_id"] == "test_creator_001"
    assert result.results[0]["total_match_score"] == 92.0


def test_chat_loop_max_iterations() -> None:
    looping_call = _make_tool_call(
        call_id="tc-loop",
        name="search_creator_pool",
        arguments={"niche": "fitness"},
    )

    def _llm_side_effect(*args, **kwargs):
        if kwargs.get("tool_choice") == "none":
            return _make_llm_response(content="Final response after max tool calls.")
        return _make_llm_response(tool_calls=[looping_call])

    with (
        patch("backend.app.services.brand_chat_service.LLMClient") as llm_cls,
        patch("backend.app.services.brand_chat_service.ToolOrchestrator") as orchestrator_cls,
    ):
        llm_instance = llm_cls.return_value
        llm_instance.generate_with_tools.side_effect = _llm_side_effect

        orchestrator_instance = orchestrator_cls.return_value
        orchestrator_instance.execute_tool.return_value = ToolResponse.ok(
            tool="search_creator_pool",
            data=[MOCK_CREATOR],
            message="Found creators.",
            meta=ToolResponseMeta(latency_ms=3.0, result_count=1),
        )

        result = brand_chat_discover("Keep calling tools")

    assert result.final_response == "Final response after max tool calls."
    assert len(result.tool_calls_made) == 5
    assert llm_instance.generate_with_tools.call_count == 6

    last_call_kwargs = llm_instance.generate_with_tools.call_args_list[-1].kwargs
    assert last_call_kwargs["tool_choice"] == "none"


def test_chat_endpoint_integration(client: TestClient, valid_api_key: str) -> None:
    mock_service_response = BrandChatResponse(
        tool_calls_made=[{"name": "search_creator_pool", "args": {"niche": "fitness"}, "latency_ms": 5.0}],
        final_response="Top creators identified.",
        results=[MOCK_CREATOR],
        clarification=None,
        total_latency_ms=40.0,
    )

    with patch(
        "backend.app.api.campaign_routes.brand_chat_discover_service",
        return_value=mock_service_response,
    ):
        response = client.post(
            "/api/brand/campaign/chat",
            headers={"X-API-Key": valid_api_key},
            json={
                "prompt": "Find fitness creators for an upcoming supplement launch",
                "brand_name": "FitCo",
            },
        )

    assert response.status_code == 200
    data = response.json()

    assert data["final_response"] == "Top creators identified."
    assert isinstance(data["results"], list)
    assert isinstance(data["tool_calls_made"], list)
    assert "total_latency_ms" in data


def test_chat_endpoint_rate_limit(client: TestClient, valid_api_key: str) -> None:
    mock_service_response = BrandChatResponse(
        tool_calls_made=[],
        final_response="ok",
        results=[],
        clarification=None,
        total_latency_ms=1.0,
    )

    with patch(
        "backend.app.api.campaign_routes.brand_chat_discover_service",
        return_value=mock_service_response,
    ):
        last_response = None
        for _ in range(11):
            last_response = client.post(
                "/api/brand/campaign/chat",
                headers={"X-API-Key": valid_api_key},
                json={"prompt": "Need fitness creators for our campaign"},
            )

    assert last_response is not None
    assert last_response.status_code == 429
    assert "rate limit exceeded" in last_response.json()["detail"].lower()
