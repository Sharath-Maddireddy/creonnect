from __future__ import annotations

import base64
import io

from PIL import Image

from backend.app.domain.image_editor_models import ApplyFilterRequest
from backend.app.services.image_editor_config_service import get_image_editor_filter_catalog, get_image_editor_public_config
from backend.app.services.image_editor_filter_service import apply_filter_to_image
from backend.app.services.image_editor_ai_service import compile_ai_edit_prompt
from backend.app.services.image_editor_provider_config import get_image_editor_provider_settings


def _make_image_bytes(size: tuple[int, int] = (24, 16), color: tuple[int, int, int] = (120, 90, 60)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_public_config_exposes_filter_only_metadata() -> None:
    config = get_image_editor_public_config()

    assert config.mode == "filter-only"
    assert config.config_version == "3.0.0-filter-only"
    assert config.supported_modes == ["filter-only", "ai-edit"]
    assert config.ai_edit_available is False
    assert any(style.id == "lofi-dusk" for style in config.styles)
    assert any(control.id == "white-balance" for control in config.controls)


def test_prd_filter_catalog_exposes_safe_original_filters() -> None:
    catalog = get_image_editor_filter_catalog()
    by_id = {item.id: item for item in catalog.filters}

    assert catalog.catalog_version == "1.0.0"
    assert by_id["original-superhero-suit"].campaign_eligible is False
    assert by_id["original-superhero-suit"].mode == "ai-edit"
    assert by_id["authentic-grain"].mode == "deterministic"
    assert by_id["before-after-composite"].requires_secondary_asset is True


def test_catalog_ai_prompt_is_compiled_and_rejects_protected_ip() -> None:
    from backend.app.domain.image_editor_models import AIModeEditRequest

    prompt, filter_id = compile_ai_edit_prompt(
        AIModeEditRequest(
            original_asset_id="asset-1",
            filter_id="original-superhero-suit",
            settings={"color_scheme": "orange and teal", "mask": "yes"},
        )
    )
    assert filter_id == "original-superhero-suit"
    assert "entirely original superhero suit" in prompt

    try:
        compile_ai_edit_prompt(AIModeEditRequest(original_asset_id="asset-1", prompt="Make me Spider-Man"))
    except ValueError as exc:
        assert "protected character" in str(exc)
    else:
        raise AssertionError("Expected protected-IP request to be rejected.")


def test_apply_filter_preserves_dimensions_and_returns_image() -> None:
    request = ApplyFilterRequest(
        style_id="lofi-dusk",
        intensity_id="balanced",
        quality_preset_id="standard",
        enabled_control_ids=["white-balance", "film-grain"],
    )

    response = apply_filter_to_image(_make_image_bytes(), request)

    assert response.width == 24
    assert response.height == 16
    assert response.mode == "filter-only"
    assert response.engine == "pillow-deterministic-filter"
    assert response.image_base64

    decoded = base64.b64decode(response.image_base64)
    result = Image.open(io.BytesIO(decoded))
    assert result.size == (24, 16)


def test_apply_filter_is_deterministic_for_identical_request() -> None:
    request = ApplyFilterRequest(
        style_id="clean-studio",
        intensity_id="subtle",
        quality_preset_id="final",
        enabled_control_ids=["white-balance"],
    )
    image_bytes = _make_image_bytes(color=(90, 120, 150))

    first = apply_filter_to_image(image_bytes, request)
    second = apply_filter_to_image(image_bytes, request)

    assert first.request_hash == second.request_hash
    assert first.image_base64 == second.image_base64


def test_selected_controls_change_the_applied_filter_profile() -> None:
    image_bytes = _make_image_bytes(color=(90, 120, 150))
    without_optional_controls = apply_filter_to_image(
        image_bytes,
        ApplyFilterRequest(style_id="lofi-dusk", enabled_control_ids=[]),
    )
    with_optional_controls = apply_filter_to_image(
        image_bytes,
        ApplyFilterRequest(style_id="lofi-dusk", enabled_control_ids=["white-balance", "film-grain"]),
    )

    assert without_optional_controls.applied_profile["temperature"] == 0.0
    assert without_optional_controls.applied_profile["grain"] == 0.0
    assert with_optional_controls.applied_profile["temperature"] != 0.0
    assert with_optional_controls.applied_profile["grain"] != 0.0
    assert without_optional_controls.image_base64 != with_optional_controls.image_base64


def test_apply_filter_rejects_unsupported_output_format() -> None:
    request = ApplyFilterRequest(style_id="clean-studio", output_format="gif")

    try:
        apply_filter_to_image(_make_image_bytes(), request)
    except ValueError as exc:
        assert "output_format" in str(exc)
    else:
        raise AssertionError("Expected ValueError for an unsupported output format.")


def test_apply_filter_rejects_unknown_control() -> None:
    request = ApplyFilterRequest(
        style_id="clean-studio",
        intensity_id="balanced",
        quality_preset_id="standard",
        enabled_control_ids=["unknown-control"],
    )

    try:
        apply_filter_to_image(_make_image_bytes(), request)
    except ValueError as exc:
        assert "Unknown control_id" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported control.")


def test_image_editor_provider_config_does_not_reuse_shared_azure_credentials(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://existing-text-ai.example")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "existing-text-ai-key")
    monkeypatch.delenv("IMAGE_EDITOR_AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("IMAGE_EDITOR_AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("IMAGE_EDITOR_AZURE_OPENAI_IMAGE_DEPLOYMENT", raising=False)

    settings = get_image_editor_provider_settings()

    assert settings.gpt_image.endpoint == ""
    assert settings.gpt_image.api_key == ""
    assert settings.gpt_image.is_configured is False


def test_image_editor_provider_config_uses_namespaced_credentials(monkeypatch) -> None:
    monkeypatch.setenv("IMAGE_EDITOR_AZURE_OPENAI_ENDPOINT", "https://image-ai.example")
    monkeypatch.setenv("IMAGE_EDITOR_AZURE_OPENAI_API_KEY", "image-ai-key")
    monkeypatch.setenv("IMAGE_EDITOR_AZURE_OPENAI_IMAGE_DEPLOYMENT", "gpt-image-deployment")

    settings = get_image_editor_provider_settings()

    assert settings.gpt_image.endpoint == "https://image-ai.example"
    assert settings.gpt_image.deployment == "gpt-image-deployment"
    assert settings.gpt_image.is_configured is True


def test_image_editor_uses_direct_namespaced_gemini_credentials(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "existing-vision-key")
    monkeypatch.setenv("IMAGE_EDITOR_GEMINI_API_KEY", "image-editor-gemini-key")
    monkeypatch.setenv("IMAGE_EDITOR_GEMINI_MODEL", "gemini-image-model")

    settings = get_image_editor_provider_settings()

    assert settings.gemini.provider == "google-gemini"
    assert settings.gemini.api_key == "image-editor-gemini-key"
    assert settings.gemini.endpoint == ""
    assert settings.gemini.is_configured is True
