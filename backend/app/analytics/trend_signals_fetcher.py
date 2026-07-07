from __future__ import annotations

"""Fetch live trend signals from external sources for prompt context.

This module provides a single public async function,
`fetch_live_trend_signals`, which gathers short, plain-text trend cues from:
1) Tavily Search API and 2) Google Trends via `pytrends`.

The function is failure-tolerant by design: source-level failures are logged at
warning level and partial results are returned without raising.
"""

import asyncio
import os
from typing import Any

from backend.app.utils.logger import logger


def _clean_text(value: Any, *, max_length: int | None = None) -> str:
    """Normalize a value into a compact string, optionally truncating length."""
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().split())
    if not text:
        return ""
    if max_length is not None:
        return text[:max_length]
    return text


def _build_tavily_query(primary_category: str, sub_niches: list[str]) -> str:
    """Build the Tavily search query for recent short-form platform trends."""
    primary = _clean_text(primary_category)
    first_niche = _clean_text(sub_niches[0]) if sub_niches else ""
    if first_niche:
        return (
            f"trending {primary} {first_niche} content on Instagram Reels and "
            "TikTok this week"
        )
    return f"trending {primary} content on Instagram Reels and TikTok this week"


def _fetch_tavily_signals_sync(primary_category: str, sub_niches: list[str]) -> list[str]:
    """Fetch trend snippets from Tavily synchronously (to be run in a thread)."""
    api_key = _clean_text(os.getenv("TAVILY_API_KEY"))
    if not api_key:
        logger.warning("[TrendSignals] Tavily skipped: missing TAVILY_API_KEY.")
        return []

    try:
        from tavily import TavilyClient
    except Exception as exc:
        logger.warning("[TrendSignals] Tavily unavailable: %s", exc)
        return []

    try:
        client = TavilyClient(api_key=api_key)
        query = _build_tavily_query(primary_category, sub_niches)
        response = client.search(query=query, max_results=5, search_depth="advanced")
        results = response.get("results", []) if isinstance(response, dict) else []

        signals: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            snippet = _clean_text(item.get("content"), max_length=200)
            if snippet:
                signals.append(snippet)
        return signals
    except Exception as exc:
        logger.warning("[TrendSignals] Tavily fetch failed: %s", exc)
        return []


def _build_google_keywords(primary_category: str, sub_niches: list[str]) -> list[str]:
    """Build up to 5 deduplicated Google Trends keywords."""
    raw_keywords = [primary_category, *sub_niches[:2]]
    seen: set[str] = set()
    keywords: list[str] = []
    for raw in raw_keywords:
        keyword = _clean_text(raw)
        if not keyword:
            continue
        key = keyword.casefold()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(keyword)
        if len(keywords) >= 5:
            break
    return keywords


def _fetch_google_trends_signals_sync(primary_category: str, sub_niches: list[str]) -> list[str]:
    """Fetch related top queries from Google Trends synchronously."""
    try:
        from pytrends.request import TrendReq
    except Exception as exc:
        logger.warning("[TrendSignals] Google Trends unavailable: %s", exc)
        return []

    keywords = _build_google_keywords(primary_category, sub_niches)
    if not keywords:
        logger.warning("[TrendSignals] Google Trends skipped: no valid keywords.")
        return []

    try:
        client = TrendReq()
        client.build_payload(kw_list=keywords, timeframe="now 7-d")
        related = client.related_queries()
        if not isinstance(related, dict):
            return []

        first_keyword = keywords[0]
        first_related = related.get(first_keyword)
        if not isinstance(first_related, dict):
            return []

        top_df = first_related.get("top")
        if top_df is None or getattr(top_df, "empty", True):
            return []

        if "query" not in getattr(top_df, "columns", []):
            return []

        queries = top_df["query"].dropna().astype(str).tolist()
        signals: list[str] = []
        for query in queries[:5]:
            text = _clean_text(query)
            if text:
                signals.append(text)
        return signals
    except Exception as exc:
        logger.warning("[TrendSignals] Google Trends fetch failed: %s", exc)
        return []


async def _fetch_tavily_signals(primary_category: str, sub_niches: list[str]) -> list[str]:
    """Run Tavily fetch in a background thread."""
    return await asyncio.to_thread(
        _fetch_tavily_signals_sync,
        primary_category,
        sub_niches,
    )


async def _fetch_google_trends_signals(primary_category: str, sub_niches: list[str]) -> list[str]:
    """Run Google Trends fetch in a background thread."""
    return await asyncio.to_thread(
        _fetch_google_trends_signals_sync,
        primary_category,
        sub_niches,
    )


async def fetch_live_trend_signals(
    primary_category: str,
    sub_niches: list[str],
) -> list[str]:
    """Fetch and merge live trend signals from Tavily and Google Trends.

    The two source fetches are executed concurrently. Failures from either
    source never raise from this function; warnings are logged and successful
    source results are still returned.

    Args:
        primary_category: Main creator/category topic.
        sub_niches: Optional sub-niche list used to refine source queries.

    Returns:
        A deduplicated list of up to 10 non-empty plain-text trend strings.
    """
    try:
        tavily_signals, google_signals = await asyncio.gather(
            _fetch_tavily_signals(primary_category, sub_niches),
            _fetch_google_trends_signals(primary_category, sub_niches),
        )
    except Exception as exc:
        logger.warning("[TrendSignals] Aggregation failed: %s", exc)
        return []

    unique_signals: list[str] = []
    seen: set[str] = set()
    for signal in [*tavily_signals, *google_signals]:
        text = _clean_text(signal)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_signals.append(text)
        if len(unique_signals) >= 10:
            break

    return unique_signals
