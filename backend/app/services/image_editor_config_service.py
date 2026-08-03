"""Config loader and validator for the backend-owned image editor."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.domain.image_editor_models import (
    ImageEditorConfigResponse,
    ImageEditorControlSummary,
    ImageEditorCatalogFilterSummary,
    ImageEditorFilterCatalogResponse,
    ImageEditorIntensitySummary,
    ImageEditorQualityPresetSummary,
    ImageEditorStyleSummary,
)


_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "image_editor" / "filter_only_config_v3.json"
)
_AI_FILTER_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "image_editor" / "ai_filter_catalog_v1.json"
)


def _load_raw_config() -> dict[str, Any]:
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("Image editor config must be a JSON object.")
    required_keys = {"config_key", "config_version", "mode", "styles", "edit_intensity", "quality_presets"}
    missing = sorted(required_keys - set(payload))
    if missing:
        raise ValueError(f"Image editor config missing keys: {', '.join(missing)}")
    return payload


@lru_cache(maxsize=1)
def get_image_editor_raw_config() -> dict[str, Any]:
    return _load_raw_config()


@lru_cache(maxsize=1)
def get_image_editor_public_config() -> ImageEditorConfigResponse:
    raw = get_image_editor_raw_config()
    return ImageEditorConfigResponse(
        config_key=str(raw["config_key"]),
        config_version=str(raw["config_version"]),
        mode=str(raw["mode"]),
        supported_modes=["filter-only", "ai-edit"],
        ai_edit_available=False,
        styles=[
            ImageEditorStyleSummary(
                id=str(style["id"]),
                label=str(style["label"]),
                description=str(style["description"]),
                popular=bool(style.get("popular", False)),
                filter_only_compatible=bool(style.get("filter_only_compatible", True)),
            )
            for style in raw.get("styles", [])
        ],
        intensities=[
            ImageEditorIntensitySummary(
                id=str(item["id"]),
                label=str(item["label"]),
                value=int(item["value"]),
            )
            for item in raw.get("edit_intensity", [])
        ],
        quality_presets=[
            ImageEditorQualityPresetSummary(
                id=str(item["id"]),
                label=str(item["label"]),
                output_format=str(item["output_format"]),
                output_compression=(
                    int(item["output_compression"]) if item.get("output_compression") is not None else None
                ),
            )
            for item in raw.get("quality_presets", [])
        ],
        controls=[
            ImageEditorControlSummary(
                id=str(item["id"]),
                label=str(item["label"]),
                enabled=bool(item.get("enabled", False)),
                visible_in_filter_only_mode=bool(item.get("visible_in_filter_only_mode", False)),
                filter_only_compatible=bool(item.get("filter_only_compatible", False)),
                operation_type=str(item.get("operation_type", "")),
            )
            for item in raw.get("controls", [])
        ],
        allowed_operations=[str(item) for item in raw.get("allowed_operations", [])],
        forbidden_operations=[str(item) for item in raw.get("forbidden_operations", [])],
    )


@lru_cache(maxsize=1)
def get_image_editor_filter_catalog() -> ImageEditorFilterCatalogResponse:
    """Return the public PRD filter catalog without provider prompt templates."""
    with _AI_FILTER_CATALOG_PATH.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict) or not isinstance(payload.get("filters"), list):
        raise ValueError("AI image filter catalog is invalid.")
    return ImageEditorFilterCatalogResponse(
        catalog_key=str(payload.get("catalog_key", "")),
        catalog_version=str(payload.get("catalog_version", "")),
        filters=[ImageEditorCatalogFilterSummary.model_validate(item) for item in payload["filters"]],
    )


def get_image_editor_catalog_filter(filter_id: str) -> ImageEditorCatalogFilterSummary:
    """Return one catalog entry or reject an unknown filter identifier."""
    for item in get_image_editor_filter_catalog().filters:
        if item.id == filter_id:
            return item
    raise ValueError(f"Unknown image editor filter: {filter_id}")


def get_style_profile(style_id: str) -> dict[str, Any]:
    raw = get_image_editor_raw_config()
    for style in raw.get("styles", []):
        if style.get("id") == style_id:
            return dict(style)
    raise ValueError(f"Unknown style_id: {style_id}")


def get_intensity_profile(intensity_id: str) -> dict[str, Any]:
    raw = get_image_editor_raw_config()
    for item in raw.get("edit_intensity", []):
        if item.get("id") == intensity_id:
            return dict(item)
    raise ValueError(f"Unknown intensity_id: {intensity_id}")


def get_quality_preset(quality_preset_id: str) -> dict[str, Any]:
    raw = get_image_editor_raw_config()
    for item in raw.get("quality_presets", []):
        if item.get("id") == quality_preset_id:
            return dict(item)
    raise ValueError(f"Unknown quality_preset_id: {quality_preset_id}")


def validate_filter_controls(control_ids: list[str]) -> None:
    raw = get_image_editor_raw_config()
    controls_by_id = {str(item.get("id")): item for item in raw.get("controls", [])}
    for control_id in control_ids:
        control = controls_by_id.get(control_id)
        if not control:
            raise ValueError(f"Unknown control_id: {control_id}")
        if not bool(control.get("filter_only_compatible", False)):
            raise ValueError(f"Control '{control_id}' is not filter-only compatible.")
