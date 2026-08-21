"""Server-owned structured configuration for the Creator Image Editor."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.domain.image_editor_models import (
    CreatorImageEditorConfigResponse,
    CreatorImageEditorEnhancement,
    CreatorImageEditorOption,
    CreatorImageEditorStyle,
    CreatorImageGenerationSelection,
)
from backend.app.services.creator_image_filter_prompt_service import get_creator_image_filter_prompt_config


_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "image_editor" / "creator_image_editor_v1.json"


@lru_cache(maxsize=1)
def get_creator_image_editor_raw_config() -> dict[str, Any]:
    with _CONFIG_PATH.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    required = {"config_version", "styles", "goals", "events", "enhancements", "output_formats"}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"Creator image editor config missing: {', '.join(sorted(missing))}")
    return payload


@lru_cache(maxsize=1)
def get_creator_image_editor_config() -> CreatorImageEditorConfigResponse:
    raw = get_creator_image_editor_raw_config()
    prompt_flags = {
        str(item["style_id"]): bool(item["is_rotating"])
        for item in get_creator_image_filter_prompt_config()["filters"]
    }
    style_flags = {str(item["id"]): bool(item["is_rotating"]) for item in raw["styles"]}
    if style_flags != prompt_flags:
        raise ValueError("Creator image style and prompt catalogs must have matching IDs and rotating flags")
    return CreatorImageEditorConfigResponse(
        config_version=str(raw["config_version"]),
        styles=[
            CreatorImageEditorStyle.model_validate(
                {key: value[key] for key in ("id", "label", "description", "tag", "is_rotating", "category")}
            )
            for value in raw["styles"]
        ],
        goals=[CreatorImageEditorOption.model_validate(value) for value in raw["goals"]],
        events=[CreatorImageEditorOption.model_validate(value) for value in raw["events"]],
        enhancements=[CreatorImageEditorEnhancement.model_validate(value) for value in raw["enhancements"]],
        output_formats=[str(value) for value in raw["output_formats"]],
    )


def validate_creator_image_selection(selection: CreatorImageGenerationSelection) -> None:
    config = get_creator_image_editor_config()
    valid_ids = {
        "style_id": {item.id for item in config.styles},
        "goal_id": {item.id for item in config.goals},
        "event_id": {item.id for item in config.events},
        "enhancement_ids": {item.id for item in config.enhancements},
    }
    for field, value in (("style_id", selection.style_id), ("goal_id", selection.goal_id), ("event_id", selection.event_id)):
        if value not in valid_ids[field]:
            raise ValueError(f"Unknown {field}: {value}")
    unknown = set(selection.enhancement_ids).difference(valid_ids["enhancement_ids"])
    if unknown:
        raise ValueError(f"Unknown enhancement_ids: {', '.join(sorted(unknown))}")
    if len(selection.enhancement_ids) != len(set(selection.enhancement_ids)):
        raise ValueError("enhancement_ids must not contain duplicates")
    enhancements = {item.id: item for item in config.enhancements}
    selected = set(selection.enhancement_ids)
    conflicts = sorted(
        item_id for item_id in selected if selected.intersection(enhancements[item_id].mutually_exclusive_with)
    )
    if conflicts:
        raise ValueError("background_remove and background_blur cannot be selected together")
    if selection.output_format not in config.output_formats:
        raise ValueError(f"Unsupported output_format: {selection.output_format}")
