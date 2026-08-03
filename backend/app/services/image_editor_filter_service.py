"""Deterministic filter-only processing service for Phase 1."""

from __future__ import annotations

import base64
import hashlib
import io
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from backend.app.domain.image_editor_models import ApplyFilterRequest, ApplyFilterResponse, ApplyFilterWarning
from backend.app.services.image_editor_config_service import (
    get_image_editor_public_config,
    get_intensity_profile,
    get_quality_preset,
    get_style_profile,
    validate_filter_controls,
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _apply_temperature(image: Image.Image, amount: float) -> Image.Image:
    if amount == 0:
        return image
    r_mult = 1.0 + (amount / 100.0) * 0.12
    b_mult = 1.0 - (amount / 100.0) * 0.12
    g_mult = 1.0
    return image.convert("RGB").point(
        lambda px, lut={
            "r": [int(_clamp(i * r_mult, 0, 255)) for i in range(256)],
            "g": [int(_clamp(i * g_mult, 0, 255)) for i in range(256)],
            "b": [int(_clamp(i * b_mult, 0, 255)) for i in range(256)],
        }: px
    )


def _split_apply_temperature(image: Image.Image, amount: float) -> Image.Image:
    if amount == 0:
        return image
    r, g, b = image.convert("RGB").split()
    r = r.point(lambda i: int(_clamp(i * (1.0 + (amount / 100.0) * 0.12), 0, 255)))
    b = b.point(lambda i: int(_clamp(i * (1.0 - (amount / 100.0) * 0.12), 0, 255)))
    return Image.merge("RGB", (r, g, b))


def _apply_tint(image: Image.Image, amount: float) -> Image.Image:
    if amount == 0:
        return image
    r, g, b = image.convert("RGB").split()
    g = g.point(lambda i: int(_clamp(i * (1.0 - (amount / 100.0) * 0.05), 0, 255)))
    return Image.merge("RGB", (r, g, b))


def _apply_exposure(image: Image.Image, amount: float) -> Image.Image:
    if amount == 0:
        return image
    factor = 1.0 + (amount / 100.0) * 0.35
    return ImageEnhance.Brightness(image).enhance(_clamp(factor, 0.5, 1.6))


def _apply_contrast(image: Image.Image, amount: float) -> Image.Image:
    if amount == 0:
        return image
    factor = 1.0 + (amount / 100.0) * 0.45
    return ImageEnhance.Contrast(image).enhance(_clamp(factor, 0.55, 1.8))


def _apply_saturation(image: Image.Image, amount: float) -> Image.Image:
    if amount == 0:
        return image
    factor = 1.0 + (amount / 100.0) * 0.35
    return ImageEnhance.Color(image).enhance(_clamp(factor, 0.4, 1.6))


def _apply_sharpness(image: Image.Image, amount: float) -> Image.Image:
    if amount == 0:
        return image
    factor = 1.0 + (amount / 100.0) * 0.5
    return ImageEnhance.Sharpness(image).enhance(_clamp(factor, 0.4, 1.8))


def _apply_fade(image: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return image
    overlay = Image.new("RGB", image.size, color=(245, 240, 235))
    alpha = _clamp(amount / 100.0 * 0.22, 0.0, 0.25)
    return Image.blend(image.convert("RGB"), overlay, alpha)


def _apply_grain(image: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return image
    grayscale = ImageOps.grayscale(image.convert("RGB"))
    noise = Image.effect_noise(image.size, _clamp(amount * 1.6, 1.0, 32.0))
    mixed = Image.blend(grayscale, noise, _clamp(amount / 100.0 * 0.35, 0.0, 0.35))
    mixed_rgb = Image.merge("RGB", (mixed, mixed, mixed))
    return Image.blend(image.convert("RGB"), mixed_rgb, _clamp(amount / 100.0 * 0.16, 0.0, 0.16))


def _apply_vignette(image: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return image
    width, height = image.size
    mask = Image.new("L", (width, height), 255)
    center_x = width / 2.0
    center_y = height / 2.0
    max_distance = (center_x ** 2 + center_y ** 2) ** 0.5
    pixels = mask.load()
    strength = _clamp(amount / 100.0, 0.0, 1.0)
    for y in range(height):
        for x in range(width):
            dx = x - center_x
            dy = y - center_y
            distance = (dx ** 2 + dy ** 2) ** 0.5 / max_distance
            falloff = 1.0 - distance ** 1.8 * 0.55 * strength
            pixels[x, y] = int(_clamp(255 * falloff, 0, 255))
    return Image.composite(image.convert("RGB"), Image.new("RGB", image.size, "black"), mask)


def _apply_monochrome(image: Image.Image, enabled: bool) -> Image.Image:
    if not enabled:
        return image
    return ImageOps.grayscale(image).convert("RGB")


def _scale_profile(profile: dict[str, Any], intensity_value: int) -> dict[str, Any]:
    ratio = _clamp(intensity_value / 50.0, 0.0, 1.8)
    scaled = {}
    for key, value in profile.items():
        if isinstance(value, bool):
            scaled[key] = value
        elif isinstance(value, (int, float)):
            scaled[key] = round(float(value) * ratio, 2)
        else:
            scaled[key] = value
    return scaled


def build_filter_request_hash(request: ApplyFilterRequest, width: int, height: int) -> str:
    payload = (
        f"style={request.style_id}|"
        f"intensity={request.intensity_id}|"
        f"quality={request.quality_preset_id}|"
        f"controls={','.join(sorted(request.enabled_control_ids))}|"
        f"width={width}|height={height}|"
        f"output={request.output_format or ''}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _encode_image(image: Image.Image, output_format: str, compression: int | None) -> tuple[str, str]:
    buffer = io.BytesIO()
    fmt = output_format.upper()
    save_kwargs: dict[str, Any] = {}
    if fmt in {"JPEG", "JPG"}:
        save_kwargs["quality"] = compression or 90
        save_kwargs["optimize"] = True
        image = image.convert("RGB")
        mime_type = "image/jpeg"
    elif fmt == "WEBP":
        save_kwargs["quality"] = compression or 90
        mime_type = "image/webp"
    else:
        fmt = "PNG"
        mime_type = "image/png"
    image.save(buffer, format=fmt, **save_kwargs)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), mime_type


def apply_filter_to_image(image_bytes: bytes, request: ApplyFilterRequest) -> ApplyFilterResponse:
    validate_filter_controls(request.enabled_control_ids)
    style = get_style_profile(request.style_id)
    intensity = get_intensity_profile(request.intensity_id)
    quality = get_quality_preset(request.quality_preset_id)
    public_config = get_image_editor_public_config()

    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    original_dimensions = (width, height)
    request_hash = build_filter_request_hash(request, width, height)

    profile = _scale_profile(style.get("native_filter_profile", {}), int(intensity["value"]))

    warnings: list[ApplyFilterWarning] = []
    if abs(float(profile.get("grain", 0))) >= 12:
        warnings.append(ApplyFilterWarning(code="high_grain", message="Selected profile applies visible grain."))
    if abs(float(profile.get("contrast", 0))) >= 10:
        warnings.append(
            ApplyFilterWarning(code="high_contrast", message="Selected profile applies high contrast and may clip tones.")
        )

    image = _split_apply_temperature(image, float(profile.get("temperature", 0)))
    image = _apply_tint(image, float(profile.get("tint", 0)))
    image = _apply_exposure(image, float(profile.get("exposure", 0)))
    image = _apply_contrast(image, float(profile.get("contrast", 0)))
    image = _apply_saturation(image, float(profile.get("saturation", 0)) + float(profile.get("vibrance", 0)) * 0.6)
    image = _apply_fade(image, float(profile.get("fade", 0)))
    image = _apply_grain(image, float(profile.get("grain", 0)))
    image = _apply_vignette(image, float(profile.get("vignette", 0)))
    image = _apply_sharpness(image, float(profile.get("sharpness", 0)))
    image = _apply_monochrome(image, bool(profile.get("monochrome", False)))

    if image.size != original_dimensions:
        raise ValueError("Filter-only mode must preserve the source dimensions.")

    output_format = str(request.output_format or quality["output_format"]).lower()
    image_base64, mime_type = _encode_image(
        image=image,
        output_format=output_format,
        compression=quality.get("output_compression"),
    )

    return ApplyFilterResponse(
        config_version=public_config.config_version,
        mode=public_config.mode,
        engine="pillow-deterministic-filter",
        request_hash=request_hash,
        mime_type=mime_type,
        width=width,
        height=height,
        output_format=output_format,
        image_base64=image_base64,
        warnings=warnings,
        applied_profile=profile,
    )
