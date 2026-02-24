"""
AI post analysis service.

This module generates narrative analysis only. It does not compute
or alter deterministic scoring metrics.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, cast

from backend.app.ai.llm_client import LLMClient, LLMClientError


def _error_response() -> Dict[str, Any]:
    """Return the required structured error payload."""
    return {
        "status": "ERROR",
        "summary": "",
        "drivers": [],
        "recommendations": [],
    }


def _extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Parse a JSON object from model output.

    Accepts plain JSON or fenced markdown containing JSON.
    Returns None if parsing fails or payload is not an object.
    """
    text = (raw_text or "").strip()
    if not text:
        return None

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()

    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None
    return cast(Dict[str, Any], parsed)


def _validate_driver(item: Any) -> bool:
    """Validate one driver item against required schema."""
    if not isinstance(item, dict):
        return False
    required_keys = {"id", "label", "type", "explanation"}
    if set(item.keys()) != required_keys:
        return False
    if not isinstance(item.get("id"), str):
        return False
    if not isinstance(item.get("label"), str):
        return False
    if item.get("type") not in {"POSITIVE", "LIMITING"}:
        return False
    if not isinstance(item.get("explanation"), str):
        return False
    return True


def _validate_recommendation(item: Any) -> bool:
    """Validate one recommendation item against required schema."""
    if not isinstance(item, dict):
        return False
    required_keys = {"id", "text", "impact_level"}
    if set(item.keys()) != required_keys:
        return False
    if not isinstance(item.get("id"), str):
        return False
    if not isinstance(item.get("text"), str):
        return False
    if item.get("impact_level") not in {"HIGH", "MEDIUM", "LOW"}:
        return False
    return True


def _validate_response_schema(payload: Dict[str, Any]) -> bool:
    """
    Validate strict response schema from AI.

    Required top-level keys:
    - summary: str
    - drivers: list[driver]
    - recommendations: list[recommendation]
    """
    required_top_keys = {"summary", "drivers", "recommendations"}
    if set(payload.keys()) != required_top_keys:
        return False

    if not isinstance(payload.get("summary"), str):
        return False
    if not isinstance(payload.get("drivers"), list):
        return False
    if not isinstance(payload.get("recommendations"), list):
        return False

    drivers = cast(List[Any], payload["drivers"])
    recommendations = cast(List[Any], payload["recommendations"])

    if len(drivers) < 1 or len(recommendations) < 1:
        return False

    if not all(_validate_driver(item) for item in drivers):
        return False
    if not all(_validate_recommendation(item) for item in recommendations):
        return False

    return True


def _build_prompt(
    post_metadata: Dict[str, Any],
    metrics: Dict[str, Any],
    signals: Dict[str, Any],
    benchmarks: Dict[str, Any],
    tier_name: str,
) -> Dict[str, str]:
    """Build strict prompt requesting JSON-only narrative analysis."""
    system_prompt = (
        "You are an analytics explanation assistant.\n"
        "You must only explain provided deterministic metrics/signals.\n"
        "Never compute numeric scores.\n"
        "Never alter numeric values.\n"
        "Never invent missing metrics.\n"
        "Return ONLY valid JSON.\n"
        "Return STRICT JSON only, with no markdown and no extra text.\n"
        "Do not wrap the JSON in markdown or code fences.\n"
        "Do not include explanations outside the JSON object.\n"
        "If a metric or signal is not present in the input JSON, you must not reference it.\n"
        "Do not infer missing values.\n"
        "Reference exact numeric values from metrics and signals when explaining performance.\n"
        "Do not generate new numeric values.\n"
        "You are allowed to reference the provided 'ai_content_score' and 'ai_content_band' if present in signals.\n"
        "You must treat 'ai_content_score' as a fixed deterministic value.\n"
        "You must never recompute, approximate, or suggest a different numeric score.\n"
        "You must not suggest that the score should be changed.\n"
        "You must not generate any new numeric values.\n"
        "You must only explain WHY the score may be high or low using the provided metrics and signals.\n"
        "If ai_content_score is present, explanations must be consistent with it.\n"
        "Do not include any keys other than: summary, drivers, recommendations.\n"
        "Driver 'type' must be exactly POSITIVE or LIMITING.\n"
        "Recommendation 'impact_level' must be exactly HIGH, MEDIUM, or LOW."
    )

    user_payload = {
        "tier_name": tier_name,
        "post_metadata": post_metadata,
        "metrics": metrics,
        "signals": signals,
        "benchmarks": benchmarks,
        "response_schema": {
            "summary": "string",
            "drivers": [
                {
                    "id": "string",
                    "label": "string",
                    "type": "POSITIVE | LIMITING",
                    "explanation": "string",
                }
            ],
            "recommendations": [
                {
                    "id": "string",
                    "text": "string",
                    "impact_level": "HIGH | MEDIUM | LOW",
                }
            ],
        },
    }

    return {
        "system": system_prompt,
        "user": json.dumps(user_payload, ensure_ascii=True),
    }


def generate_post_ai_analysis(
    post_metadata: dict,
    metrics: dict,
    signals: dict,
    benchmarks: dict,
    tier_name: str
) -> dict:
    """
    Generate AI narrative analysis for a post from deterministic inputs.

    This function does not compute scoring values. It only requests narrative
    interpretation of provided deterministic data and validates strict JSON.
    """
    prompt = _build_prompt(
        post_metadata=cast(Dict[str, Any], post_metadata or {}),
        metrics=cast(Dict[str, Any], metrics or {}),
        signals=cast(Dict[str, Any], signals or {}),
        benchmarks=cast(Dict[str, Any], benchmarks or {}),
        tier_name=tier_name or "",
    )

    llm = LLMClient(model_name="gpt-4o-mini", temperature=0.2)
    try:
        raw = llm.generate(prompt)
    except (LLMClientError, Exception):
        return _error_response()

    parsed = _extract_json_object(raw or "")
    if parsed is None or not _validate_response_schema(parsed):
        return _error_response()

    return {
        "status": "READY",
        "summary": parsed["summary"],
        "drivers": parsed["drivers"],
        "recommendations": parsed["recommendations"],
    }
