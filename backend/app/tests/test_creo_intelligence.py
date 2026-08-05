"""Tests for Creo Intelligence backend components.

Covers:
  - creo_session_store  : Redis session read / write / delete / validation
  - creo_intelligence_service : SSE event formatting, safe_json_loads, tool loop helpers
  - creo_intelligence_routes  : API endpoint contracts (POST /chat, DELETE /session)
  - tool_schemas              : 12 tools present, new 4 schemas are valid
  - tool_orchestrator         : 4 new Creo Intelligence handler dispatch
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("BRAND_API_KEY", "test-creo-key")
    return "test-creo-key"


@pytest.fixture(autouse=True)
def reset_creo_rate_limiter():
    """Reset the Creo Intelligence rate limiter before each test."""
    from backend.app.api.creo_intelligence_routes import _rate_limiter
    _rate_limiter.reset()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tool Schemas — all 12 tools present
# ─────────────────────────────────────────────────────────────────────────────


class TestToolSchemas:
    def test_total_tool_count(self):
        from backend.app.ai.tool_schemas import BRAND_DISCOVERY_TOOLS
        assert len(BRAND_DISCOVERY_TOOLS) == 12

    def test_all_expected_tools_present(self):
        from backend.app.ai.tool_schemas import BRAND_DISCOVERY_TOOLS
        names = {t["function"]["name"] for t in BRAND_DISCOVERY_TOOLS}
        expected = {
            # Original 8
            "search_creator_pool",
            "find_lookalike_creators",
            "score_creator_brand_fit",
            "get_creator_analysis",
            "ask_brand_clarification",
            "generate_outreach_brief",
            "generate_content_brief",
            "estimate_campaign_cost",
            # New Creo Intelligence 4
            "plan_campaign",
            "review_campaign_results",
            "suggest_budget_allocation",
            "benchmark_campaign_performance",
        }
        assert names == expected

    def test_new_tools_have_required_fields(self):
        from backend.app.ai.tool_schemas import BRAND_DISCOVERY_TOOLS
        new_tools = [t for t in BRAND_DISCOVERY_TOOLS if t["function"]["name"] in {
            "plan_campaign", "review_campaign_results",
            "suggest_budget_allocation", "benchmark_campaign_performance",
        }]
        for tool in new_tools:
            assert tool["type"] == "function"
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]
            assert "required" in tool["function"]["parameters"]

    def test_plan_campaign_required_fields(self):
        from backend.app.ai.tool_schemas import BRAND_DISCOVERY_TOOLS
        tool = next(t for t in BRAND_DISCOVERY_TOOLS if t["function"]["name"] == "plan_campaign")
        required = tool["function"]["parameters"]["required"]
        assert "campaign_goal" in required

    def test_suggest_budget_allocation_required_fields(self):
        from backend.app.ai.tool_schemas import BRAND_DISCOVERY_TOOLS
        tool = next(t for t in BRAND_DISCOVERY_TOOLS if t["function"]["name"] == "suggest_budget_allocation")
        required = tool["function"]["parameters"]["required"]
        assert "total_budget_inr" in required
        assert "campaign_goal" in required

    def test_benchmark_required_fields(self):
        from backend.app.ai.tool_schemas import BRAND_DISCOVERY_TOOLS
        tool = next(t for t in BRAND_DISCOVERY_TOOLS if t["function"]["name"] == "benchmark_campaign_performance")
        required = tool["function"]["parameters"]["required"]
        assert "niche" in required


# ─────────────────────────────────────────────────────────────────────────────
# 2. Session Store — unit tests with mocked Redis
# ─────────────────────────────────────────────────────────────────────────────


class TestCreoSessionStore:
    """Unit tests for CreoSessionStore — all Redis calls are mocked."""

    @pytest.fixture
    def store(self):
        from backend.app.services.creo_session_store import CreoSessionStore
        return CreoSessionStore()

    # ── get_messages ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_messages_returns_empty_on_miss(self, store):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        with patch("backend.app.services.creo_session_store.get_async_redis", return_value=mock_redis):
            result = await store.get_messages("session-123")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_messages_deserializes_json(self, store):
        messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(messages))
        with patch("backend.app.services.creo_session_store.get_async_redis", return_value=mock_redis):
            result = await store.get_messages("session-abc")
        assert result == messages

    @pytest.mark.asyncio
    async def test_get_messages_returns_empty_on_invalid_json(self, store):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="not-valid-json{{{")
        with patch("backend.app.services.creo_session_store.get_async_redis", return_value=mock_redis):
            result = await store.get_messages("session-bad")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_messages_invalid_session_id(self, store):
        result = await store.get_messages("")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_messages_session_id_with_spaces(self, store):
        result = await store.get_messages("session with spaces")
        assert result == []

    # ── save_messages ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_save_messages_calls_redis_set(self, store):
        messages = [{"role": "user", "content": "test"}]
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        with patch("backend.app.services.creo_session_store.get_async_redis", return_value=mock_redis):
            await store.save_messages("session-save", messages)
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "creo:session:session-save" in call_args[0]

    @pytest.mark.asyncio
    async def test_save_messages_trims_to_max(self, store):
        """Messages beyond the max limit should be trimmed (oldest first)."""
        messages = [{"role": "user", "content": str(i)} for i in range(60)]  # > 50 limit
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        with patch("backend.app.services.creo_session_store.get_async_redis", return_value=mock_redis):
            await store.save_messages("session-trim", messages)
        stored_json = mock_redis.set.call_args[0][1]
        stored = json.loads(stored_json)
        assert len(stored) == 50
        # Should keep the LAST 50 (most recent)
        assert stored[-1]["content"] == "59"

    @pytest.mark.asyncio
    async def test_save_messages_skips_invalid_session_id(self, store):
        mock_redis = AsyncMock()
        with patch("backend.app.services.creo_session_store.get_async_redis", return_value=mock_redis):
            await store.save_messages("", [{"role": "user", "content": "x"}])
        mock_redis.set.assert_not_called()

    # ── delete_session ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_session_returns_true_when_existed(self, store):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        with patch("backend.app.services.creo_session_store.get_async_redis", return_value=mock_redis):
            result = await store.delete_session("session-del")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_session_returns_false_when_missing(self, store):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=0)
        with patch("backend.app.services.creo_session_store.get_async_redis", return_value=mock_redis):
            result = await store.delete_session("session-missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_session_invalid_id_returns_false(self, store):
        result = await store.delete_session("")
        assert result is False

    # ── session_id validation ─────────────────────────────────────────────────

    def test_valid_session_ids_pass(self, store):
        from backend.app.services.creo_session_store import _is_valid_session_id
        assert _is_valid_session_id("abc-123") is True
        assert _is_valid_session_id("550e8400-e29b-41d4-a716-446655440000") is True
        assert _is_valid_session_id("session_test_01") is True

    def test_invalid_session_ids_fail(self, store):
        from backend.app.services.creo_session_store import _is_valid_session_id
        assert _is_valid_session_id("") is False
        assert _is_valid_session_id("session with space") is False
        assert _is_valid_session_id("a" * 129) is False
        assert _is_valid_session_id(None) is False  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# 3. Creo Intelligence Service — SSE helpers & utilities
# ─────────────────────────────────────────────────────────────────────────────


class TestCreoIntelligenceServiceHelpers:

    def test_sse_event_format(self):
        from backend.app.services.creo_intelligence_service import _sse_event
        event = _sse_event("token", {"token": "Hello"})
        assert event.startswith("event: token\n")
        assert "data:" in event
        assert event.endswith("\n\n")
        payload = json.loads(event.split("data: ", 1)[1].strip())
        assert payload["token"] == "Hello"

    def test_sse_token(self):
        from backend.app.services.creo_intelligence_service import _sse_token
        result = _sse_token("world")
        assert "event: token" in result
        assert '"token": "world"' in result or json.loads(result.split("data: ", 1)[1])["token"] == "world"

    def test_sse_done_contains_required_fields(self):
        from backend.app.services.creo_intelligence_service import _sse_done
        result = _sse_done([{"name": "search_creator_pool"}], "sess-1", 1234.5)
        assert "event: done" in result
        payload = json.loads(result.split("data: ", 1)[1])
        assert "tool_calls_made" in payload
        assert payload["session_id"] == "sess-1"
        assert payload["latency_ms"] == 1234.5

    def test_sse_error_format(self):
        from backend.app.services.creo_intelligence_service import _sse_error
        result = _sse_error("Something went wrong")
        assert "event: error" in result
        payload = json.loads(result.split("data: ", 1)[1])
        assert payload["detail"] == "Something went wrong"

    def test_safe_json_loads_valid(self):
        from backend.app.services.creo_intelligence_service import _safe_json_loads
        result = _safe_json_loads('{"niche": "fitness", "limit": 10}')
        assert result == {"niche": "fitness", "limit": 10}

    def test_safe_json_loads_invalid_returns_empty(self):
        from backend.app.services.creo_intelligence_service import _safe_json_loads
        assert _safe_json_loads("not json") == {}
        assert _safe_json_loads(None) == {}  # type: ignore
        assert _safe_json_loads("") == {}

    def test_safe_json_loads_passes_dict_through(self):
        from backend.app.services.creo_intelligence_service import _safe_json_loads
        d = {"key": "value"}
        assert _safe_json_loads(d) == d

    def test_extract_latency_valid(self):
        from backend.app.services.creo_intelligence_service import _extract_latency
        assert _extract_latency({"latency_ms": 123.4}) == 123.4

    def test_extract_latency_missing(self):
        from backend.app.services.creo_intelligence_service import _extract_latency
        assert _extract_latency(None) == 0.0
        assert _extract_latency({}) == 0.0

    def test_large_tool_payload_is_bounded_before_prompting(self):
        from backend.app.services.creo_intelligence_service import _MAX_TOOL_MESSAGE_CHARS, _serialize_tool_payload_for_llm

        serialized = _serialize_tool_payload_for_llm({"success": True, "tool": "search", "data": "x" * 20_000})
        payload = json.loads(serialized)

        assert len(serialized) <= _MAX_TOOL_MESSAGE_CHARS
        assert payload["truncated"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tool Orchestrator — new Creo Intelligence handlers
# ─────────────────────────────────────────────────────────────────────────────


class TestCreoToolOrchestrator:

    @pytest.fixture
    def orchestrator(self):
        from backend.app.services.tool_orchestrator import ToolOrchestrator
        return ToolOrchestrator()

    def test_plan_campaign_dispatches_correctly(self, orchestrator):
        mock_generate = MagicMock(return_value="Campaign plan: Week 1 - find creators...")
        with patch("backend.app.ai.llm_client.LLMClient.generate", mock_generate):
            response = orchestrator.execute_tool("plan_campaign", {
                "brand_name": "TestBrand",
                "campaign_goal": "product launch",
                "budget_inr": 500000,
                "niche": "fitness",
            })
        assert response.success is True
        assert response.tool == "plan_campaign"
        assert "plan" in response.data

    def test_plan_campaign_missing_goal_returns_error(self, orchestrator):
        response = orchestrator.execute_tool("plan_campaign", {"brand_name": "TestBrand"})
        assert response.success is False
        assert "campaign_goal" in response.message.lower() or "required" in response.message.lower()

    def test_review_campaign_results_dispatches_correctly(self, orchestrator):
        mock_generate = MagicMock(return_value="Rating: Good. Reach was above average.")
        with patch("backend.app.ai.llm_client.LLMClient.generate", mock_generate):
            response = orchestrator.execute_tool("review_campaign_results", {
                "campaign_name": "Summer Launch",
                "total_reach": 500000,
                "total_engagement": 25000,
                "creator_count": 5,
                "budget_spent_inr": 200000,
                "niche": "fashion",
            })
        assert response.success is True
        assert "review" in response.data

    def test_review_campaign_missing_name_returns_error(self, orchestrator):
        response = orchestrator.execute_tool("review_campaign_results", {})
        assert response.success is False

    def test_suggest_budget_allocation_dispatches_correctly(self, orchestrator):
        mock_generate = MagicMock(return_value="Nano: 20% (₹100k), Micro: 50% (₹250k), Mid-tier: 30% (₹150k)")
        with patch("backend.app.ai.llm_client.LLMClient.generate", mock_generate):
            response = orchestrator.execute_tool("suggest_budget_allocation", {
                "total_budget_inr": 500000,
                "campaign_goal": "brand awareness",
                "niche": "beauty",
                "creator_count": 10,
            })
        assert response.success is True
        assert "allocation" in response.data
        assert response.data["total_budget_inr"] == 500000.0

    def test_suggest_budget_zero_budget_returns_error(self, orchestrator):
        response = orchestrator.execute_tool("suggest_budget_allocation", {
            "total_budget_inr": 0,
            "campaign_goal": "awareness",
        })
        assert response.success is False

    def test_suggest_budget_missing_goal_returns_error(self, orchestrator):
        response = orchestrator.execute_tool("suggest_budget_allocation", {
            "total_budget_inr": 100000,
        })
        assert response.success is False

    def test_benchmark_campaign_dispatches_correctly(self, orchestrator):
        mock_generate = MagicMock(return_value="Overall Grade: B. Engagement: Above benchmark (3.2% vs 2.5% avg).")
        with patch("backend.app.ai.llm_client.LLMClient.generate", mock_generate):
            response = orchestrator.execute_tool("benchmark_campaign_performance", {
                "niche": "tech",
                "engagement_rate": 0.032,
                "reach_per_post": 15000,
                "cost_per_engagement_inr": 4.5,
            })
        assert response.success is True
        assert "benchmark_analysis" in response.data
        assert response.data["niche"] == "tech"

    def test_benchmark_missing_niche_returns_error(self, orchestrator):
        response = orchestrator.execute_tool("benchmark_campaign_performance", {})
        assert response.success is False

    def test_unknown_tool_returns_error(self, orchestrator):
        response = orchestrator.execute_tool("nonexistent_tool", {})
        assert response.success is False
        assert "Unknown tool" in response.message or "unknown" in response.message.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 5. API Routes — endpoint contracts
# ─────────────────────────────────────────────────────────────────────────────


class TestCreoIntelligenceRoutes:

    # ── Auth & validation ─────────────────────────────────────────────────────

    def test_chat_requires_api_key(self, client: TestClient):
        response = client.post("/api/creo-intelligence/chat", json={
            "session_id": "test-sess-001",
            "message": "Find tech creators",
        })
        assert response.status_code == 401

    def test_chat_rejects_empty_message(self, client: TestClient, api_key: str):
        response = client.post(
            "/api/creo-intelligence/chat",
            headers={"X-API-Key": api_key},
            json={"session_id": "sess-001", "message": "x"},  # below min_length=2
        )
        # "x" is 1 char, min is 2 — should be 422
        assert response.status_code == 422

    def test_chat_rejects_missing_session_id(self, client: TestClient, api_key: str):
        response = client.post(
            "/api/creo-intelligence/chat",
            headers={"X-API-Key": api_key},
            json={"message": "Find me fitness creators"},
        )
        assert response.status_code == 422

    def test_chat_rejects_extra_fields(self, client: TestClient, api_key: str):
        """extra='forbid' should reject unknown fields."""
        response = client.post(
            "/api/creo-intelligence/chat",
            headers={"X-API-Key": api_key},
            json={
                "session_id": "sess-001",
                "message": "Find creators",
                "unknown_field": "should fail",
            },
        )
        assert response.status_code == 422

    def test_chat_returns_sse_content_type(self, client: TestClient, api_key: str):
        """Endpoint should return text/event-stream even when mocked."""
        async def _fake_stream(*args, **kwargs):
            yield 'event: token\ndata: {"token": "Hello"}\n\n'
            yield 'event: done\ndata: {"tool_calls_made": [], "session_id": "s1", "latency_ms": 100}\n\n'

        with patch(
            "backend.app.api.creo_intelligence_routes.creo_intelligence_stream",
            side_effect=_fake_stream,
        ):
            response = client.post(
                "/api/creo-intelligence/chat",
                headers={"X-API-Key": api_key},
                json={"session_id": "s1", "message": "Find creators in Mumbai"},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_chat_sse_stream_contains_token_and_done(self, client: TestClient, api_key: str):
        """Verify the SSE stream contains token and done events."""
        async def _fake_stream(*args, **kwargs):
            yield 'event: token\ndata: {"token": "Based"}\n\n'
            yield 'event: token\ndata: {"token": " on"}\n\n'
            yield 'event: done\ndata: {"tool_calls_made": [], "session_id": "sess-st", "latency_ms": 500}\n\n'

        with patch(
            "backend.app.api.creo_intelligence_routes.creo_intelligence_stream",
            side_effect=_fake_stream,
        ):
            response = client.post(
                "/api/creo-intelligence/chat",
                headers={"X-API-Key": api_key},
                json={"session_id": "sess-st", "message": "Find creators please"},
            )

        assert response.status_code == 200
        body = response.text
        assert "event: token" in body
        assert "event: done" in body

    def test_chat_sse_stream_with_tool_call_event(self, client: TestClient, api_key: str):
        async def _fake_stream(*args, **kwargs):
            yield 'event: tool_call\ndata: {"tool": "search_creator_pool", "args": {"niche": "tech"}}\n\n'
            yield 'event: token\ndata: {"token": "I found"}\n\n'
            yield 'event: done\ndata: {"tool_calls_made": [{"name": "search_creator_pool"}], "session_id": "tc-1", "latency_ms": 1200}\n\n'

        with patch(
            "backend.app.api.creo_intelligence_routes.creo_intelligence_stream",
            side_effect=_fake_stream,
        ):
            response = client.post(
                "/api/creo-intelligence/chat",
                headers={"X-API-Key": api_key},
                json={"session_id": "tc-1", "message": "Find tech creators"},
            )

        assert response.status_code == 200
        body = response.text
        assert "event: tool_call" in body
        assert "search_creator_pool" in body

    def test_chat_passes_brand_name_to_service(self, client: TestClient, api_key: str):
        captured = {}

        async def _fake_stream(session_id, user_message, brand_name=None):
            captured["brand_name"] = brand_name
            yield 'event: done\ndata: {"tool_calls_made": [], "session_id": "b1", "latency_ms": 100}\n\n'

        with patch(
            "backend.app.api.creo_intelligence_routes.creo_intelligence_stream",
            side_effect=_fake_stream,
        ):
            client.post(
                "/api/creo-intelligence/chat",
                headers={"X-API-Key": api_key},
                json={
                    "session_id": "b1",
                    "message": "Find creators",
                    "brand_name": "MyCoolBrand",
                },
            )

        assert captured.get("brand_name") == "MyCoolBrand"

    # ── DELETE /session ───────────────────────────────────────────────────────

    def test_delete_session_requires_api_key(self, client: TestClient):
        response = client.delete("/api/creo-intelligence/session/sess-abc")
        assert response.status_code == 401

    def test_delete_session_returns_deleted_true(self, client: TestClient, api_key: str):
        mock_store = AsyncMock()
        mock_store.delete_session = AsyncMock(return_value=True)
        with patch(
            "backend.app.api.creo_intelligence_routes.get_session_store",
            return_value=mock_store,
        ):
            response = client.delete(
                "/api/creo-intelligence/session/sess-to-delete",
                headers={"X-API-Key": api_key},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["session_id"] == "sess-to-delete"

    def test_delete_session_returns_deleted_false_when_missing(self, client: TestClient, api_key: str):
        mock_store = AsyncMock()
        mock_store.delete_session = AsyncMock(return_value=False)
        with patch(
            "backend.app.api.creo_intelligence_routes.get_session_store",
            return_value=mock_store,
        ):
            response = client.delete(
                "/api/creo-intelligence/session/nonexistent",
                headers={"X-API-Key": api_key},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is False

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def test_chat_rate_limit_enforced(self, client: TestClient, api_key: str, monkeypatch):
        """After 20 requests, the 21st should be rate-limited (429)."""
        from backend.app.api.creo_intelligence_routes import _rate_limiter
        monkeypatch.setattr(_rate_limiter, "max_requests", 3)

        async def _noop_stream(*args, **kwargs):
            yield 'event: done\ndata: {"tool_calls_made": [], "session_id": "rl", "latency_ms": 10}\n\n'

        with patch(
            "backend.app.api.creo_intelligence_routes.creo_intelligence_stream",
            side_effect=_noop_stream,
        ):
            for _ in range(3):
                r = client.post(
                    "/api/creo-intelligence/chat",
                    headers={"X-API-Key": api_key},
                    json={"session_id": "rl", "message": "Find creators"},
                )
                assert r.status_code == 200

            # 4th request should be rate-limited
            r = client.post(
                "/api/creo-intelligence/chat",
                headers={"X-API-Key": api_key},
                json={"session_id": "rl", "message": "Find creators"},
            )
            assert r.status_code == 429
