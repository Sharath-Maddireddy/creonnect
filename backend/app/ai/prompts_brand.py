"""Prompt templates for brand campaign features."""

from __future__ import annotations


CAMPAIGN_BRIEF_EXTRACTION_PROMPT = """You are an expert brand marketing campaign strategist. Extract structured campaign requirements from a brand's natural language description of their ideal creator or campaign.

We use a plain text format called TOON for our outputs.
Return exactly the TOON representation of the parsed brand profile, following these rules.

# Output Rules
1. Only return the requested keys, exactly as named.
2. Provide a single flat list of key-value pairs (no nested arrays or objects).
3. Do not include quotes, braces, commas, backticks, or markdown blocks unless it is part of a string value.
4. Each key-value pair must be on its own line: `key: value`.
5. For arrays, split items onto multiple lines using the exact format `  - item` under the key line.

# Required Fields
- brand_name: string or null
- niche: string or null (e.g. fitness, food, tech, gaming, beauty, fashion, travel)
- min_followers: integer or null
- max_followers: integer or null
- min_engagement_rate: decimal (0.0 to 1.0) or null
- campaign_goal: string or null
- content_type_preference: string or null (e.g. REEL, IMAGE, STORY)
- additional_requirements: list of strings (if empty, omit array elements)

# Follower Range Meaning
- "nano creators" = min_followers: 1000, max_followers: 10000
- "micro creators" = min_followers: 10000, max_followers: 100000
- "mid-tier" = min_followers: 100000, max_followers: 500000
- "macro" = min_followers: 500000, max_followers: 1000000
- "50k+" = min_followers: 50000
- "100k followers" = min_followers: 100000, max_followers: 100000

--- OUTPUT EXAMPLE ---
brand_name: FitLife Athletics
niche: fitness
min_followers: 50000
max_followers: null
min_engagement_rate: 0.05
campaign_goal: product launch for new pre-workout
content_type_preference: REEL
additional_requirements:
  - Must have energetic presentation style
  - Preferably based in USA

--- TARGET INPUT TO PARSE ---
{user_prompt}
"""
