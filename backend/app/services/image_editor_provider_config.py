"""Isolated provider configuration for generative image editing."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageProviderSettings:
    """Credentials and deployment metadata for one image-edit provider."""

    provider: str
    endpoint: str
    api_key: str
    deployment: str
    api_version: str = ""
    requires_endpoint: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(
            self.api_key
            and self.deployment
            and (self.endpoint or not self.requires_endpoint)
        )

    @property
    def missing_fields(self) -> tuple[str, ...]:
        values = {"api_key": self.api_key, "deployment": self.deployment}
        if self.requires_endpoint:
            values["endpoint"] = self.endpoint
        return tuple(name for name, value in values.items() if not value)


@dataclass(frozen=True)
class ImageEditorProviderSettings:
    """All AI providers available exclusively to the image editor."""

    gpt_image: ImageProviderSettings
    gemini: ImageProviderSettings


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def get_image_editor_provider_settings() -> ImageEditorProviderSettings:
    """Load namespaced credentials without reading shared text-AI variables.

    The existing AZURE_OPENAI_* settings may point to a text model deployment.
    Keeping image credentials under IMAGE_EDITOR_AZURE_* prevents image requests
    from changing or accidentally targeting that deployment.
    """
    return ImageEditorProviderSettings(
        gpt_image=ImageProviderSettings(
            provider="azure-openai",
            endpoint=_env("IMAGE_EDITOR_AZURE_OPENAI_ENDPOINT"),
            api_key=_env("IMAGE_EDITOR_AZURE_OPENAI_API_KEY"),
            deployment=_env("IMAGE_EDITOR_AZURE_OPENAI_IMAGE_DEPLOYMENT"),
            api_version=_env("IMAGE_EDITOR_AZURE_OPENAI_API_VERSION"),
        ),
        gemini=ImageProviderSettings(
            provider="google-gemini",
            endpoint="",
            api_key=_env("IMAGE_EDITOR_GEMINI_API_KEY"),
            deployment=_env("IMAGE_EDITOR_GEMINI_MODEL"),
            requires_endpoint=False,
        ),
    )


def get_image_editor_generation_provider(settings: ImageEditorProviderSettings | None = None) -> str:
    """Resolve the explicitly selected provider for Creator Image Editor jobs."""
    configured = settings or get_image_editor_provider_settings()
    preferred = _env("IMAGE_EDITOR_GENERATION_PROVIDER").lower() or "gemini"
    aliases = {
        "gpt": "gpt-image",
        "gpt-image": "gpt-image",
        "azure-openai": "gpt-image",
        "gemini": "gemini",
        "google-gemini": "gemini",
    }
    provider = aliases.get(preferred)
    if provider is None:
        raise ValueError("IMAGE_EDITOR_GENERATION_PROVIDER must be gpt-image or gemini")
    provider_settings = configured.gpt_image if provider == "gpt-image" else configured.gemini
    if not provider_settings.is_configured:
        raise ValueError(f"Selected image editor provider is not configured: {provider}")
    return provider
