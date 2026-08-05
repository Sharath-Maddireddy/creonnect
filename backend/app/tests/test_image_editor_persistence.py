from __future__ import annotations

import asyncio
import io
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from starlette.middleware.sessions import SessionMiddleware

from backend.app.api.image_editor_routes import router as image_editor_router
from backend.app.api.instagram_auth_routes import get_current_instagram_user
from backend.app.infra.database import init_db, reset_database_engines_async


def _make_png_bytes(size: tuple[int, int] = (20, 12), color: tuple[int, int, int] = (110, 80, 50)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _build_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./backend/test_image_editor.db")
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-session-secret", same_site="lax")
    app.dependency_overrides[get_current_instagram_user] = lambda: type(
        "AuthUser",
        (),
        {"id": "acct-test", "username": "tester"},
    )()
    app.include_router(image_editor_router)

    @app.on_event("startup")
    async def _startup() -> None:
        await reset_database_engines_async()
        await init_db(strict=True)

    return TestClient(app)


def test_upload_apply_persist_and_regenerate(monkeypatch) -> None:
    db_path = Path("backend/test_image_editor.db")
    if db_path.exists():
        db_path.unlink()

    client = _build_client(monkeypatch)

    async def _fake_ai_image(*, request, image_bytes, mime_type):
        return _make_png_bytes(size=(20, 12), color=(20, 30, 40)), "azure-openai", "gpt-image-2"

    monkeypatch.setattr(
        "backend.app.services.image_editor_persistence_service.generate_ai_image",
        _fake_ai_image,
    )
    with client:
        upload_response = client.post(
            "/api/v1/image-editor/assets",
            files={"image": ("sample.png", _make_png_bytes(), "image/png")},
        )
        assert upload_response.status_code == 200
        asset_id = upload_response.json()["asset_id"]

        asset_metadata_response = client.get(f"/api/v1/image-editor/assets/{asset_id}")
        assert asset_metadata_response.status_code == 200
        assert asset_metadata_response.json()["asset_id"] == asset_id
        assert asset_metadata_response.json()["is_original"] is True

        asset_content_response = client.get(f"/api/v1/image-editor/assets/{asset_id}/content")
        assert asset_content_response.status_code == 200
        assert asset_content_response.headers["content-type"].startswith("image/png")
        assert len(asset_content_response.content) > 0

        apply_response = client.post(
            f"/api/v1/image-editor/filters/apply-from-asset?original_asset_id={asset_id}",
            json={
                "style_id": "lofi-dusk",
                "intensity_id": "balanced",
                "quality_preset_id": "standard",
                "enabled_control_ids": ["white-balance", "film-grain"],
            },
        )
        assert apply_response.status_code == 200, apply_response.text
        apply_payload = apply_response.json()
        request_id = apply_payload["request_id"]
        first_result_asset_id = apply_payload["result_asset_id"]
        assert apply_payload["deduplicated"] is False

        duplicate_response = client.post(
            f"/api/v1/image-editor/filters/apply-from-asset?original_asset_id={asset_id}",
            json={
                "style_id": "lofi-dusk",
                "intensity_id": "balanced",
                "quality_preset_id": "standard",
                "enabled_control_ids": ["white-balance", "film-grain"],
            },
        )
        assert duplicate_response.status_code == 200
        duplicate_payload = duplicate_response.json()
        assert duplicate_payload["deduplicated"] is True
        assert duplicate_payload["request_id"] == request_id
        assert duplicate_payload["result_asset_id"] == first_result_asset_id

        result_asset_metadata_response = client.get(f"/api/v1/image-editor/assets/{first_result_asset_id}")
        assert result_asset_metadata_response.status_code == 200
        assert result_asset_metadata_response.json()["original_asset_id"] == asset_id
        assert result_asset_metadata_response.json()["is_original"] is False

        job_start_response = client.post(
            f"/api/v1/image-editor/filters/jobs?original_asset_id={asset_id}",
            json={
                "style_id": "clean-studio",
                "intensity_id": "subtle",
                "quality_preset_id": "final",
                "enabled_control_ids": ["white-balance"],
            },
        )
        assert job_start_response.status_code == 200
        job_payload = job_start_response.json()
        assert "job_id" in job_payload

        job_status_response = client.get(f"/api/v1/image-editor/jobs/{job_payload['job_id']}")
        assert job_status_response.status_code == 200
        job_status_payload = job_status_response.json()
        assert job_status_payload["status"] in {"queued", "started", "succeeded"}
        assert job_status_payload["queue_name"] == "image-editor-filters"
        if job_status_payload["status"] == "succeeded":
            assert "result" in job_status_payload

        ai_edit_response = client.post(
            "/api/v1/image-editor/ai-edits",
            json={
                "original_asset_id": asset_id,
                "prompt": "Remove the wall and replace the product with a new one.",
            },
        )
        assert ai_edit_response.status_code == 200
        ai_edit_payload = ai_edit_response.json()
        assert ai_edit_payload["mode"] == "ai-edit"
        assert ai_edit_payload["status"] == "completed"
        assert ai_edit_payload["provider"] == "azure-openai"
        assert ai_edit_payload["model"] == "gpt-image-2"

        repeated_ai_response = client.post(
            "/api/v1/image-editor/ai-edits",
            json={
                "original_asset_id": asset_id,
                "prompt": "Remove the wall and replace the product with a new one.",
            },
        )
        assert repeated_ai_response.status_code == 200
        assert repeated_ai_response.json()["deduplicated"] is True
        assert repeated_ai_response.json()["result_asset_id"] == ai_edit_payload["result_asset_id"]

        record_response = client.get(f"/api/v1/image-editor/edits/{request_id}")
        assert record_response.status_code == 200
        assert record_response.json()["original_asset_id"] == asset_id

        regenerate_response = client.post(f"/api/v1/image-editor/filters/{request_id}/regenerate")
        assert regenerate_response.status_code == 200
        regenerate_payload = regenerate_response.json()
        assert regenerate_payload["deduplicated"] is True
        assert regenerate_payload["result_asset_id"] == first_result_asset_id

    asyncio.run(reset_database_engines_async())
    if db_path.exists():
        db_path.unlink()
