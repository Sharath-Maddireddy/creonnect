# /document-code (or /add-comments)
Transform the target file or code block to **Staff/Principal Engineer-grade code craftsmanship** (matching top-tier engineering standards at Google, Stripe, Anthropic, and Meta).

## Core Philosophy
1. **Never explain the syntax** (e.g., NO `# loop over items`, NO `# returns data`).
2. **Always explain the Architecture, Intent, Invariants, and Failure Modes**:
   - *Why* was this approach chosen over alternatives?
   - What are the mathematical or algorithmic invariants?
   - What are the concurrency, atomicity, or rate-limit guarantees?
   - What upstream/downstream services depend on this contract?

---

## 1. Python Standards (Google Docstring + Tier-1 System Engineering)

### A. Module-Level Header
Every Python module (`.py`) MUST have a top-level docstring defining:
```python
"""
Module Name / Core Responsibility.

Architecture Role:
    Describe where this sits in the pipeline (e.g., Ingestion -> Analytics -> AI Synthesis -> Storage).

Upstream Consumers:
    List routes, workers, or tasks calling this module.

Downstream Dependencies:
    List external APIs, databases, Redis queues, or models used.

Guarantees & Invariants:
    - Thread-safety / Asyncio safety.
    - Idempotency guarantees.
    - Caching / Rate-limiting policies.
"""
```

### B. Class & Function Docstrings (Strict Google Standard)
```python
def calculate_brand_safety_index(
    creator_metrics: CreatorMetricsSnapshot,
    sentiment_distribution: Dict[str, float],
    strict_mode: bool = False,
) -> BrandSafetyScore:
    """Computes a multi-factor brand safety confidence score (0.0 - 100.0).

    Integrates negative sentiment thresholds, controversial topic frequency,
    and historical comment toxicity. Applies non-linear penalty curves to
    prevent high-follower accounts from masking acute brand risk.

    Args:
        creator_metrics: 30-day historical snapshot of engagement and follower metrics.
        sentiment_distribution: Normalized histogram of sentiment tags (keys: 'pos', 'neu', 'neg').
            Sum of values must equal 1.0 ± 0.001.
        strict_mode: If True, applies zero-tolerance multipliers for alcohol, gambling,
            and political controversy flags regardless of audience engagement.

    Returns:
        BrandSafetyScore: Typed container containing the normalized composite score,
            risk tier enumeration (`LOW`, `MODERATE`, `HIGH`, `CRITICAL`), and granular
            penalty breakdowns for auditability.

    Raises:
        ValueError: If `sentiment_distribution` keys are malformed or values do not sum to 1.0.
        MetricUnderflowError: If `creator_metrics` contains fewer than minimum required sample posts.

    Complexity:
        Time: O(N) where N is the number of analyzed comments/posts.
        Space: O(1) auxiliary working memory.
    """
```

### C. Inline Intent & Architectural Callouts
Use structured tags for non-obvious engineering decisions:
- `# NOTE(arch):` Architectural rationale or design tradeoff.
- `# INVARIANT:` Assumptions that must never be violated.
- `# PERF:` Performance optimization (e.g., vectorized ops, avoiding N+1 queries, Redis pipelining).
- `# FALLBACK:` Graceful degradation behavior when an external API (OpenAI/Instagram) times out.
- `# SECURITY:` Input sanitization, token redaction, or rate-limiting guards.

---

## 2. Frontend / React / TypeScript Standards (TSDoc + Clean Architecture)

### A. Component-Level Documentation
```tsx
/**
 * `TrendsDiscoveryGrid`
 *
 * Primary exploration interface for trending niche topics and creator clusters.
 * Orchestrates infinite scroll pagination, active filter debounce, and optimistic
 * UI updates when saving trend bookmarks.
 *
 * @remarks
 * Uses virtualized rendering for lists exceeding 50 items to maintain 60fps scrolling.
 * Emits telemetry events on filter change for conversion analytics.
 *
 * @param props - {@link TrendsDiscoveryGridProps} configuration.
 * @returns Accessible grid container with live ARIA announcements.
 */
```

### B. Hooks & State Transformations
Document side-effects, cache invalidation keys, and cleanup lifecycles:
```tsx
/**
 * Hook to manage real-time background analysis polling.
 *
 * @param jobId - UUID string for the active Redis RQ job.
 * @param options - Polling interval and retry budget configuration.
 * 
 * @returns Current job state, progress percentage (0-100), and terminal result payload.
 * 
 * @example
 * ```tsx
 * const { status, progress, data, error } = useAnalysisJob(jobId, { pollIntervalMs: 2000 });
 * ```
 */
```

---

## Instructions for Execution:
1. Scan the target file completely to understand its architecture and edge cases.
2. Add the **Module Header Docstring**.
3. Add **Comprehensive Docstrings** to all public functions, classes, API routes, and components with typed args, returns, error conditions, and complexity.
4. Add **Architectural Tag Comments** (`NOTE(arch)`, `INVARIANT`, `PERF`, `FALLBACK`) before complex logic, calculations, or external service interactions.
5. Keep existing logic, variables, and code structure 100% functionally identical.
