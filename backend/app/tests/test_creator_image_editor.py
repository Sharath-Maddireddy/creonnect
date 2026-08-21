from __future__ import annotations

import pytest
from types import SimpleNamespace

from backend.app.domain.image_editor_models import CreatorImageGenerationSelection
from backend.app.services.creator_image_editor_config_service import (
    get_creator_image_editor_config,
    validate_creator_image_selection,
)
from backend.app.services.creator_image_filter_prompt_service import get_creator_image_filter_prompt_config
from backend.app.services.creator_image_editor_job_service import (
    _compile_structured_prompt,
    _public_generation_error,
)
from backend.app.services.creator_image_source_service import _validate_public_url
from backend.app.services.image_editor_asset_service import read_asset_bytes
from backend.app.services.image_editor_filter_service import _apply_vignette
from PIL import Image


_BRAND_PRODUCTION_STYLE_IDS = {
    "luxury_product", "brand_kit_color_match", "product_pop_enhancement", "relight",
}
_TRENDING_STYLE_IDS = {
    "lofi_dusk", "sun_kissed", "old_fuji", "y2k_digicam", "disposable_flash",
    "golden_hour_film", "vsco_muted", "polaroid_vintage",
}


def test_creator_editor_config_exposes_prd_v1_choices() -> None:
    config = get_creator_image_editor_config()
    expected_ids = _TRENDING_STYLE_IDS | _BRAND_PRODUCTION_STYLE_IDS
    assert {style.id for style in config.styles} == expected_ids
    assert {style.tag for style in config.styles} == {"evergreen", "rotating"}
    assert {style.id for style in config.styles if style.is_rotating} == {
        "lofi_dusk", "y2k_digicam", "disposable_flash",
    }
    assert {style.category for style in config.styles} == {"brand-production", "trending"}
    assert {style.id for style in config.styles if style.category == "brand-production"} == _BRAND_PRODUCTION_STYLE_IDS
    assert {style.id for style in config.styles if style.category == "trending"} == _TRENDING_STYLE_IDS
    assert {"post", "story", "reel_cover", "ad", "portfolio"} == {goal.id for goal in config.goals}


def test_every_creator_filter_has_a_partial_identity_preserving_prompt() -> None:
    filters = get_creator_image_filter_prompt_config()["filters"]
    assert len(filters) == 12
    for item in filters:
        prompt = item["prompt"].lower()
        assert item["resolution"] == "1K"
        assert "input_fidelity" not in item
        if item["style_id"] in _BRAND_PRODUCTION_STYLE_IDS:
            # Brand-production filters stay tightly identity-locked: subtle,
            # campaign-safe adjustments only.
            assert prompt.startswith("keep the person's face, identity, and features exactly the same")
            assert "partial edit" in prompt
            assert "not a regeneration" in prompt
            assert "only apply" in prompt
        else:
            # Trending filters are allowed a bold, fully-committed transformation
            # as long as the person stays recognizable.
            assert prompt.startswith("keep this person recognizable as the same individual")
            assert "bold" in prompt
            assert "do not change who the person is" in prompt


def test_background_enhancements_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="cannot be selected together"):
        validate_creator_image_selection(
            CreatorImageGenerationSelection(
                goal_id="post",
                style_id="lofi_dusk",
                enhancement_ids=["background_remove", "background_blur"],
            )
        )


def test_provider_prompt_is_compiled_without_creator_free_text() -> None:
    prompt = _compile_structured_prompt(CreatorImageGenerationSelection(goal_id="post", style_id="lofi_dusk"))
    assert "structured UI selections" in prompt
    assert "bold, fully committed style transformation" in prompt
    assert "teal-and-amber dusk color grading" in prompt
    assert prompt.startswith("Keep this person recognizable as the same individual")
    assert "Return one edited version of this exact source" in prompt
    assert "Additional creator direction" not in prompt


def test_brand_production_prompt_stays_identity_locked() -> None:
    prompt = _compile_structured_prompt(CreatorImageGenerationSelection(goal_id="post", style_id="relight"))
    assert "structured UI selections" in prompt
    assert "partial edit of this exact source image, not a regeneration" in prompt
    assert prompt.startswith("Keep the person's face, identity, and features exactly the same")


def test_remote_url_guard_rejects_localhost() -> None:
    with pytest.raises(ValueError, match="private or local"):
        _validate_public_url("http://127.0.0.1/private-image.png")


def test_missing_asset_has_actionable_error() -> None:
    with pytest.raises(ValueError, match="upload the source again"):
        read_asset_bytes(SimpleNamespace(storage_path="C:/definitely-not-present/image.png"))


def test_vignette_preserves_image_dimensions() -> None:
    result = _apply_vignette(Image.new("RGB", (120, 80), "white"), 30)
    assert result.size == (120, 80)


def test_gemini_quota_failure_is_actionable() -> None:
    error = RuntimeError("429 RESOURCE_EXHAUSTED")
    error.status_code = 429

    assert _public_generation_error(error) == {
        "code": "provider_quota_exhausted",
        "message": "Gemini image quota is unavailable. Enable billing or quota for Nano Banana 2, then retry.",
    }


def test_serialize_job_state_never_includes_payload_key() -> None:
    """Regression: public job dicts must not contain a "payload" key at all.

    Not payload:null — the key itself must be absent. Client code that tries to
    read it gets KeyError rather than silently treating null as "empty but valid".
    """
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from backend.app.infra.job_state_store import serialize_job_state

    row = SimpleNamespace(
        job_id="j1", status="failed", queue_name="creator-image-editor",
        job_name="generate-creator-image", account_id="user-A", source_ref="asset-1",
        payload_json={"selection": {"style_id": "lofi_dusk"}, "source_asset_id": "asset-1"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        started_at=None, finished_at=None, progress_json=None, error_json=None,
        result_json=None, warnings_json=[], quality_json=None,
    )

    serialized = serialize_job_state(row)
    assert "payload" not in serialized, (
        "payload key must be absent from serialize_job_state; previous is not allowed"
    )
    assert serialized["job_id"] == "j1"
    assert serialized["status"] == "failed"
    assert serialized["account_id"] == "user-A"


def test_retry_payload_helper_enforces_ownership_and_queue_membership(monkeypatch) -> None:
    """Regression: _get_creator_image_job_payload_for_retry returns None unless
    get_creator_image_job() accepts the (job_id, account_id) pair.

    Uses pytest.monkeypatch for all module-level function overrides.
    """
    from types import SimpleNamespace
    from backend.app.services import creator_image_editor_job_service as job_mod

    fake_payload = {"selection": {"style_id": "lofi_dusk"}, "source_asset_id": "asset-1"}
    fake_row = SimpleNamespace(payload_json=None)  # mutated per-case below
    calls = {}

    def fake_session_factory():
        class _Session:
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *exc):
                return False
            def get(self_inner, model_cls, job_id):
                calls["session_get_job_id"] = job_id
                return fake_row if calls.get("session_should_find") else None
        return _Session()

    monkeypatch.setattr(job_mod, "get_sync_sessionmaker", lambda: fake_session_factory)

    # ---- Case 1: ownership helper says NO (wrong account / wrong queue) ----
    calls.clear(); calls["session_should_find"] = True
    monkeypatch.setattr(job_mod, "get_creator_image_job", lambda *, job_id, account_id: None)
    result = job_mod._get_creator_image_job_payload_for_retry(
        job_id="j1", account_id="attacker-id"
    )
    assert result is None, "Helper must return None when ownership check fails"
    assert "session_get_job_id" not in calls, (
        "Helper must NOT read the DB at all when ownership was rejected"
    )

    # ---- Case 2: ownership passes, but DB row is missing (race / gone) ----
    calls.clear(); calls["session_should_find"] = False
    monkeypatch.setattr(
        job_mod,
        "get_creator_image_job",
        lambda *, job_id, account_id: {"job_id": job_id, "status": "failed"},
    )
    result = job_mod._get_creator_image_job_payload_for_retry(job_id="j1", account_id="user-A")
    assert result is None, "Helper must return None when DB row cannot be loaded"

    # ---- Case 3: ownership passes, DB row present but payload_json is NOT a dict ----
    calls.clear(); calls["session_should_find"] = True
    fake_row.payload_json = "not a dict"
    result = job_mod._get_creator_image_job_payload_for_retry(job_id="j1", account_id="user-A")
    assert result is None, "Helper must return None when persisted payload_json is not a dict"

    # ---- Case 4: acceptance — ownership OK + dict payload => returned DEEP COPY ----
    calls.clear(); calls["session_should_find"] = True
    fake_row.payload_json = {"selection": {"style_id": "lofi_dusk"}, "source_asset_id": "asset-1"}
    result = job_mod._get_creator_image_job_payload_for_retry(job_id="j1", account_id="user-A")
    assert result == fake_payload
    result["selection"]["style_id"] = "HACKED"
    assert fake_row.payload_json["selection"]["style_id"] == "lofi_dusk", (
        "Returned payload must be a DEEP copy so nested mutations cannot touch ORM state"
    )
