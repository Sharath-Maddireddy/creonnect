"""Agentic brand discovery service with bounded tool-calling orchestration."""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.ai.llm_client import LLMClient
from backend.app.ai.tool_schemas import BRAND_DISCOVERY_TOOLS, MAX_TOOL_CALLS
from backend.app.services.tool_orchestrator import ToolOrchestrator
from backend.app.utils.logger import logger


class BrandChatResponse(BaseModel):
    """Response envelope for brand chat discovery tool-calling sessions."""

    model_config = ConfigDict(extra="forbid")

    tool_calls_made: list[dict[str, Any]] = Field(default_factory=list)
    final_response: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    clarification: dict[str, Any] | None = None
    total_latency_ms: float


def brand_chat_discover(prompt: str, brand_name: str | None = None) -> BrandChatResponse:
    """Run an agentic tool-calling loop to discover creator matches for a brand brief."""
    started_at = time.perf_counter()

    llm = LLMClient(model_name="gpt-4o", temperature=0.2)
    orchestrator = ToolOrchestrator()

    user_prompt = prompt.strip() if isinstance(prompt, str) else ""
    if not user_prompt:
        return BrandChatResponse(
            final_response="Please provide a campaign brief so I can find relevant creators.",
            total_latency_ms=(time.perf_counter() - started_at) * 1000.0,
        )

    if isinstance(brand_name, str) and brand_name.strip():
        user_prompt = f"Brand: {brand_name.strip()}\n\nBrief: {user_prompt}"

    system_prompt = (
        "You are Creonnect's AI campaign discovery assistant. You help brands "
        "find the best creator matches by using the available tools. Analyze the brand's brief "
        "and decide which tools to call. You may call multiple tools to combine search strategies "
        "(e.g., lookalike + filter search). Always explain your discovery strategy."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    tool_calls_made: list[dict[str, Any]] = []
    collected_results: list[dict[str, Any]] = []
    clarification: dict[str, Any] | None = None
    final_response = ""

    iterations = 0
    while iterations < MAX_TOOL_CALLS:
        iterations += 1
        response = llm.generate_with_tools(messages=messages, tools=BRAND_DISCOVERY_TOOLS)
        choice = response.choices[0]
        message = choice.message

        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            final_response = (message.content or "").strip()
            break

        assistant_payload: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [],
        }
        for call in tool_calls:
            function_obj = getattr(call, "function", None)
            function_name = getattr(function_obj, "name", "")
            raw_arguments = getattr(function_obj, "arguments", "{}")
            assistant_payload["tool_calls"].append(
                {
                    "id": getattr(call, "id", ""),
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": raw_arguments if isinstance(raw_arguments, str) else "{}",
                    },
                }
            )

        messages.append(assistant_payload)

        for call in tool_calls:
            call_id = getattr(call, "id", "")
            function_obj = getattr(call, "function", None)
            function_name = getattr(function_obj, "name", "")
            raw_arguments = getattr(function_obj, "arguments", "{}")

            parsed_args = _safe_json_loads(raw_arguments)
            if not isinstance(parsed_args, dict):
                parsed_args = {}

            try:
                tool_response = orchestrator.execute_tool(function_name, parsed_args)
                tool_latency_ms = _extract_latency_ms(tool_response.meta)
                tool_calls_made.append(
                    {
                        "name": function_name,
                        "args": parsed_args,
                        "latency_ms": tool_latency_ms,
                    }
                )

                if tool_response.success:
                    _collect_results(collected_results, tool_response.data)
                    if tool_response.tool == "ask_brand_clarification" and isinstance(tool_response.data, dict):
                        clarification = dict(tool_response.data)

                tool_payload = tool_response.model_dump(mode="python")
            except Exception as exc:  # noqa: BLE001
                logger.exception("[BrandChat] Tool execution failed tool=%s", function_name)
                tool_calls_made.append(
                    {
                        "name": function_name,
                        "args": parsed_args,
                        "latency_ms": 0.0,
                    }
                )
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

    if not final_response:
        messages.append(
            {
                "role": "user",
                "content": (
                    "You have reached the maximum number of tool calls. Please provide your final "
                    "response based on the information gathered so far."
                ),
            }
        )
        forced = llm.generate_with_tools(
            messages=messages,
            tools=BRAND_DISCOVERY_TOOLS,
            tool_choice="none",
        )
        final_response = (forced.choices[0].message.content or "").strip()

    merged_results = _dedupe_and_rank_results(collected_results)

    return BrandChatResponse(
        tool_calls_made=tool_calls_made,
        final_response=final_response,
        results=merged_results,
        clarification=clarification,
        total_latency_ms=(time.perf_counter() - started_at) * 1000.0,
    )


def _safe_json_loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("[BrandChat] Failed to decode tool arguments: %s", value)
            return {}
    return value if isinstance(value, dict) else {}


def _collect_results(store: list[dict[str, Any]], payload: Any) -> None:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                store.append(item)
        return

    if isinstance(payload, dict):
        if "account_id" in payload:
            store.append(payload)
            return
        nested = payload.get("results")
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    store.append(item)


def _dedupe_and_rank_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_account: dict[str, dict[str, Any]] = {}

    for result in results:
        account_id = result.get("account_id")
        if not isinstance(account_id, str) or not account_id.strip():
            continue
        key = account_id.strip()

        existing = by_account.get(key)
        if existing is None or _is_better_result(result, existing):
            by_account[key] = result

    ranked = list(by_account.values())
    ranked.sort(
        key=lambda item: (
            _to_float(item.get("total_match_score")),
            _to_int(item.get("follower_count")),
        ),
        reverse=True,
    )
    return ranked


def _is_better_result(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    candidate_score = _to_float(candidate.get("total_match_score"))
    current_score = _to_float(current.get("total_match_score"))
    if candidate_score != current_score:
        return candidate_score > current_score

    candidate_followers = _to_int(candidate.get("follower_count"))
    current_followers = _to_int(current.get("follower_count"))
    return candidate_followers > current_followers


def _to_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def _extract_latency_ms(meta: dict[str, Any] | None) -> float:
    if not isinstance(meta, dict):
        return 0.0
    raw = meta.get("latency_ms")
    return _to_float(raw)
