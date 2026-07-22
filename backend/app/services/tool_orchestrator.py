"""Tool orchestrator for brand-side tool-calling dispatch and audit logging."""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.ai.llm_client import LLMClient
from backend.app.ai.prompts import format_user_json_block, format_user_text_block
from backend.app.domain.brand_models import BrandProfile
from backend.app.domain.tool_response import ToolResponse, ToolResponseMeta
from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import AccountAnalysisResult, CreatorDiscoveryMeta, CreatorVector
from backend.app.services.creator_pool_service import find_lookalikes, query_creator_pool
from backend.app.utils.logger import logger


class ToolOrchestrator:
    """Central tool dispatch layer for LLM tool-use requests."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._shared_llm = llm_client or LLMClient()
        self._llm_profiles: dict[tuple[float, int], LLMClient] = {}

    def _get_llm_client(self, *, temperature: float | None = None, max_tokens: int | None = None) -> LLMClient:
        if temperature is None and max_tokens is None:
            return self._shared_llm
        temp = float(temperature if temperature is not None else 0.7)
        tokens = int(max_tokens if max_tokens is not None else 800)
        key = (temp, tokens)
        client = self._llm_profiles.get(key)
        if client is None:
            client = LLMClient(temperature=temp, max_tokens=tokens)
            self._llm_profiles[key] = client
        return client
    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResponse:
        """Execute one tool call and return a standardized response envelope."""
        started_at = time.perf_counter()
        response: ToolResponse
        safe_args = arguments if isinstance(arguments, dict) else {}

        try:
            if not isinstance(tool_name, str) or not tool_name.strip():
                response = ToolResponse.error(
                    tool="unknown",
                    message="Invalid tool name.",
                )
            elif not isinstance(arguments, dict):
                response = ToolResponse.error(
                    tool=tool_name,
                    message="Invalid arguments payload; expected object.",
                )
            else:
                normalized_tool = tool_name.strip()
                _HANDLERS = {
                    "search_creator_pool": self._search_creator_pool,
                    "find_lookalike_creators": self._find_lookalike_creators,
                    "score_creator_brand_fit": self._score_creator_brand_fit,
                    "get_creator_analysis": self._get_creator_analysis,
                    "ask_brand_clarification": self._ask_brand_clarification,
                    "generate_outreach_brief": self._generate_outreach_brief,
                    "generate_content_brief": self._generate_content_brief,
                    "estimate_campaign_cost": self._estimate_campaign_cost,
                    # ── Creo Intelligence tools ──
                    "plan_campaign": self._plan_campaign,
                    "review_campaign_results": self._review_campaign_results,
                    "suggest_budget_allocation": self._suggest_budget_allocation,
                    "benchmark_campaign_performance": self._benchmark_campaign_performance,
                }
                handler = _HANDLERS.get(normalized_tool)
                if handler is not None:
                    response = handler(arguments)
                else:
                    response = ToolResponse.error(
                        tool=normalized_tool,
                        message=f"Unknown tool: {normalized_tool}",
                    )
        except Exception as exc:  # noqa: BLE001
            response = ToolResponse.error(
                tool=tool_name if isinstance(tool_name, str) and tool_name else "unknown",
                message=f"Tool execution failed: {exc}",
            )

        latency_ms = (time.perf_counter() - started_at) * 1000.0
        response.meta = self._merge_meta(response.meta, ToolResponseMeta(latency_ms=latency_ms))

        logger.info(
            "[ToolOrchestrator] tool=%s params=%s latency_ms=%.0f success=%s",
            tool_name,
            self._redact_embeddings(safe_args),
            latency_ms,
            response.success,
        )
        return response

    def _search_creator_pool(self, arguments: dict[str, Any]) -> ToolResponse:
        niche = self._as_optional_string(arguments.get("niche"), "niche")
        min_followers = self._as_optional_int(arguments.get("min_followers"), "min_followers")
        max_followers = self._as_optional_int(arguments.get("max_followers"), "max_followers")
        limit = self._as_optional_int(arguments.get("limit"), "limit")

        if err := self._check_sentinel(niche, "search_creator_pool"): return err
        if err := self._check_sentinel(min_followers, "search_creator_pool"): return err
        if err := self._check_sentinel(max_followers, "search_creator_pool"): return err
        if err := self._check_sentinel(limit, "search_creator_pool"): return err

        min_value = min_followers if isinstance(min_followers, int) else None
        max_value = max_followers if isinstance(max_followers, int) else None
        limit_value = 20 if limit is None else limit
        if limit_value is not None and limit_value > 50:
            return ToolResponse.error("search_creator_pool", "limit must be <= 50.")
        if min_value is not None and max_value is not None and min_value > max_value:
            return ToolResponse.error("search_creator_pool", "min_followers cannot be greater than max_followers.")

        creators = query_creator_pool(
            niche=niche if isinstance(niche, str) else None,
            min_followers=min_value,
            max_followers=max_value,
            limit=limit_value,
        )
        return ToolResponse.ok(
            tool="search_creator_pool",
            data=creators,
            message=f"Found {len(creators)} creator(s).",
            ui={"layout": "card_grid"},
            meta=ToolResponseMeta(latency_ms=0.0, result_count=len(creators)),
        )

    def _find_lookalike_creators(self, arguments: dict[str, Any]) -> ToolResponse:
        account_id = self._as_required_string(arguments.get("account_id"), "account_id")
        if err := self._check_sentinel(account_id, "find_lookalike_creators"): return err

        limit = self._as_optional_int(arguments.get("limit"), "limit")
        if err := self._check_sentinel(limit, "find_lookalike_creators"): return err
        limit_value = 5 if limit is None else limit
        if limit_value is not None and limit_value > 10:
            return ToolResponse.error("find_lookalike_creators", "limit must be <= 10.")

        lookalikes = find_lookalikes(account_id, k=limit_value)
        if lookalikes is None:
            return ToolResponse.error(
                tool="find_lookalike_creators",
                message=f"Creator '{account_id}' not found.",
                meta=ToolResponseMeta(latency_ms=0.0, result_count=0),
            )

        return ToolResponse.ok(
            tool="find_lookalike_creators",
            data=lookalikes,
            message=f"Found {len(lookalikes)} lookalike creator(s).",
            ui={"layout": "card_grid"},
            meta=ToolResponseMeta(latency_ms=0.0, result_count=len(lookalikes)),
        )

    def _score_creator_brand_fit(self, arguments: dict[str, Any]) -> ToolResponse:
        account_id = self._as_required_string(arguments.get("account_id"), "account_id")
        if err := self._check_sentinel(account_id, "score_creator_brand_fit"): return err

        brand_niche = self._as_required_string(arguments.get("brand_niche"), "brand_niche")
        if err := self._check_sentinel(brand_niche, "score_creator_brand_fit"): return err

        min_followers = self._as_optional_int(arguments.get("min_followers"), "min_followers")
        max_followers = self._as_optional_int(arguments.get("max_followers"), "max_followers")
        min_engagement_rate = self._as_optional_float(arguments.get("min_engagement_rate"), "min_engagement_rate")

        for value in (min_followers, max_followers, min_engagement_rate):
            if err := self._check_sentinel(value, "score_creator_brand_fit"): return err

        min_value = min_followers if isinstance(min_followers, int) else None
        max_value = max_followers if isinstance(max_followers, int) else None
        if min_value is not None and max_value is not None and min_value > max_value:
            return ToolResponse.error("score_creator_brand_fit", "min_followers cannot be greater than max_followers.")

        brand_profile = BrandProfile(
            brand_name="tool_request",
            niche=brand_niche,
            min_followers=min_value,
            max_followers=max_value,
            min_engagement_rate=min_engagement_rate if isinstance(min_engagement_rate, float) else None,
        )

        creator = self._load_creator_by_account_id(account_id)
        if creator is None:
            return ToolResponse.error("score_creator_brand_fit", f"Creator '{account_id}' not found.")

        score = score_creator_against_brand(
            account_id=account_id,
            brand=brand_profile,
            creator_dominant_category=self._as_string_or_none(creator.get("creator_dominant_category")),
            creator_embedding=creator.get("embedding") if isinstance(creator.get("embedding"), list) else None,
            follower_count=self._as_int_or_none(creator.get("follower_count")),
            avg_views=int(creator.get("avg_views") or 0),
            avg_likes=int(creator.get("avg_likes") or 0),
            avg_comments=int(creator.get("avg_comments") or 0),
            ahs_score=self._as_float_or_none(creator.get("ahs_score")),
            predicted_engagement_rate=self._as_float_or_none(creator.get("predicted_engagement_rate")),
            visual_quality_score_total=float(creator.get("avg_visual_quality_score") or 0.0),
            brand_safety_score_total_0_50=float(creator.get("avg_brand_safety_score") or 50.0),
            adult_content_detected=creator.get("adult_content_detected") if isinstance(creator.get("adult_content_detected"), bool) else None,
        )

        return ToolResponse.ok(
            tool="score_creator_brand_fit",
            data=score.model_dump(mode="python"),
            message="Computed creator-brand fit score.",
            ui={"layout": "score_card"},
            meta=ToolResponseMeta(latency_ms=0.0, result_count=1),
        )

    def _get_creator_analysis(self, arguments: dict[str, Any]) -> ToolResponse:
        account_id = self._as_required_string(arguments.get("account_id"), "account_id")
        if err := self._check_sentinel(account_id, "get_creator_analysis"): return err

        session_factory = get_sync_sessionmaker()
        try:
            with session_factory() as session:
                row = session.execute(
                    select(AccountAnalysisResult)
                    .where(AccountAnalysisResult.account_id == account_id)
                    .order_by(AccountAnalysisResult.updated_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            return ToolResponse.error("get_creator_analysis", f"Failed to query analysis store: {exc}")

        if row is None or not isinstance(row.result_json, dict):
            return ToolResponse.error("get_creator_analysis", f"No analysis found for creator '{account_id}'.")

        return ToolResponse.ok(
            tool="get_creator_analysis",
            data=row.result_json,
            message="Retrieved creator analysis profile.",
            ui={"layout": "profile_detail"},
            meta=ToolResponseMeta(latency_ms=0.0, result_count=1),
        )

    def _ask_brand_clarification(self, arguments: dict[str, Any]) -> ToolResponse:
        question = self._as_required_string(arguments.get("question"), "question")
        if err := self._check_sentinel(question, "ask_brand_clarification"): return err

        raw_options = arguments.get("suggested_options")
        suggested_options: list[str] | None = None
        if raw_options is not None:
            if not isinstance(raw_options, list) or not all(isinstance(item, str) for item in raw_options):
                return ToolResponse.error("ask_brand_clarification", "suggested_options must be an array of strings.")
            suggested_options = [item.strip() for item in raw_options if item.strip()]

        return ToolResponse.ok(
            tool="ask_brand_clarification",
            data={
                "question": question,
                "suggested_options": suggested_options or [],
            },
            message="Clarification required.",
            ui={"layout": "clarification_chips"},
            meta=ToolResponseMeta(latency_ms=0.0, result_count=1),
        )
    def _generate_outreach_brief(self, arguments: dict[str, Any]) -> ToolResponse:
        account_id = self._as_required_string(arguments.get("account_id"), "account_id")
        if err := self._check_sentinel(account_id, "generate_outreach_brief"): return err

        campaign_goal = self._as_required_string(arguments.get("campaign_goal"), "campaign_goal")
        if err := self._check_sentinel(campaign_goal, "generate_outreach_brief"): return err

        brand_tone = self._as_optional_string(arguments.get("brand_tone"), "brand_tone")
        if err := self._check_sentinel(brand_tone, "generate_outreach_brief"): return err

        deliverables = self._as_optional_string_list(arguments.get("deliverables"), "deliverables")
        if err := self._check_sentinel(deliverables, "generate_outreach_brief"): return err

        analysis = self._load_creator_analysis_by_account_id(account_id)
        if analysis is None:
            return ToolResponse.error("generate_outreach_brief", f"No analysis found for creator '{account_id}'.")

        compact_analysis = self._summarize_analysis_for_prompt(analysis)
        outreach_prompt = {
            "system": (
                "You create concise brand outreach drafts for creators. "
                "Return plain text only. This is a draft and must mention that brand confirmation is required before sending."
            ),
            "user": (
                "Creator account (data): " + format_user_text_block(account_id) + "\n"
                "Creator analysis JSON (data): " + format_user_json_block(compact_analysis) + "\n"
                "Campaign goal (data): " + format_user_text_block(campaign_goal) + "\n"
                "Brand tone (data): " + format_user_text_block(brand_tone or "neutral") + "\n"
                "Deliverables JSON (data): " + format_user_json_block(deliverables or []) + "\n\n"
                "Write one personalized outreach message draft. Keep it under 180 words."
            ),
        }

        draft_text = self._get_llm_client().generate(outreach_prompt)
        if not isinstance(draft_text, str) or not draft_text.strip():
            return ToolResponse.error("generate_outreach_brief", "Failed to generate outreach draft.")

        return ToolResponse.ok(
            tool="generate_outreach_brief",
            data={
                "account_id": account_id,
                "draft_message": draft_text.strip(),
                "campaign_goal": campaign_goal,
                "brand_tone": brand_tone,
                "deliverables": deliverables or [],
                "draft_only": True,
            },
            message="Generated outreach draft.",
            ui={"layout": "draft_message", "requires_confirmation": True},
            meta=ToolResponseMeta(latency_ms=0.0, result_count=1),
        )

    def _generate_content_brief(self, arguments: dict[str, Any]) -> ToolResponse:
        account_id = self._as_required_string(arguments.get("account_id"), "account_id")
        if err := self._check_sentinel(account_id, "generate_content_brief"): return err

        brand_name = self._as_required_string(arguments.get("brand_name"), "brand_name")
        if err := self._check_sentinel(brand_name, "generate_content_brief"): return err

        key_messages = self._as_required_string_list(arguments.get("key_messages"), "key_messages")
        if err := self._check_sentinel(key_messages, "generate_content_brief"): return err

        content_format = self._as_optional_string(arguments.get("content_format"), "content_format")
        if err := self._check_sentinel(content_format, "generate_content_brief"): return err

        allowed_formats = {"REEL", "IMAGE", "STORY", "CAROUSEL"}
        if isinstance(content_format, str):
            content_format = content_format.upper()
            if content_format not in allowed_formats:
                return ToolResponse.error(
                    "generate_content_brief",
                    "content_format must be one of: REEL, IMAGE, STORY, CAROUSEL.",
                )

        analysis = self._load_creator_analysis_by_account_id(account_id)
        if analysis is None:
            return ToolResponse.error("generate_content_brief", f"No analysis found for creator '{account_id}'.")

        compact_analysis = self._summarize_analysis_for_prompt(analysis)
        brief_prompt = {
            "system": (
                "You create structured creator content briefs. "
                "Return valid JSON only with keys: objective, key_messages, content_format, "
                "creative_direction, hashtags, posting_guidelines."
            ),
            "user": (
                "Creator account (data): " + format_user_text_block(account_id) + "\n"
                "Creator analysis JSON (data): " + format_user_json_block(compact_analysis) + "\n"
                "Brand name (data): " + format_user_text_block(brand_name) + "\n"
                "Key messages JSON (data): " + format_user_json_block(key_messages) + "\n"
                "Preferred format (data): " + format_user_text_block(content_format or "Not specified") + "\n\n"
                "Produce a draft content brief aligned to the creator's style and audience. "
                "hashtags must be an array of strings."
            ),
        }

        brief_text = self._get_llm_client().generate(brief_prompt)
        if not isinstance(brief_text, str) or not brief_text.strip():
            return ToolResponse.error("generate_content_brief", "Failed to generate content brief draft.")

        structured_brief = self._extract_json_dict(brief_text)
        if structured_brief is None:
            structured_brief = {
                "objective": "",
                "key_messages": key_messages,
                "content_format": content_format or "REEL",
                "creative_direction": brief_text.strip(),
                "hashtags": [],
                "posting_guidelines": "",
            }

        structured_brief.setdefault("objective", "")
        structured_brief.setdefault("key_messages", key_messages)
        structured_brief.setdefault("content_format", content_format or "REEL")
        structured_brief.setdefault("creative_direction", "")
        structured_brief.setdefault("hashtags", [])
        structured_brief.setdefault("posting_guidelines", "")

        return ToolResponse.ok(
            tool="generate_content_brief",
            data={
                "account_id": account_id,
                "brand_name": brand_name,
                "brief": structured_brief,
                "draft_only": True,
            },
            message="Generated content brief draft.",
            ui={"layout": "content_brief", "requires_confirmation": True},
            meta=ToolResponseMeta(latency_ms=0.0, result_count=1),
        )

    def _estimate_campaign_cost(self, arguments: dict[str, Any]) -> ToolResponse:
        account_id = self._as_required_string(arguments.get("account_id"), "account_id")
        if err := self._check_sentinel(account_id, "estimate_campaign_cost"): return err

        deliverable_type = self._as_required_string(arguments.get("deliverable_type"), "deliverable_type")
        if err := self._check_sentinel(deliverable_type, "estimate_campaign_cost"): return err

        deliverable_type = deliverable_type.upper()
        multipliers = {
            "IMAGE": 1.0,
            "REEL": 2.5,
            "STORY": 0.5,
            "CAROUSEL": 1.5,
            "PACKAGE": 4.0,
        }
        if deliverable_type not in multipliers:
            return ToolResponse.error(
                "estimate_campaign_cost",
                "deliverable_type must be one of: REEL, IMAGE, STORY, CAROUSEL, PACKAGE.",
            )

        deliverable_count = self._as_optional_int(arguments.get("deliverable_count"), "deliverable_count")
        if err := self._check_sentinel(deliverable_count, "estimate_campaign_cost"): return err

        count_value = 1 if deliverable_count is None else deliverable_count
        if count_value <= 0:
            return ToolResponse.error("estimate_campaign_cost", "deliverable_count must be greater than 0.")

        creator = self._load_creator_by_account_id(account_id)
        if creator is None:
            return ToolResponse.error("estimate_campaign_cost", f"Creator '{account_id}' not found.")

        follower_count = max(0, int(creator.get("follower_count") or 0))
        predicted_er = float(creator.get("predicted_engagement_rate") or 0.0)

        image_base = (follower_count / 10_000.0) * 10.0
        estimated = image_base * multipliers[deliverable_type] * float(count_value)

        er_percent = predicted_er * 100.0 if predicted_er <= 1.0 else predicted_er
        if er_percent > 5.0:
            estimated *= 1.3

        min_cost = round(estimated * 0.8, 2)
        max_cost = round(estimated * 1.3, 2)

        return ToolResponse.ok(
            tool="estimate_campaign_cost",
            data={
                "account_id": account_id,
                "deliverable_type": deliverable_type,
                "deliverable_count": count_value,
                "follower_count": follower_count,
                "predicted_engagement_rate": predicted_er,
                "min_cost_usd": min_cost,
                "max_cost_usd": max_cost,
                "currency": "USD",
            },
            message="Estimated campaign cost range.",
            ui={"layout": "cost_estimate"},
            meta=ToolResponseMeta(latency_ms=0.0, result_count=1),
        )

    def _load_creator_analysis_by_account_id(self, account_id: str) -> dict[str, Any] | None:
        session_factory = get_sync_sessionmaker()
        try:
            with session_factory() as session:
                row = session.execute(
                    select(AccountAnalysisResult)
                    .where(AccountAnalysisResult.account_id == account_id)
                    .order_by(AccountAnalysisResult.updated_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
        except SQLAlchemyError:
            return None

        if row is None or not isinstance(row.result_json, dict):
            return None

        return row.result_json
    def _load_creator_by_account_id(self, account_id: str) -> dict[str, Any] | None:
        session_factory = get_sync_sessionmaker()
        try:
            with session_factory() as session:
                row = session.execute(
                    select(CreatorDiscoveryMeta, CreatorVector)
                    .join(CreatorVector, CreatorVector.account_id == CreatorDiscoveryMeta.account_id, isouter=True)
                    .where(CreatorDiscoveryMeta.account_id == account_id)
                    .limit(1)
                ).one_or_none()
        except SQLAlchemyError:
            return None

        if row is None:
            return None

        meta, vector = row
        return {
            "account_id": meta.account_id,
            "creator_dominant_category": meta.creator_dominant_category,
            "follower_count": meta.follower_count,
            "ahs_score": meta.ahs_score,
            "predicted_engagement_rate": meta.predicted_engagement_rate,
            "avg_visual_quality_score": meta.avg_visual_quality_score,
            "avg_brand_safety_score": meta.avg_brand_safety_score,
            "adult_content_detected": meta.adult_content_detected,
            "avg_views": meta.avg_views,
            "avg_likes": meta.avg_likes,
            "avg_comments": meta.avg_comments,
            "embedding": list(vector.embedding) if vector is not None and vector.embedding is not None else None,
        }

    def _merge_meta(self, base_meta: dict[str, Any] | None, override: ToolResponseMeta) -> dict[str, Any]:
        merged = dict(base_meta or {})
        merged.update(override.model_dump(mode="python", exclude_none=True))
        return merged

    def _redact_embeddings(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                if isinstance(key, str) and key.lower() == "embedding":
                    redacted[key] = "[REDACTED]"
                else:
                    redacted[key] = self._redact_embeddings(item)
            return redacted
        if isinstance(value, list):
            return [self._redact_embeddings(item) for item in value]
        return value

    def _summarize_analysis_for_prompt(self, analysis: dict[str, Any], *, max_chars: int = 2500) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "account_id": analysis.get("account_id"),
            "username": analysis.get("username"),
            "creator_dominant_category": analysis.get("creator_dominant_category"),
            "follower_count": analysis.get("follower_count"),
            "predicted_engagement_rate": analysis.get("predicted_engagement_rate"),
            "ahs_score": analysis.get("ahs_score"),
            "avg_brand_safety_score": analysis.get("avg_brand_safety_score"),
            "avg_visual_quality_score": analysis.get("avg_visual_quality_score"),
            "avg_views": analysis.get("avg_views"),
            "avg_likes": analysis.get("avg_likes"),
            "avg_comments": analysis.get("avg_comments"),
            "posts_per_week": analysis.get("posts_per_week"),
            "bio": analysis.get("bio"),
            "niche_tags": analysis.get("niche_tags"),
        }

        for key in (
            "profile",
            "overview",
            "audience_summary",
            "content_summary",
            "brand_safety_summary",
            "engagement_summary",
        ):
            value = analysis.get(key)
            if value is not None:
                summary[key] = value

        serialized = json.dumps(summary, ensure_ascii=True, default=str)
        if len(serialized) <= max_chars:
            return summary

        return {
            "account_id": summary.get("account_id"),
            "username": summary.get("username"),
            "creator_dominant_category": summary.get("creator_dominant_category"),
            "follower_count": summary.get("follower_count"),
            "predicted_engagement_rate": summary.get("predicted_engagement_rate"),
            "ahs_score": summary.get("ahs_score"),
            "bio": summary.get("bio"),
            "niche_tags": summary.get("niche_tags"),
        }

    def _check_sentinel(self, value: Any, tool_name: str) -> "ToolResponse | None":
        "Return an error ToolResponse if value is an __error__ sentinel, else None."
        if isinstance(value, str) and value.startswith("__error__"):
            return ToolResponse.error(tool_name, value.removeprefix("__error__"))
        return None

    def _as_required_string(self, value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            return f"__error__{field_name} must be a non-empty string."
        return value.strip()

    def _as_optional_string(self, value: Any, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return f"__error__{field_name} must be a string when provided."
        text = value.strip()
        return text or None

    def _as_optional_int(self, value: Any, field_name: str) -> int | None | str:
        if value is None:
            return None
        if isinstance(value, bool):
            return f"__error__{field_name} must be an integer."
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return f"__error__{field_name} must be an integer."

    def _as_optional_float(self, value: Any, field_name: str) -> float | None | str:
        if value is None:
            return None
        if isinstance(value, bool):
            return f"__error__{field_name} must be a number."
        if isinstance(value, (int, float)):
            return float(value)
        return f"__error__{field_name} must be a number."

    def _as_optional_string_list(self, value: Any, field_name: str) -> list[str] | None | str:
        if value is None:
            return None
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return f"__error__{field_name} must be an array of strings."
        return [item.strip() for item in value if item.strip()]

    def _as_required_string_list(self, value: Any, field_name: str) -> list[str] | str:
        parsed = self._as_optional_string_list(value, field_name)
        if parsed is None:
            return f"__error__{field_name} must be a non-empty array of strings."
        if isinstance(parsed, str):
            return parsed
        if not parsed:
            return f"__error__{field_name} must be a non-empty array of strings."
        return parsed

    def _extract_json_dict(self, value: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = value.find("{")
        end = value.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            parsed = json.loads(value[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    def _as_string_or_none(self, value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return None

    def _as_int_or_none(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None

    def _as_float_or_none(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return None

    # ── Creo Intelligence LLM-backed tools ────────────────────────────────────
    # These tools call the LLM to generate strategic content (plans, reviews,
    # budget allocations, benchmarks) instead of querying the database.
    def _plan_campaign(self, arguments):  # type: ignore[override]
        """Generate a structured campaign plan via LLM."""
        from backend.app.domain.tool_response import ToolResponse as TR

        brand_name = self._as_optional_string(arguments.get("brand_name"), "brand_name")
        campaign_goal = self._as_optional_string(arguments.get("campaign_goal"), "campaign_goal")
        if err := self._check_sentinel(brand_name, "plan_campaign"):
            return err
        if err := self._check_sentinel(campaign_goal, "plan_campaign"):
            return err
        if not isinstance(campaign_goal, str) or not campaign_goal:
            return TR.error("plan_campaign", "campaign_goal is required.")

        budget_inr = self._as_float_or_none(arguments.get("budget_inr"))
        timeline_weeks = self._as_int_or_none(arguments.get("timeline_weeks"))
        niche = self._as_string_or_none(arguments.get("niche"))
        content_type = self._as_string_or_none(arguments.get("content_type"))
        target_audience = self._as_string_or_none(arguments.get("target_audience"))

        parts = []
        if isinstance(brand_name, str):
            parts.append("Brand (data): " + format_user_text_block(brand_name))
        parts.append("Campaign Goal (data): " + format_user_text_block(campaign_goal))
        if budget_inr is not None:
            parts.append("Budget INR: " + f"{budget_inr:,.0f}")
        if timeline_weeks is not None:
            parts.append("Timeline Weeks: " + str(timeline_weeks))
        if niche:
            parts.append("Niche (data): " + format_user_text_block(niche))
        if content_type:
            parts.append("Content Format (data): " + format_user_text_block(content_type))
        if target_audience:
            parts.append("Target Audience (data): " + format_user_text_block(target_audience))

        prompt = {
            "system": (
                "You are a senior influencer marketing strategist. Generate a concise, structured "
                "influencer campaign plan. Include: campaign objective, recommended creator tiers "
                "(nano/micro/mid-tier/macro), content format strategy, posting schedule, KPIs to "
                "track, and 3 actionable next steps. Be specific and practical. Use INR for budgets."
            ),
            "user": "\n".join(parts),
        }
        try:
            plan_text = self._get_llm_client(temperature=0.3, max_tokens=800).generate(prompt)
            return TR.ok(
                tool="plan_campaign",
                data={"plan": plan_text, "brand_name": brand_name, "campaign_goal": campaign_goal},
                message="Campaign plan generated.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[ToolOrchestrator] plan_campaign LLM error: %s", exc)
            return TR.error("plan_campaign", "Failed to generate plan: " + str(exc))

    def _review_campaign_results(self, arguments):  # type: ignore[override]
        """Analyze campaign performance metrics via LLM."""
        from backend.app.domain.tool_response import ToolResponse as TR

        campaign_name = self._as_optional_string(arguments.get("campaign_name"), "campaign_name")
        if err := self._check_sentinel(campaign_name, "review_campaign_results"):
            return err
        if not isinstance(campaign_name, str) or not campaign_name:
            return TR.error("review_campaign_results", "campaign_name is required.")

        metric_parts = ["Campaign (data): " + format_user_text_block(campaign_name)]
        for field, label in [
            ("total_reach", "Total Reach"),
            ("total_impressions", "Total Impressions"),
            ("total_engagement", "Total Engagements"),
            ("creator_count", "Creator Count"),
            ("conversions", "Conversions"),
        ]:
            val = self._as_int_or_none(arguments.get(field))
            if val is not None:
                metric_parts.append(label + ": " + f"{val:,}")
        budget_spent = self._as_float_or_none(arguments.get("budget_spent_inr"))
        if budget_spent is not None:
            metric_parts.append("Budget Spent INR: " + f"{budget_spent:,.0f}")
        for field, label in [("campaign_goal", "Campaign Goal"), ("niche", "Niche")]:
            val = self._as_string_or_none(arguments.get(field))
            if val:
                metric_parts.append(label + " (data): " + format_user_text_block(val))

        prompt = {
            "system": (
                "You are a senior influencer marketing analyst. Review the campaign metrics provided "
                "and give a structured performance analysis. Include: overall performance rating "
                "(Excellent/Good/Average/Below Average), what worked well, what underperformed, "
                "key metrics assessment, and 3 concrete improvement recommendations for the next campaign."
            ),
            "user": "\n".join(metric_parts),
        }
        try:
            review_text = self._get_llm_client(temperature=0.2, max_tokens=700).generate(prompt)
            return TR.ok(
                tool="review_campaign_results",
                data={"review": review_text, "campaign_name": campaign_name},
                message="Campaign review completed.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[ToolOrchestrator] review_campaign_results LLM error: %s", exc)
            return TR.error("review_campaign_results", "Failed to generate review: " + str(exc))

    def _suggest_budget_allocation(self, arguments):  # type: ignore[override]
        """Recommend budget split across creator tiers via LLM."""
        from backend.app.domain.tool_response import ToolResponse as TR

        total_budget = self._as_float_or_none(arguments.get("total_budget_inr"))
        campaign_goal = self._as_optional_string(arguments.get("campaign_goal"), "campaign_goal")
        if err := self._check_sentinel(campaign_goal, "suggest_budget_allocation"):
            return err
        if total_budget is None or total_budget <= 0:
            return TR.error("suggest_budget_allocation", "total_budget_inr must be a positive number.")
        if not isinstance(campaign_goal, str) or not campaign_goal:
            return TR.error("suggest_budget_allocation", "campaign_goal is required.")

        creator_count = self._as_int_or_none(arguments.get("creator_count"))
        niche = self._as_string_or_none(arguments.get("niche"))
        preferred_tiers_raw = arguments.get("preferred_tiers")
        preferred_tiers = (
            [t for t in preferred_tiers_raw if isinstance(t, str)]
            if isinstance(preferred_tiers_raw, list)
            else None
        )

        alloc_parts = [
            "Total Budget INR: " + f"{total_budget:,.0f}",
            "Campaign Goal (data): " + format_user_text_block(campaign_goal),
        ]
        if creator_count is not None:
            alloc_parts.append("Number of Creators: " + str(creator_count))
        if niche:
            alloc_parts.append("Niche (data): " + format_user_text_block(niche))
        if preferred_tiers:
            alloc_parts.append("Preferred Tiers JSON (data): " + format_user_json_block(preferred_tiers))

        prompt = {
            "system": (
                "You are a senior influencer marketing strategist specializing in budget optimization. "
                "Recommend how to allocate the influencer marketing budget across creator tiers. "
                "Provide: tier breakdown with % and INR amounts, rationale for each tier, expected "
                "reach and engagement per tier, and a recommended split between content creation fees "
                "and paid amplification. Be specific with numbers."
            ),
            "user": "\n".join(alloc_parts),
        }
        try:
            allocation_text = self._get_llm_client(temperature=0.2, max_tokens=600).generate(prompt)
            return TR.ok(
                tool="suggest_budget_allocation",
                data={
                    "allocation": allocation_text,
                    "total_budget_inr": total_budget,
                    "campaign_goal": campaign_goal,
                },
                message="Budget allocation generated.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[ToolOrchestrator] suggest_budget_allocation LLM error: %s", exc)
            return TR.error("suggest_budget_allocation", "Failed to generate allocation: " + str(exc))

    def _benchmark_campaign_performance(self, arguments):  # type: ignore[override]
        """Compare campaign metrics to industry benchmarks via LLM."""
        from backend.app.domain.tool_response import ToolResponse as TR

        niche = self._as_optional_string(arguments.get("niche"), "niche")
        if err := self._check_sentinel(niche, "benchmark_campaign_performance"):
            return err
        if not isinstance(niche, str) or not niche:
            return TR.error("benchmark_campaign_performance", "niche is required.")

        bench_parts = ["Niche (data): " + format_user_text_block(niche)]
        engagement_rate = self._as_float_or_none(arguments.get("engagement_rate"))
        if engagement_rate is not None:
            bench_parts.append("Engagement Rate: " + f"{engagement_rate * 100:.2f}%")
        reach_per_post = self._as_int_or_none(arguments.get("reach_per_post"))
        if reach_per_post is not None:
            bench_parts.append("Avg Reach per Post: " + f"{reach_per_post:,}")
        cpe = self._as_float_or_none(arguments.get("cost_per_engagement_inr"))
        if cpe is not None:
            bench_parts.append("Cost per Engagement INR: " + f"{cpe:.2f}")
        cpm = self._as_float_or_none(arguments.get("cost_per_reach_inr"))
        if cpm is not None:
            bench_parts.append("CPM INR: " + f"{cpm:.2f}")
        conversion_rate = self._as_float_or_none(arguments.get("conversion_rate"))
        if conversion_rate is not None:
            bench_parts.append("Conversion Rate: " + f"{conversion_rate * 100:.2f}%")

        prompt = {
            "system": (
                "You are an influencer marketing analytics expert with deep knowledge of Indian "
                "market benchmarks. Compare the provided campaign metrics against typical industry "
                "benchmarks for the given niche in India. Provide: performance grade for each metric "
                "(Above/At/Below benchmark), the benchmark reference values you are comparing against, "
                "an overall campaign performance score (A/B/C/D), and 3 specific improvement actions "
                "to reach benchmark levels."
            ),
            "user": "\n".join(bench_parts),
        }
        try:
            benchmark_text = self._get_llm_client(temperature=0.1, max_tokens=700).generate(prompt)
            return TR.ok(
                tool="benchmark_campaign_performance",
                data={"benchmark_analysis": benchmark_text, "niche": niche},
                message="Benchmark analysis completed.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[ToolOrchestrator] benchmark_campaign_performance LLM error: %s", exc)
            return TR.error("benchmark_campaign_performance", "Failed to benchmark: " + str(exc))
