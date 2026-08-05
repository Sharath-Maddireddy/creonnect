# Best Use Cases for Tool Calling — Creonnect Brand Side

## Context: What Exists Today

The brand side currently has **three endpoints** under `/api/brand/campaign`:

| Endpoint | What it does | AI involvement |
|---|---|---|
| `POST /campaign/match` | Structured `BrandProfile` → score pool → top 10 | None (deterministic) |
| `POST /campaign/discover` | Natural language prompt → parse → score pool → top 10 | 1 LLM call via [campaign_prompt_service.py](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/campaign_prompt_service.py) to extract structured brief |
| `GET /campaign/lookalikes/{id}` | Vector similarity → top-k | None (pgvector) |

The AI-powered flow in `/discover` is a single **prompt → parse → execute** chain. The LLM extracts `brand_name`, `niche`, `min_followers`, etc. from free text, and then hard-coded Python runs the match engine. This is where tool calling can massively upgrade the brand experience.

---

## The 3 Best Cases for Tool Calling

### 🥇 1. Agentic Campaign Discovery (Highest Impact)

**Problem today:** The `/discover` endpoint does one LLM call to extract a flat brief, then runs a fixed pipeline. If the brand says *"Find me fitness creators with great Reels who are similar to @kayla_itsines"*, the system can't:
- Look up `@kayla_itsines` to understand what "similar" means
- Filter by content type (Reels vs Images)
- Combine lookalike search with filter-based discovery
- Iteratively refine results based on what's found

**Tool-calling solution:** Give the LLM access to your existing backend capabilities as tools, and let it orchestrate multi-step discovery.

```
┌─────────────────────────────────────────────────┐
│  Brand prompt: "Find fitness creators with      │
│  50k+ followers who post Reels like             │
│  @kayla_itsines, high brand safety"             │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │  LLM + Tools   │
              └───────┬────────┘
                      │
        ┌─────────────┼─────────────────┐
        ▼             ▼                 ▼
  Tool Call 1    Tool Call 2       Tool Call 3
  search_pool()  find_lookalikes() get_creator_profile()
        │             │                 │
        └─────────────┼─────────────────┘
                      ▼
              ┌────────────────┐
              │  LLM Synthesis │  ← merges, dedupes, ranks
              └───────┬────────┘
                      ▼
           Final ranked results +
           natural language explanation
```

#### Proposed Tool Schema

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_creator_pool",
            "description": "Search the Creonnect creator database by niche, follower range, and quality filters. Returns scored creator profiles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "niche": {
                        "type": "string",
                        "description": "Content niche to filter by (e.g. fitness, food, tech, beauty, fashion)"
                    },
                    "min_followers": {
                        "type": "integer",
                        "description": "Minimum follower count"
                    },
                    "max_followers": {
                        "type": "integer",
                        "description": "Maximum follower count"
                    },
                    "min_engagement_rate": {
                        "type": "number",
                        "description": "Minimum engagement rate as decimal (0.0-1.0)"
                    },
                    "min_brand_safety": {
                        "type": "number",
                        "description": "Minimum brand safety score (0-100)"
                    },
                    "content_type": {
                        "type": "string",
                        "enum": ["REEL", "IMAGE", "ANY"],
                        "description": "Filter by dominant content type"
                    }
                },
                "required": ["niche"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_lookalike_creators",
            "description": "Find creators who are semantically similar to a reference creator using vector embeddings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Account ID of the reference creator"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of lookalikes to return (default 5, max 10)"
                    }
                },
                "required": ["account_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_creator_analysis",
            "description": "Get the full analysis profile for a specific creator including health score, content quality, brand safety, and engagement metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "The creator's account ID"
                    }
                },
                "required": ["account_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "score_creator_brand_fit",
            "description": "Score how well a specific creator matches a brand profile. Returns match score breakdown across niche fit, engagement quality, brand safety, content quality, and audience size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Creator account ID to evaluate"
                    },
                    "brand_niche": {
                        "type": "string",
                        "description": "Brand's content niche"
                    },
                    "min_followers": {"type": "integer"},
                    "max_followers": {"type": "integer"},
                    "min_engagement_rate": {"type": "number"},
                    "min_brand_safety": {"type": "number"}
                },
                "required": ["account_id", "brand_niche"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_creators",
            "description": "Compare multiple creators side-by-side on key metrics. Use when a brand wants to decide between shortlisted creators.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of creator account IDs to compare (2-5)"
                    },
                    "focus_metrics": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["engagement", "brand_safety", "content_quality", "audience_size", "niche_fit"]
                        },
                        "description": "Which metrics to emphasize in comparison"
                    }
                },
                "required": ["account_ids"]
            }
        }
    }
]
```

> [!IMPORTANT]
> This is the single highest-ROI tool-calling use case because it transforms `/discover` from a rigid single-shot pipeline into a flexible agent that can handle complex, multi-constraint brand briefs.

---

### 🥈 2. Campaign Brief Refinement via Conversational Tools

**Problem today:** If the LLM extracts an ambiguous brief (e.g., brand says "mid-tier creators" but means fashion specifically), the system guesses or falls back to `"general"` niche. There's no way to ask clarifying questions.

**Tool-calling solution:** Add tools that let the LLM ask the brand for clarification *before* executing the search.

```python
{
    "name": "ask_brand_clarification",
    "description": "Ask the brand user a clarifying question when their campaign brief is ambiguous. Returns the user's answer.",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The clarifying question to ask"
            },
            "suggested_options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional suggested answers for quick selection"
            }
        },
        "required": ["question"]
    }
}
```

**Example flow:**
```
Brand: "I need creators for our summer launch"
  → LLM calls ask_brand_clarification(
      question="What product category is your summer launch in?",
      suggested_options=["Fashion/Apparel", "Food/Beverage", "Fitness", "Beauty", "Travel"]
    )
Brand: "It's swimwear"
  → LLM calls search_creator_pool(niche="fashion", content_type="REEL")
  → LLM returns curated results with context
```

---

### 🥉 3. Post-Discovery Campaign Planning Tools

**Problem today:** After matching creators, the brand gets a list and a generic summary. They have no tools to take the next step (outreach, budget estimation, content brief generation).

**Tool-calling solution:** Add downstream action tools that the agent can invoke after discovery:

```python
tools_phase_2 = [
    {
        "name": "generate_outreach_brief",
        "description": "Generate a personalized outreach brief for a specific creator based on their content style and the brand's campaign goals.",
        "parameters": {
            "account_id": "string",       # creator to draft for
            "campaign_goal": "string",     # what the brand wants
            "brand_tone": "string",        # casual, professional, etc.
            "deliverables": ["string"]     # e.g. ["2 Reels", "3 Stories"]
        }
    },
    {
        "name": "estimate_campaign_cost",
        "description": "Estimate collaboration cost range for a creator based on their follower count, engagement rate, and content type.",
        "parameters": {
            "account_ids": ["string"],
            "deliverable_type": "REEL | IMAGE | STORY",
            "quantity": "integer"
        }
    },
    {
        "name": "generate_content_brief",
        "description": "Generate a content creation brief tailored to a specific creator's style and the brand's messaging.",
        "parameters": {
            "account_id": "string",
            "brand_name": "string",
            "key_messages": ["string"],
            "content_type": "REEL | IMAGE"
        }
    }
]
```

---

## Architecture Comparison

| Approach | Current (`/discover`) | Tool Calling (Recommended) | Full Agentic Loop |
|---|---|---|---|
| LLM calls | 1 (extraction) | 1-4 (extraction + tool orchestration) | 5-10+ (autonomous planning) |
| Flexibility | Rigid pipeline | Handles complex multi-constraint briefs | Maximum flexibility |
| Latency | ~2-3s | ~5-8s | ~15-30s |
| Cost per query | ~$0.002 | ~$0.01-0.03 | ~$0.05-0.15 |
| Error surface | Small | Moderate (tool schema validation) | Large (needs guardrails) |
| **Best for** | MVP / simple queries | **Production brand product** | Power-user / enterprise |

> [!TIP]
> **Recommendation:** Start with the tool-calling approach (middle column). It gives you 80% of the agentic benefit at 20% of the complexity. You can graduate to a full agentic loop later for enterprise clients.

---

## Implementation Priority

| Priority | Use Case | Complexity | Impact |
|---|---|---|---|
| **P0** | `search_creator_pool` + `find_lookalike_creators` + `score_creator_brand_fit` as tools in `/discover` | Medium | 🔥🔥🔥 Transforms discovery |
| **P1** | `ask_brand_clarification` for conversational refinement | Low | 🔥🔥 Reduces bad matches |
| **P1** | `get_creator_analysis` for drill-down during conversation | Low | 🔥🔥 Deeper insights |
| **P2** | `compare_creators` side-by-side | Medium | 🔥 Decision support |
| **P3** | `generate_outreach_brief` + `generate_content_brief` | Medium | 🔥 End-to-end workflow |
| **P3** | `estimate_campaign_cost` | Low | 🔥 Planning support |

---

## Key Implementation Notes

### What model to use for tool calling?

Your codebase already uses `gpt-4o-mini` in [campaign_prompt_service.py](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/campaign_prompt_service.py#L51). For tool calling:
- **`gpt-4o-mini`** — Good enough for simple tool routing, cheapest option
- **`gpt-4o`** — Better at complex multi-tool orchestration, recommended for production
- **`gemini-2.0-flash`** — Already in your stack for vision/batch, supports function calling, 50% off with batch API

### How it maps to existing code

Every proposed tool maps directly to existing backend functions:

| Tool | Existing Implementation |
|---|---|
| `search_creator_pool` | [creator_pool_service.query_creator_pool()](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/creator_pool_service.py#L106-L126) |
| `find_lookalike_creators` | [creator_pool_service.find_lookalikes()](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/creator_pool_service.py#L166-L211) |
| `score_creator_brand_fit` | [brand_match_engine.score_creator_against_brand()](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/analytics/brand_match_engine.py#L212-L323) |
| `get_creator_analysis` | [account_analysis_result_store](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/account_analysis_result_store.py) |
| `compare_creators` | New — composes `get_creator_analysis` × N |

> [!NOTE]
> The beauty of this approach is that **zero new backend services** are needed for P0. You're wrapping existing functions as tool schemas and letting the LLM orchestrate them.

---

## Open Questions

1. **Stateful or stateless?** Should the brand conversation have session memory (multi-turn refinement), or stay single-shot like today?
2. **Max tool calls per request?** Suggest capping at 4-5 to keep latency under 10s.
3. **Should we expose this as a chat-style API** (`POST /api/brand/chat`) or upgrade the existing `/discover` endpoint?
4. **Budget for LLM costs?** Tool-calling with `gpt-4o` costs ~5-15× more per query than current `gpt-4o-mini` extraction-only.
