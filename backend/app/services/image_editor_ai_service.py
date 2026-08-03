"""Provider calls for the explicit AI-edit mode."""

from __future__ import annotations

import asyncio
import base64
import io

from PIL import Image

from backend.app.domain.image_editor_models import AIModeEditRequest, AIModeEditResponse
from backend.app.services.image_editor_config_service import get_image_editor_catalog_filter
from backend.app.services.image_editor_provider_config import get_image_editor_provider_settings


_PROTECTED_IP_TERMS = (
    "spider-man", "spiderman", "marvel", "disney", "dc comics", "batman", "superman", "iron man",
)


def compile_ai_edit_prompt(request: AIModeEditRequest) -> tuple[str, str | None]:
    """Compile catalog prompts on the server and reject protected-IP requests."""
    user_text = (request.prompt or "").strip()
    normalized = user_text.lower()
    if any(term in normalized for term in _PROTECTED_IP_TERMS):
        raise ValueError("This editor supports original transformations only; protected character or franchise requests are not allowed.")
    if not request.filter_id:
        if not user_text:
            raise ValueError("Enter an AI edit instruction or choose a catalog filter.")
        return user_text, None

    catalog_filter = get_image_editor_catalog_filter(request.filter_id)
    if catalog_filter.mode != "ai-edit":
        raise ValueError(f"{catalog_filter.label} is not an AI-edit filter.")
    unexpected = sorted(set(request.settings) - set(catalog_filter.settings))
    if unexpected:
        raise ValueError(f"Unsupported settings for {catalog_filter.label}: {', '.join(unexpected)}")
    settings_text = "; ".join(
        f"{key.replace('_', ' ')}: {str(value).strip()[:160]}"
        for key, value in sorted(request.settings.items())
        if str(value).strip()
    )
    prompt = (
        f"Apply the Creonnect {catalog_filter.label} transformation. {catalog_filter.description} "
        "Preserve the subject identity, the original product, and image composition unless this filter explicitly changes clothing or illustration style. "
        "Do not add copyrighted characters, third-party logos, or trademarked costume designs."
    )
    if catalog_filter.id == "original-superhero-suit":
        prompt += " Use an entirely original superhero suit design with no resemblance to any existing franchise character."
    if settings_text:
        prompt += f" Requested settings: {settings_text}."
    if user_text:
        prompt += f" Additional creator direction: {user_text}."
    return prompt, catalog_filter.id


def _generate_with_gpt_image(*, image_bytes: bytes, prompt: str) -> bytes:
    from openai import OpenAI

    settings = get_image_editor_provider_settings().gpt_image
    if not settings.is_configured:
        raise ValueError(f"GPT Image configuration is incomplete: {', '.join(settings.missing_fields)}")
    client = OpenAI(
        api_key=settings.api_key,
        base_url=f"{settings.endpoint.rstrip('/')}/openai/v1/",
    )
    image_file = io.BytesIO(image_bytes)
    image_file.name = "original.png"
    response = client.images.edit(
        model=settings.deployment,
        image=image_file,
        prompt=prompt,
    )
    encoded = response.data[0].b64_json if response.data else None
    if not encoded:
        raise ValueError("GPT Image returned no image data.")
    return base64.b64decode(encoded)


def _generate_with_gemini(*, image_bytes: bytes, mime_type: str, prompt: str) -> bytes:
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
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if part.inline_data and part.inline_data.data:
                return part.inline_data.data
    raise ValueError("Gemini returned no image data.")


async def generate_ai_image(*, request: AIModeEditRequest, image_bytes: bytes, mime_type: str) -> tuple[bytes, str, str]:
    """Generate one AI edit and return bytes, provider, and model."""
    settings = get_image_editor_provider_settings()
    model = settings.gpt_image.deployment if request.provider == "gpt-image" else settings.gemini.deployment
    if request.provider == "gpt-image":
        result = await asyncio.to_thread(_generate_with_gpt_image, image_bytes=image_bytes, prompt=request.prompt)
        return result, "azure-openai", model
    result = await asyncio.to_thread(
        _generate_with_gemini,
        image_bytes=image_bytes,
        mime_type=mime_type,
        prompt=request.prompt,
    )
    return result, "google-gemini", model


def create_ai_edit_placeholder_response(request: AIModeEditRequest) -> AIModeEditResponse:
    """Retained for callers that explicitly request the old placeholder behavior."""
    return AIModeEditResponse(
        mode="ai-edit",
        status="not-enabled",
        message=(
            "AI edit mode is not enabled in this backend yet. "
            "Use filter-only mode for deterministic edits."
        ),
    )
