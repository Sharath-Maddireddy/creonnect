"""Shared helpers for parsing LLM TOON responses into typed Pydantic models.

Extracts the common logic duplicated in:
- global_trend_engine.py (fetch_global_trends)
- trend_recommendation_engine.py (generate_trend_recommendations)
"""

from __future__ import annotations

from typing import Any, Type, TypeVar

from backend.app.ai.toon import loads as toon_loads

T = TypeVar("T")


def toon_parse_list(text: str, root_key: str, model_cls: Type[T]) -> list[T]:
    """Parse TOON text into a validated list of Pydantic model instances.

    The LLM may return either:
    - A top-level list (lines starting with '-')  → wrap under root_key
    - A dict whose root_key maps to a list       → extract the list
    - A dict containing a list somewhere         → find first list value
    - A single dict                              → wrap into a list

    Each dict item is validated via model_cls.model_validate() (or direct
    constructor **item as a fallback).

    Args:
        text: Raw TOON text from the LLM.
        root_key: The expected key when wrapping a top-level list.
        model_cls: Pydantic model class to instantiate for each item.

    Returns:
        Validated list of model instances (may be empty if nothing parses).

    Raises:
        ValueError: If the text cannot be parsed into valid TOON.
    """
    text = text.strip()

    if text.startswith("-"):
        # LLM returned a top-level list; wrap under root_key
        wrapped = f"{root_key}:\n" + "\n".join("  " + line for line in text.splitlines())
        parsed = toon_loads(wrapped)
        raw_items: list[dict[str, Any]] = parsed.get(root_key, []) if isinstance(parsed, dict) else []
    else:
        parsed = toon_loads(text)
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected dict from TOON parser, got {type(parsed).__name__}")

        # Try root_key first
        if root_key in parsed and isinstance(parsed[root_key], list):
            raw_items = parsed[root_key]
        else:
            # Find first list value in the parsed dict
            raw_items = None
            for v in parsed.values():
                if isinstance(v, list):
                    raw_items = v
                    break

            if raw_items is None:
                # Treat the parsed dict itself as a single item
                raw_items = [parsed]

    # Validate each item
    results: list[T] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            try:
                instance = model_cls.model_validate(item)  # type: ignore[attr-defined]
            except Exception:
                instance = model_cls(**item)
            results.append(instance)
        except Exception as exc:
            from backend.app.utils.logger import logger
            logger.warning("toon_parse_list: skipped invalid item for %s: %s", model_cls.__name__, exc)

    return results
