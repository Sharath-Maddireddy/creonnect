"""OpenAI-compatible function tool schemas for brand discovery tool-calling."""

from __future__ import annotations

from typing import Any

MAX_TOOL_CALLS: int = 5


BRAND_DISCOVERY_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_creator_pool",
            "description": "Search the creator pool by niche, follower range, and engagement criteria. Returns ranked creator profiles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "niche": {
                        "type": "string",
                        "description": "Creator niche/category filter, e.g. fitness, fashion, tech.",
                    },
                    "min_followers": {
                        "type": "integer",
                        "description": "Minimum follower count.",
                    },
                    "max_followers": {
                        "type": "integer",
                        "description": "Maximum follower count.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of creators to return.",
                        "default": 20,
                        "maximum": 50,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_lookalike_creators",
            "description": "Find creators similar to a reference creator using semantic vector similarity. Use when the brand references a specific creator handle or wants 'creators like X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Reference creator account id/handle.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lookalikes to return.",
                        "default": 5,
                        "maximum": 10,
                    },
                },
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "score_creator_brand_fit",
            "description": "Score how well a specific creator matches a brand's requirements. Returns a 0-100 match score with sub-scores for niche fit, engagement, brand safety, content quality, and audience size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Creator account id to score.",
                    },
                    "brand_niche": {
                        "type": "string",
                        "description": "Brand niche/category used for fit scoring.",
                    },
                    "min_followers": {
                        "type": "integer",
                        "description": "Optional minimum follower threshold.",
                    },
                    "max_followers": {
                        "type": "integer",
                        "description": "Optional maximum follower threshold.",
                    },
                    "min_engagement_rate": {
                        "type": "number",
                        "description": "Optional minimum engagement rate threshold (0-1).",
                    },
                },
                "required": ["account_id", "brand_niche"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_creator_analysis",
            "description": "Retrieve the full analysis profile for a specific creator including engagement metrics, content analysis, brand safety scores, and audience insights. Use for drill-down when a brand asks 'tell me more about creator X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Creator account id to retrieve analysis for.",
                    },
                },
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_brand_clarification",
            "description": "Ask the brand a targeted clarifying question when their brief is ambiguous. Use at most once per request. Returns the brand's answer for use in subsequent tool calls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Clarifying question to ask the brand.",
                    },
                    "suggested_options": {
                        "type": "array",
                        "description": "Optional suggested answer choices to speed up clarification.",
                        "items": {
                            "type": "string",
                        },
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_outreach_brief",
            "description": "Generate a personalised outreach message draft for a specific creator. This produces a DRAFT only - nothing is sent without brand confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Creator account id for the outreach draft.",
                    },
                    "campaign_goal": {
                        "type": "string",
                        "description": "Primary campaign goal to position in outreach.",
                    },
                    "brand_tone": {
                        "type": "string",
                        "description": "Optional tone hint, e.g. professional, casual, playful.",
                    },
                    "deliverables": {
                        "type": "array",
                        "description": "Optional list of requested deliverables.",
                        "items": {
                            "type": "string",
                        },
                    },
                },
                "required": ["account_id", "campaign_goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_content_brief",
            "description": "Generate a structured content creation brief tailored to the creator's posting style and the brand's key messages. Produces a DRAFT only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Creator account id for the brief.",
                    },
                    "brand_name": {
                        "type": "string",
                        "description": "Brand name for contextualized messaging.",
                    },
                    "key_messages": {
                        "type": "array",
                        "description": "Core campaign messages that must appear in the brief.",
                        "items": {
                            "type": "string",
                        },
                    },
                    "content_format": {
                        "type": "string",
                        "description": "Optional content format preference.",
                        "enum": ["REEL", "IMAGE", "STORY", "CAROUSEL"],
                    },
                },
                "required": ["account_id", "brand_name", "key_messages"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_campaign_cost",
            "description": "Estimate collaboration cost range based on creator follower count, engagement rate, and deliverable type. Returns min/max cost range in USD.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Creator account id for cost estimation.",
                    },
                    "deliverable_type": {
                        "type": "string",
                        "description": "Deliverable type for pricing heuristic.",
                        "enum": ["REEL", "IMAGE", "STORY", "CAROUSEL", "PACKAGE"],
                    },
                    "deliverable_count": {
                        "type": "integer",
                        "description": "Number of deliverables requested.",
                        "default": 1,
                    },
                },
                "required": ["account_id", "deliverable_type"],
            },
        },
    },
]
