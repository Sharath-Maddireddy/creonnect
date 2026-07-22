"""Creo Intelligence — multi-turn agentic chat service with SSE streaming.

This service powers the Creo Intelligence chat UI at brand.creonnect.com/ai-builder.
It wraps the existing ToolOrchestrator + LLMClient with:

  - Redis-backed conversation history (multi-turn, load-balancer safe)
  - SSE streaming of the final LLM response token-by-token
  - The full "Creo Intelligence" persona system prompt
  - All 12 brand tools (8 discovery + 4 strategic)
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from backend.app.ai.llm_client import LLMClient, LLMClientError
from backend.app.ai.tool_schemas import BRAND_DISCOVERY_TOOLS
from backend.app.services.creo_session_store import get_session_store
from backend.app.services.tool_orchestrator import ToolOrchestrator
from backend.app.utils.logger import logger

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_TOOL_ITERATIONS = 6  # guard against infinite tool-call loops
_STREAMING_MODEL = None
_STREAMING_TEMPERATURE = 0.3
_STREAMING_MAX_TOKENS = 1500

# ── System prompt ──────────────────────────────────────────────────────────────

_CREO_INTELLIGENCE_SYSTEM_PROMPT = """\
You are Creo Intelligence — Creonnect's centralized AI assistant for brand campaign \
strategy, creator discovery, and performance analysis.

You help brand teams:
- Find and evaluate creators for campaigns (by niche, location, follower range)
- Plan campaigns with goals, timelines, and budgets
- Draft personalised outreach messages and content briefs
- Review and benchmark campaign performance against industry standards
- Allocate budgets across creator tiers for maximum ROI
- Identify lookalike creators and score creator-brand fit

## Guidelines
- Always use your available tools before responding with recommendations — \
  never guess creator metrics or fabricate data.
- When presenting creators, always include: handle, follower count, engagement \
  rate, and your reasoning for the recommendation.
- If the brand's brief is ambiguous, use the ask_brand_clarification tool once \
  before proceeding.
- Be confident, strategic, and concise. Avoid filler phrases.
- Format structured outputs (plans, allocations, benchmarks) using clear \
  headers and bullet points for readability.
- All monetary values should use Indian Rupees (INR / ₹) unless the brand \
  specifies otherwise.
"""

# ── SSE helpers ────────────────────────────────────────────────────────────────


def _sse_event(event: str, data: Any) -> str:
    """Format a single Server-Sent Event frame."""
    payload = json.dumps(data, ensure_ascii=True, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _sse_token(token: str) -> str:
    return _sse_event("token", {"token": token})


def _sse_tool_call(tool_name: str, args: dict[str, Any]) -> str:
    return _sse_event("tool_call", {"tool": tool_name, "args": args})


def _sse_done(tool_calls_made: list[dict], session_id: str, latency_ms: float) -> str:
    return _sse_event(
        "done",
        {
            "tool_calls_made": tool_calls_made,
            "session_id": session_id,
            "latency_ms": round(latency_ms, 1),
        },
    )


def _sse_error(detail: str) -> str:
    return _sse_event("error", {"detail": detail})


# ── Main service ───────────────────────────────────────────────────────────────


async def creo_intelligence_stream(
    session_id: str,
    user_message: str,
    brand_name: str | None = None,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted strings for a Creo Intelligence turn.

    SSE events emitted in order:
      1. ``tool_call``  — for each tool the LLM invokes (may be zero or many)
      2. ``token``      — one per streamed token of the final assistant response
      3. ``done``       — final metadata (tool calls made, latency)

    On error: a single ``error`` event is emitted then the generator exits.

    Args:
        session_id:   Client-supplied opaque session identifier (validated server-side).
        user_message: The brand user's latest message.
        brand_name:   Optional brand name prepended to the message for context.
    """
    started_at = time.perf_counter()
    store = get_session_store()
    orchestrator = ToolOrchestrator()

    # ── 1. Load conversation history ──────────────────────────────────────────
    try:
        history = await store.get_messages(session_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("[CreoIntelligence] Failed to load session %s: %s", session_id, exc)
        yield _sse_error("Failed to load conversation history. Please try again.")
        return

    # ── 2. Build message list for this turn ───────────────────────────────────
    effective_message = user_message.strip()
    if brand_name and isinstance(brand_name, str) and brand_name.strip():
        effective_message = f"Brand: {brand_name.strip()}\n\n{effective_message}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _CREO_INTELLIGENCE_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": effective_message},
    ]

    # ── 3. Agentic tool-calling loop (blocking, run in thread pool) ───────────
    tool_calls_made: list[dict[str, Any]] = []

    try:
        llm = LLMClient(model_name=_STREAMING_MODEL, temperature=_STREAMING_TEMPERATURE)

        messages, tool_calls_made = await asyncio.to_thread(
            _run_tool_loop,
            llm,
            orchestrator,
            messages,
        )
    except LLMClientError as exc:
        logger.error("[CreoIntelligence] LLM tool loop failed: %s", exc)
        yield _sse_error("AI service is temporarily unavailable. Please try again.")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CreoIntelligence] Unexpected error in tool loop.")
        yield _sse_error("An unexpected error occurred. Please try again.")
        return

    # Emit tool_call SSE events for each tool that was executed
    for tc in tool_calls_made:
        yield _sse_tool_call(tc.get("name", ""), tc.get("args", {}))

    # ── 4. Stream the final response ──────────────────────────────────────────
    final_response_text = ""
    try:
        async for token in _stream_final_response(llm, messages):
            final_response_text += token
            yield _sse_token(token)
    except Exception as exc:  # noqa: BLE001
        logger.error("[CreoIntelligence] Streaming failed: %s", exc)
        yield _sse_error("Response streaming failed. Please retry.")
        return

    # ── 5. Persist updated history to Redis ───────────────────────────────────
    new_history = [
        *history,
        {"role": "user", "content": effective_message},
        {"role": "assistant", "content": final_response_text},
    ]
    try:
        await store.save_messages(session_id, new_history)
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: the response was already streamed; log and continue
        logger.error("[CreoIntelligence] Failed to persist session %s: %s", session_id, exc)

    latency_ms = (time.perf_counter() - started_at) * 1000.0
    yield _sse_done(tool_calls_made, session_id, latency_ms)
    logger.info(
        "[CreoIntelligence] session=%s tools=%d latency_ms=%.0f",
        session_id,
        len(tool_calls_made),
        latency_ms,
    )


# ── Tool loop (sync, runs in thread pool) ─────────────────────────────────────


def _run_tool_loop(
    llm: LLMClient,
    orchestrator: ToolOrchestrator,
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Execute the agentic tool-calling loop synchronously.

    Returns:
        (updated_messages, tool_calls_made)
    """
    tool_calls_made: list[dict[str, Any]] = []

    for iteration in range(_MAX_TOOL_ITERATIONS):
        response = llm.generate_with_tools(messages=messages, tools=BRAND_DISCOVERY_TOOLS)
        choice = response.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None) or []

        if not tool_calls:
            # No more tool calls — the LLM is ready to give its final response
            # We do NOT append the assistant message here; streaming will produce it
            break

        # Append the assistant's tool-use decision to the message chain
        assistant_payload: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": getattr(call, "id", ""),
                    "type": "function",
                    "function": {
                        "name": getattr(getattr(call, "function", None), "name", ""),
                        "arguments": getattr(getattr(call, "function", None), "arguments", "{}"),
                    },
                }
                for call in tool_calls
            ],
        }
        messages.append(assistant_payload)

        # Execute each tool and append results
        for call in tool_calls:
            call_id = getattr(call, "id", "")
            function_obj = getattr(call, "function", None)
            function_name = getattr(function_obj, "name", "")
            raw_arguments = getattr(function_obj, "arguments", "{}")

            parsed_args = _safe_json_loads(raw_arguments)

            try:
                tool_response = orchestrator.execute_tool(function_name, parsed_args)
                tool_latency_ms = _extract_latency(tool_response.meta)
                tool_calls_made.append(
                    {"name": function_name, "args": parsed_args, "latency_ms": tool_latency_ms}
                )
                tool_payload = tool_response.model_dump(mode="python")
            except Exception as exc:  # noqa: BLE001
                logger.exception("[CreoIntelligence] Tool execution error: tool=%s", function_name)
                tool_calls_made.append({"name": function_name, "args": parsed_args, "latency_ms": 0.0})
                tool_payload = {
                    "success": False,
                    "tool": function_name,
                    "message": f"Tool execution error: {exc}",
                    "data": None,
                    "ui": None,
                    "meta": None,
                }

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(tool_payload, ensure_ascii=True, default=str),
                }
            )

        if iteration == _MAX_TOOL_ITERATIONS - 1:
            logger.warning("[CreoIntelligence] Reached max tool iterations (%d).", _MAX_TOOL_ITERATIONS)

    return messages, tool_calls_made


# ── Streaming final response ───────────────────────────────────────────────────


async def _stream_final_response(
    llm: LLMClient,
    messages: list[dict[str, Any]],
) -> AsyncGenerator[str, None]:
    """Stream the final assistant response token-by-token via OpenAI streaming API."""
    client = llm.client
    if client is None:
        raise LLMClientError("LLM client not initialized.")

    model = llm.model

    def _open_stream():
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if "5.6" in model or "o1" in model:
            payload["max_completion_tokens"] = _STREAMING_MAX_TOKENS
        else:
            payload["max_tokens"] = _STREAMING_MAX_TOKENS
            payload["temperature"] = _STREAMING_TEMPERATURE
        return client.chat.completions.create(**payload)

    stream = await asyncio.to_thread(_open_stream)

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue
        token = getattr(delta, "content", None)
        if token:
            yield token


# ── Utilities ─────────────────────────────────────────────────────────────────


def _safe_json_loads(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _extract_latency(meta: Any) -> float:
    if not isinstance(meta, dict):
        return 0.0
    raw = meta.get("latency_ms")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    return 0.0
