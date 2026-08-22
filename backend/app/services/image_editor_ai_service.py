"""Provider calls for the explicit AI-edit mode."""

from __future__ import annotations

import asyncio
import base64
import io
import os
import time
from urllib.parse import urlsplit

import cv2
import numpy as np
from PIL import Image
from PIL import ImageDraw, ImageFilter, ImageOps

from backend.app.domain.image_editor_models import AIModeEditRequest
from backend.app.services.image_editor_provider_config import get_image_editor_provider_settings


def _azure_image_client_options(endpoint: str, configured_api_version: str) -> tuple[str, dict[str, str]]:
    """Normalize an Azure OpenAI or Foundry project endpoint for image APIs."""
    normalized = endpoint.rstrip("/")
    parsed = urlsplit(normalized)
    if "/api/projects/" in parsed.path:
        # Foundry project URLs do not expose /api/projects/.../openai/v1/images.
        # Image deployments use the resource-level Foundry Models API instead.
        return f"{parsed.scheme}://{parsed.netloc}/openai/v1/", {"api-version": "preview"}
    api_version = configured_api_version or "preview"
    return f"{normalized}/openai/v1/", {"api-version": api_version}


def _as_provider_png(image_bytes: bytes) -> io.BytesIO:
    """GPT Image edits accept PNG/JPG inputs; normalize browser uploads safely."""
    with Image.open(io.BytesIO(image_bytes)) as parsed:
        image = ImageOps.exif_transpose(parsed).convert("RGBA")
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    output.name = "original.png"
    return output


def _overlap_ratio(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    intersection_width = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    intersection_height = max(0, min(ay + ah, by + bh) - max(ay, by))
    intersection = intersection_width * intersection_height
    if not intersection:
        return 0.0
    return intersection / float(min(aw * ah, bw * bh))


def detect_face_boxes(image_bytes: bytes) -> list[tuple[int, int, int, int]]:
    """Detect frontal and profile faces without sending biometric data elsewhere."""
    with Image.open(io.BytesIO(image_bytes)) as parsed:
        source = ImageOps.exif_transpose(parsed).convert("RGB")
    source_array = np.asarray(source)
    height, width = source_array.shape[:2]
    scale = min(1.0, 1600.0 / max(width, height))
    if scale < 1.0:
        source_array = cv2.resize(source_array, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    grayscale = cv2.equalizeHist(cv2.cvtColor(source_array, cv2.COLOR_RGB2GRAY))
    minimum = max(24, round(min(grayscale.shape) * 0.035))
    cascade_names = (
        "haarcascade_frontalface_default.xml",
        "haarcascade_frontalface_alt2.xml",
        "haarcascade_profileface.xml",
    )
    detected: list[tuple[int, int, int, int]] = []
    for cascade_name in cascade_names:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + cascade_name)
        for mirrored in (False, True) if "profile" in cascade_name else (False,):
            scan = cv2.flip(grayscale, 1) if mirrored else grayscale
            boxes = cascade.detectMultiScale(scan, scaleFactor=1.08, minNeighbors=5, minSize=(minimum, minimum))
            for x, y, box_width, box_height in boxes:
                if mirrored:
                    x = scan.shape[1] - x - box_width
                candidate = tuple(round(value / scale) for value in (x, y, box_width, box_height))
                if not any(_overlap_ratio(candidate, existing) >= 0.55 for existing in detected):
                    detected.append(candidate)
    return sorted(detected, key=lambda box: (box[1], box[0]))


def _expanded_face_box(box: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    x, y, width, height = box
    image_width, image_height = size
    left = max(0, round(x - width * 0.16))
    top = max(0, round(y - height * 0.38))
    right = min(image_width, round(x + width * 1.16))
    bottom = min(image_height, round(y + height * 1.18))
    return left, top, right, bottom


def build_face_protection_mask(image_bytes: bytes, face_boxes: list[tuple[int, int, int, int]]) -> io.BytesIO | None:
    """Create a provider mask whose opaque areas cover every detected head."""
    if not face_boxes:
        return None
    with Image.open(io.BytesIO(image_bytes)) as parsed:
        source = ImageOps.exif_transpose(parsed)
        size = source.size
    alpha = Image.new("L", size, 0)
    for box in face_boxes:
        left, top, right, bottom = _expanded_face_box(box, size)
        alpha.paste(255, (left, top, right, bottom))
    mask = Image.new("RGBA", size, (0, 0, 0, 0))
    mask.putalpha(alpha)
    output = io.BytesIO()
    mask.save(output, format="PNG")
    output.seek(0)
    output.name = "face-protection-mask.png"
    return output


def _resolve_target_face_boxes(
    *,
    source_boxes: list[tuple[int, int, int, int]],
    generated_boxes: list[tuple[int, int, int, int]],
    source_size: tuple[int, int],
    generated_size: tuple[int, int],
) -> list[tuple[int, int, int, int]]:
    """Match detected faces and estimate locations when the output detector misses one."""
    if len(generated_boxes) > len(source_boxes):
        raise ValueError(
            "Identity safety check rejected the generated result because an additional face was detected. Please retry."
        )
    scale_x = generated_size[0] / source_size[0]
    scale_y = generated_size[1] / source_size[1]
    expected = [
        (round(x * scale_x), round(y * scale_y), round(width * scale_x), round(height * scale_y))
        for x, y, width, height in source_boxes
    ]
    if not generated_boxes:
        return expected

    matches: dict[int, tuple[int, int, int, int]] = {}
    unused_source_indexes = set(range(len(expected)))
    for generated_box in generated_boxes:
        generated_center = (
            generated_box[0] + generated_box[2] / 2,
            generated_box[1] + generated_box[3] / 2,
        )
        source_index = min(
            unused_source_indexes,
            key=lambda index: (
                expected[index][0] + expected[index][2] / 2 - generated_center[0]
            ) ** 2 + (
                expected[index][1] + expected[index][3] / 2 - generated_center[1]
            ) ** 2,
        )
        matches[source_index] = generated_box
        unused_source_indexes.remove(source_index)

    offsets_x = [matches[index][0] - expected[index][0] for index in matches]
    offsets_y = [matches[index][1] - expected[index][1] for index in matches]
    width_scales = [matches[index][2] / max(1, expected[index][2]) for index in matches]
    height_scales = [matches[index][3] / max(1, expected[index][3]) for index in matches]
    offset_x = float(np.median(offsets_x))
    offset_y = float(np.median(offsets_y))
    width_scale = float(np.median(width_scales))
    height_scale = float(np.median(height_scales))
    targets = []
    for index, box in enumerate(expected):
        if index in matches:
            targets.append(matches[index])
            continue
        x, y, width, height = box
        targets.append((
            max(0, round(x + offset_x)),
            max(0, round(y + offset_y)),
            max(1, round(width * width_scale)),
            max(1, round(height * height_scale)),
        ))
    return targets


def restore_original_faces(
    *, original_bytes: bytes, generated_bytes: bytes, face_boxes: list[tuple[int, int, int, int]]
) -> bytes:
    """Pixel-anchor detected faces after generation; the provider mask alone is advisory."""
    if not face_boxes:
        return generated_bytes
    with Image.open(io.BytesIO(original_bytes)) as parsed_original:
        original = ImageOps.exif_transpose(parsed_original).convert("RGB")
    with Image.open(io.BytesIO(generated_bytes)) as parsed_generated:
        output_format = parsed_generated.format or "PNG"
        generated = parsed_generated.convert("RGB")
    generated_face_boxes = detect_face_boxes(generated_bytes)
    composed = generated.copy()
    source_faces = list(face_boxes)
    target_faces = _resolve_target_face_boxes(
        source_boxes=source_faces,
        generated_boxes=generated_face_boxes,
        source_size=original.size,
        generated_size=generated.size,
    )
    for source_box, target_box in zip(source_faces, target_faces):
        source_bounds = _expanded_face_box(source_box, original.size)
        target_bounds = _expanded_face_box(target_box, generated.size)
        target_width = target_bounds[2] - target_bounds[0]
        target_height = target_bounds[3] - target_bounds[1]
        source_patch = original.crop(source_bounds).resize((target_width, target_height), Image.Resampling.LANCZOS)
        patch_mask = Image.new("L", (target_width, target_height), 0)
        draw = ImageDraw.Draw(patch_mask)
        inset = max(2, round(min(target_width, target_height) * 0.04))
        draw.ellipse((inset, inset, target_width - inset, target_height - inset), fill=255)
        feather_radius = max(3, round(min(target_width, target_height) * 0.055))
        patch_mask = patch_mask.filter(ImageFilter.GaussianBlur(feather_radius))
        composed.paste(source_patch, target_bounds[:2], patch_mask)
    buffer = io.BytesIO()
    save_format = "JPEG" if output_format.upper() in {"JPEG", "JPG"} else "PNG"
    save_options = {"quality": 95} if save_format == "JPEG" else {}
    composed.save(buffer, format=save_format, **save_options)
    return buffer.getvalue()


def _usage_value(usage: object, *names: str) -> int | None:
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _estimated_cost(*, provider: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Calculate only when deployment-specific rates are deliberately configured."""
    prefix = "IMAGE_EDITOR_GPT" if provider == "azure-openai" else "IMAGE_EDITOR_GEMINI"
    try:
        input_rate = float((os.getenv(f"{prefix}_INPUT_TOKEN_COST_PER_1M_USD") or "").strip())
        output_rate = float((os.getenv(f"{prefix}_OUTPUT_TOKEN_COST_PER_1M_USD") or "").strip())
    except ValueError:
        return None
    if input_tokens is None and output_tokens is None:
        return None
    return round(((input_tokens or 0) * input_rate + (output_tokens or 0) * output_rate) / 1_000_000, 10)


def _generate_with_gpt_image(*, image_bytes: bytes, prompt: str) -> tuple[bytes, dict]:
    from openai import OpenAI

    settings = get_image_editor_provider_settings().gpt_image
    if not settings.is_configured:
        raise ValueError(f"GPT Image configuration is incomplete: {', '.join(settings.missing_fields)}")
    base_url, default_query = _azure_image_client_options(settings.endpoint, settings.api_version)
    client = OpenAI(
        api_key=settings.api_key,
        base_url=base_url,
        default_query=default_query,
    )
    image_file = _as_provider_png(image_bytes)
    face_boxes = detect_face_boxes(image_bytes)
    request_options = dict(
        model=settings.deployment,
        image=image_file,
        prompt=prompt,
        input_fidelity="high",
        quality="high",
    )
    response = client.images.edit(**request_options)
    encoded = response.data[0].b64_json if response.data else None
    if not encoded:
        raise ValueError("GPT Image returned no image data.")
    usage = getattr(response, "usage", None)
    input_tokens = _usage_value(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_value(usage, "output_tokens", "completion_tokens")
    total_tokens = _usage_value(usage, "total_tokens")
    # GPT Image 2's high-fidelity edit path preserves the complete source image.
    # A separate alpha mask produced transparent/black backgrounds on Azure, and
    # detector-based face replacement rejected valid edits on false positives.
    return base64.b64decode(encoded), {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens if total_tokens is not None and total_tokens >= 0 else (
            (input_tokens or 0) + (output_tokens or 0) if input_tokens is not None or output_tokens is not None else None
        ),
        "input_faces_detected": len(face_boxes),
    }


def _generate_with_gemini(
    *,
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    image_size: str = "1K",
) -> tuple[bytes, dict]:
    """Run the waiting-user image flow through Gemini generateContent.

    This is intentionally synchronous. A future whole-shoot flow should use the
    Gemini Batch API at its orchestration boundary rather than routing through
    this single-image function.
    """
    from google import genai
    from google.genai import types

    settings = get_image_editor_provider_settings().gemini
    if not settings.is_configured:
        raise ValueError(f"Gemini configuration is incomplete: {', '.join(settings.missing_fields)}")
    client = genai.Client(api_key=settings.api_key)
    response = client.models.generate_content(
        model=settings.deployment,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size=image_size),
        ),
    )
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if part.inline_data and part.inline_data.data:
                usage = getattr(response, "usage_metadata", None)
                input_tokens = _usage_value(usage, "prompt_token_count", "input_token_count")
                output_tokens = _usage_value(usage, "candidates_token_count", "output_token_count")
                total_tokens = _usage_value(usage, "total_token_count")
                return part.inline_data.data, {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens if total_tokens is not None and total_tokens >= 0 else (
                        (input_tokens or 0) + (output_tokens or 0) if input_tokens is not None or output_tokens is not None else None
                    ),
                    "resolution": image_size,
                }
    raise ValueError("Gemini returned no image data.")


async def generate_ai_image(*, request: AIModeEditRequest, image_bytes: bytes, mime_type: str) -> tuple[bytes, str, str]:
    """Generate one AI edit and return bytes, provider, and model."""
    settings = get_image_editor_provider_settings()
    model = settings.gpt_image.deployment if request.provider == "gpt-image" else settings.gemini.deployment
    if request.provider == "gpt-image":
        result, _ = await asyncio.wait_for(
            asyncio.to_thread(_generate_with_gpt_image, image_bytes=image_bytes, prompt=request.prompt),
            timeout=180,
        )
        return result, "azure-openai", model
    result, _ = await asyncio.wait_for(
        asyncio.to_thread(
            _generate_with_gemini,
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=request.prompt,
            image_size=request.resolution or "1K",
        ),
        timeout=180,
    )
    return result, "google-gemini", model


async def generate_ai_image_with_metrics(*, request: AIModeEditRequest, image_bytes: bytes, mime_type: str) -> tuple[bytes, dict]:
    """Generate an edit while retaining provider usage when the SDK exposes it."""
    settings = get_image_editor_provider_settings()
    is_gpt = request.provider == "gpt-image"
    provider = "azure-openai" if is_gpt else "google-gemini"
    model = settings.gpt_image.deployment if is_gpt else settings.gemini.deployment
    started = time.perf_counter()
    if is_gpt:
        generated_bytes, metrics = await asyncio.wait_for(
            asyncio.to_thread(_generate_with_gpt_image, image_bytes=image_bytes, prompt=request.prompt), timeout=180,
        )
    else:
        generated_bytes, metrics = await asyncio.wait_for(
            asyncio.to_thread(
                _generate_with_gemini,
                image_bytes=image_bytes,
                mime_type=mime_type,
                prompt=request.prompt,
                image_size=request.resolution or "1K",
            ),
            timeout=180,
        )
    metrics["provider"] = provider
    metrics["model"] = model
    metrics["latency_ms"] = round((time.perf_counter() - started) * 1000)
    metrics["estimated_cost_usd"] = _estimated_cost(
        provider=provider, input_tokens=metrics.get("input_tokens"), output_tokens=metrics.get("output_tokens"),
    )
    return generated_bytes, metrics
