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
    {
        "type": "function",
        "function": {
            "name": "plan_campaign",
            "description": (
                "Generate a structured influencer campaign plan covering goals, timeline, "
                "creator tier recommendations, content formats, and KPIs. Use when the brand "
                "wants to plan or kick off a new campaign."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "brand_name": {
                        "type": "string",
                        "description": "Name of the brand running the campaign.",
                    },
                    "campaign_goal": {
                        "type": "string",
                        "description": "Primary campaign objective, e.g. product launch, brand awareness, sales.",
                    },
                    "budget_inr": {
                        "type": "number",
                        "description": "Total campaign budget in INR.",
                    },
                    "timeline_weeks": {
                        "type": "integer",
                        "description": "Campaign duration in weeks.",
                    },
                    "niche": {
                        "type": "string",
                        "description": "Creator niche/category, e.g. fitness, beauty, tech.",
                    },
                    "content_type": {
                        "type": "string",
                        "description": "Preferred content format.",
                        "enum": ["REEL", "IMAGE", "STORY", "CAROUSEL", "MIXED"],
                    },
                    "target_audience": {
                        "type": "string",
                        "description": "Brief description of the target audience.",
                    },
                },
                "required": ["brand_name", "campaign_goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "review_campaign_results",
            "description": (
                "Analyze and summarize the performance of an influencer campaign. "
                "Identifies what worked, what didn't, and provides actionable recommendations. "
                "Use when the brand shares campaign metrics or asks for performance review."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "campaign_name": {
                        "type": "string",
                        "description": "Name or description of the campaign.",
                    },
                    "total_reach": {
                        "type": "integer",
                        "description": "Total combined reach across all creators.",
                    },
                    "total_impressions": {
                        "type": "integer",
                        "description": "Total impressions generated.",
                    },
                    "total_engagement": {
                        "type": "integer",
                        "description": "Total engagements (likes + comments + shares + saves).",
                    },
                    "creator_count": {
                        "type": "integer",
                        "description": "Number of creators involved in the campaign.",
                    },
                    "budget_spent_inr": {
                        "type": "number",
                        "description": "Total budget spent in INR.",
                    },
                    "conversions": {
                        "type": "integer",
                        "description": "Number of conversions or sales attributed to the campaign.",
                    },
                    "campaign_goal": {
                        "type": "string",
                        "description": "Original campaign objective for comparison.",
                    },
                    "niche": {
                        "type": "string",
                        "description": "Creator niche to benchmark against industry averages.",
                    },
                },
                "required": ["campaign_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_budget_allocation",
            "description": (
                "Recommend how to split an influencer marketing budget across creator tiers "
                "and content types to maximize ROI. Use when a brand asks how to allocate "
                "or distribute their campaign budget."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "total_budget_inr": {
                        "type": "number",
                        "description": "Total available influencer marketing budget in INR.",
                    },
                    "campaign_goal": {
                        "type": "string",
                        "description": "Primary campaign objective, e.g. awareness, conversions, engagement.",
                    },
                    "creator_count": {
                        "type": "integer",
                        "description": "Approximate number of creators to work with.",
                    },
                    "niche": {
                        "type": "string",
                        "description": "Creator niche/category for pricing context.",
                    },
                    "preferred_tiers": {
                        "type": "array",
                        "description": "Preferred creator tiers to include.",
                        "items": {
                            "type": "string",
                            "enum": ["nano", "micro", "mid-tier", "macro"],
                        },
                    },
                },
                "required": ["total_budget_inr", "campaign_goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "benchmark_campaign_performance",
            "description": (
                "Compare campaign metrics against industry benchmarks for the given niche. "
                "Returns a performance grade and gap analysis. Use when a brand wants to "
                "know how their results compare to industry standards."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "niche": {
                        "type": "string",
                        "description": "Creator niche to benchmark against, e.g. fitness, beauty, tech.",
                    },
                    "engagement_rate": {
                        "type": "number",
                        "description": "Observed average engagement rate as a decimal (e.g. 0.045 for 4.5%).",
                    },
                    "reach_per_post": {
                        "type": "integer",
                        "description": "Average reach per post across the campaign.",
                    },
                    "cost_per_engagement_inr": {
                        "type": "number",
                        "description": "Cost per engagement in INR.",
                    },
                    "cost_per_reach_inr": {
                        "type": "number",
                        "description": "Cost per 1000 reach (CPM) in INR.",
                    },
                    "conversion_rate": {
                        "type": "number",
                        "description": "Conversion rate as a decimal (e.g. 0.02 for 2%).",
                    },
                },
                "required": ["niche"],
            },
        },
    },
]
