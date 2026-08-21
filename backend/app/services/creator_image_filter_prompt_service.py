"""Reviewable, server-owned prompt catalog for Creator Image Editor filters."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_PROMPT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "image_editor" / "ai_filter_prompts_v1.json"
_SUPPORTED_RESOLUTIONS = {"512", "1K", "2K", "4K"}


@lru_cache(maxsize=1)
def get_creator_image_filter_prompt_config() -> dict[str, Any]:
    with _PROMPT_CONFIG_PATH.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not payload.get("version") or not isinstance(payload.get("filters"), list):
        raise ValueError("Creator image filter prompt config is invalid")
    style_ids = [str(item.get("style_id", "")) for item in payload["filters"]]
    if any(not style_id for style_id in style_ids) or len(style_ids) != len(set(style_ids)):
        raise ValueError("Creator image filter prompt style IDs must be non-empty and unique")
    if any(not str(item.get("prompt", "")).strip() for item in payload["filters"]):
        raise ValueError("Every Creator image filter must define a prompt")
    if any(item.get("resolution") not in _SUPPORTED_RESOLUTIONS for item in payload["filters"]):
        raise ValueError("Every Creator image filter must define a supported Gemini resolution")
    return payload


def get_creator_image_filter(style_id: str) -> dict[str, Any]:
    for item in get_creator_image_filter_prompt_config()["filters"]:
        if item["style_id"] == style_id:
            return item
    raise ValueError(f"Unknown Creator image filter prompt: {style_id}")


def get_creator_image_filter_prompt(style_id: str) -> str:
    return str(get_creator_image_filter(style_id)["prompt"]).strip()


def get_creator_image_filter_resolution(style_id: str) -> str:
    return str(get_creator_image_filter(style_id)["resolution"])
