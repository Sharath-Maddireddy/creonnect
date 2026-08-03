"""Phase 1 backend-owned image editor routes."""

from __future__ import annotations

import io
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.instagram_auth_routes import AuthenticatedInstagramUser, get_current_instagram_user
from backend.app.domain.image_editor_models import (
    AIModeEditRequest,
    AIModeEditResponse,
    ApplyFilterRequest,
    ApplyFilterResponse,
    ImageEditRecordResponse,
    ImageAssetMetadataResponse,
    ImageEditorConfigResponse,
    ImageEditorFilterCatalogResponse,
    ImageEditJobStatusResponse,
    PersistedFilterResponse,
    UploadImageResponse,
)
from backend.app.infra.database import get_db
from backend.app.services.image_editor_ai_service import compile_ai_edit_prompt
from backend.app.services.image_editor_asset_service import (
    build_asset_metadata_response,
    create_original_asset,
    get_asset_or_404,
    read_asset_bytes,
)
from backend.app.services.image_editor_config_service import get_image_editor_filter_catalog, get_image_editor_public_config
from backend.app.services.image_editor_filter_service import apply_filter_to_image
from backend.app.services.image_editor_persistence_service import (
    apply_filter_from_original_asset,
    get_edit_record_or_404,
    regenerate_filter_request,
    apply_ai_edit_from_original_asset,
)
from backend.app.services.image_editor_job_service import (
    enqueue_filter_apply_job,
    get_image_editor_job_status,
    run_filter_apply_job,
)
from backend.app.utils.logger import logger


router = APIRouter(
    prefix="/api/v1/image-editor",
    tags=["image-editor"],
    dependencies=[Depends(get_current_instagram_user)],
)

MAX_IMAGE_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


async def _read_valid_image_upload(image: UploadFile) -> bytes:
    payload = await image.read(MAX_IMAGE_UPLOAD_BYTES + 1)
    if not payload:
        raise ValueError("Uploaded image is empty.")
    if len(payload) > MAX_IMAGE_UPLOAD_BYTES:
        raise ValueError("Uploaded image exceeds the 15 MB limit.")
    with Image.open(io.BytesIO(payload)) as parsed:
        if parsed.width * parsed.height > MAX_IMAGE_PIXELS:
            raise ValueError("Uploaded image exceeds the 40 megapixel limit.")
        parsed.verify()
    return payload


@router.get("/config", response_model=ImageEditorConfigResponse)
async def get_image_editor_config() -> ImageEditorConfigResponse:
    """Return the backend-controlled image editor config metadata."""
    return get_image_editor_public_config()


@router.get("/filter-catalog", response_model=ImageEditorFilterCatalogResponse)
async def get_image_editor_filter_catalog_endpoint() -> ImageEditorFilterCatalogResponse:
    """Return the PRD-driven filter catalog for the Image Editor UI."""
    return get_image_editor_filter_catalog()


@router.post("/assets", response_model=UploadImageResponse)
async def upload_original_asset(
    image: UploadFile = File(...),
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> UploadImageResponse:
    """Upload and persist an immutable original asset for filter-only editing."""
    try:
        image_bytes = await _read_valid_image_upload(image)
        mime_type = str(image.content_type or "application/octet-stream")
        return await create_original_asset(
            db=db,
            account_id=current_user.id,
            filename=image.filename or "upload",
            mime_type=mime_type,
            image_bytes=image_bytes,
        )
    except (ValueError, UnidentifiedImageError) as exc:
        raise HTTPException(status_code=422, detail=str(exc) or "Unsupported image file.") from exc


@router.get("/assets/{asset_id}", response_model=ImageAssetMetadataResponse)
async def get_asset_metadata_endpoint(
    asset_id: str,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> ImageAssetMetadataResponse:
    """Fetch persisted metadata for an original or derived asset."""
    try:
        asset = await get_asset_or_404(db, current_user.id, asset_id)
        return build_asset_metadata_response(asset)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/assets/{asset_id}/content")
async def get_asset_content_endpoint(
    asset_id: str,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return raw asset bytes for a persisted original or derived asset."""
    try:
        asset = await get_asset_or_404(db, current_user.id, asset_id)
        payload = read_asset_bytes(asset)
        headers = {"Content-Disposition": f'inline; filename="{asset.filename}"'}
        return Response(content=payload, media_type=asset.mime_type, headers=headers)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/filters/apply", response_model=ApplyFilterResponse)
async def apply_filter_endpoint(
    image: UploadFile = File(...),
    style_id: str = Form(...),
    intensity_id: str = Form("balanced"),
    quality_preset_id: str = Form("standard"),
    enabled_control_ids: str = Form(""),
    output_format: str | None = Form(default=None),
) -> ApplyFilterResponse:
    """Apply a deterministic filter-only edit using the backend-owned config."""
    try:
        payload = ApplyFilterRequest(
            style_id=style_id,
            intensity_id=intensity_id,
            quality_preset_id=quality_preset_id,
            enabled_control_ids=[item.strip() for item in enabled_control_ids.split(",") if item.strip()],
            output_format=output_format,
        )
        image_bytes = await _read_valid_image_upload(image)
        logger.info(
            "[ImageEditor] Applying filter style=%s intensity=%s quality=%s filename=%s",
            payload.style_id,
            payload.intensity_id,
            payload.quality_preset_id,
            image.filename,
        )
        return apply_filter_to_image(image_bytes=image_bytes, request=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/filters/apply-from-asset", response_model=PersistedFilterResponse)
async def apply_filter_from_asset_endpoint(
    request: ApplyFilterRequest,
    original_asset_id: str = Query(...),
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> PersistedFilterResponse:
    """Apply a filter from a persisted original asset and save request/result metadata."""
    try:
        return await apply_filter_from_original_asset(
            db=db,
            account_id=current_user.id,
            original_asset_id=original_asset_id,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/filters/jobs")
async def start_filter_apply_job_endpoint(
    background_tasks: BackgroundTasks,
    request: ApplyFilterRequest,
    original_asset_id: str = Query(...),
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> dict[str, str]:
    """Queue a deterministic filter apply operation and return a pollable job id."""
    try:
        job = enqueue_filter_apply_job(
            account_id=current_user.id,
            original_asset_id=original_asset_id,
            request=request,
        )
        if job["status"] == "queued":
            background_tasks.add_task(
                run_filter_apply_job,
                job_id=job["job_id"],
                account_id=current_user.id,
                original_asset_id=original_asset_id,
                request=request,
            )
        return job
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/filters/{request_id}/regenerate", response_model=PersistedFilterResponse)
async def regenerate_filter_endpoint(
    request_id: str,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> PersistedFilterResponse:
    """Regenerate a saved filter request from the immutable original asset."""
    try:
        return await regenerate_filter_request(
            db=db,
            account_id=current_user.id,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ai-edits", response_model=AIModeEditResponse)
async def create_ai_edit_endpoint(
    request: AIModeEditRequest,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> AIModeEditResponse:
    """Run an explicitly requested provider-backed AI edit."""
    try:
        compiled_prompt, filter_id = compile_ai_edit_prompt(request)
        request = request.model_copy(update={"prompt": compiled_prompt, "filter_id": filter_id})
        result = await apply_ai_edit_from_original_asset(
            db=db,
            account_id=current_user.id,
            request=request,
        )
        return AIModeEditResponse(
            mode="ai-edit",
            status="completed",
            message="AI edit completed.",
            **result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[ImageEditor] AI edit failed")
        raise HTTPException(status_code=502, detail="AI image provider request failed.") from exc


@router.get("/jobs/{job_id}", response_model=ImageEditJobStatusResponse)
async def get_image_editor_job_endpoint(
    job_id: str,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> ImageEditJobStatusResponse:
    """Poll the status of a background image editor job."""
    payload = get_image_editor_job_status(job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if payload.get("account_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found.")
    return ImageEditJobStatusResponse.model_validate(payload)


@router.get("/edits/{request_id}", response_model=ImageEditRecordResponse)
async def get_edit_record_endpoint(
    request_id: str,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> ImageEditRecordResponse:
    """Fetch persisted metadata for a saved image edit request."""
    try:
        return await get_edit_record_or_404(
            db=db,
            account_id=current_user.id,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
