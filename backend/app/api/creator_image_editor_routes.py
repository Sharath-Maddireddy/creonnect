"""PRD v1 routes for the structured Creator Image Editor.

This router is intentionally separate from the legacy ``/image-editor`` API so
the existing deterministic editor can stay live during the migration.
"""

import io
import json
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener

from backend.app.api.instagram_auth_routes import AuthenticatedInstagramUser, get_current_instagram_user
from backend.app.domain.image_editor_models import (
    CreatorImageEditorConfigResponse,
    CreatorImageGenerationSelection,
    CreatorImageJobResponse,
    CreatorImageUrlJobRequest,
)
from backend.app.services.creator_image_editor_config_service import get_creator_image_editor_config
from backend.app.services.creator_image_editor_job_service import (
    _get_creator_image_job_payload_for_retry,
    cancel_creator_image_job,
    create_creator_image_job,
    find_creator_image_job_by_idempotency,
    get_creator_image_job,
    list_creator_image_jobs,
    run_creator_image_job,
)
from backend.app.services.image_editor_asset_service import create_original_asset
from backend.app.services.creator_image_source_service import fetch_remote_image
from backend.app.infra.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(
    prefix="/api/v1/creator/image-editor",
    tags=["creator-image-editor"],
    dependencies=[Depends(get_current_instagram_user)],
)


@router.get("/config", response_model=CreatorImageEditorConfigResponse)
async def get_creator_image_editor_config_endpoint() -> CreatorImageEditorConfigResponse:
    """Return the only selectable inputs for structured generation."""
    return get_creator_image_editor_config()


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
register_heif_opener()


async def _read_image(image: UploadFile) -> tuple[bytes, str, str]:
    data = await image.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise ValueError("Uploaded image is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded image exceeds the 25 MB limit.")
    with Image.open(io.BytesIO(data)) as parsed:
        parsed.verify()
    mime_type = str(image.content_type or "image/png").lower()
    filename = image.filename or "upload"
    if mime_type in {"image/heic", "image/heif"} or filename.lower().endswith((".heic", ".heif")):
        with Image.open(io.BytesIO(data)) as parsed:
            converted = io.BytesIO()
            parsed.convert("RGB").save(converted, format="JPEG", quality=92)
        return converted.getvalue(), "image/jpeg", f"{filename.rsplit('.', 1)[0]}.jpg"
    return data, mime_type, filename


def _to_response(job: dict) -> CreatorImageJobResponse:
    status = {"started": "processing"}.get(str(job.get("status")), str(job.get("status")))
    result = job.get("result") or {}
    progress = job.get("progress") or {}
    progress_stage = str(progress["stage"]) if progress.get("stage") else None
    if status == "failed":
        progress_stage = "Generation failed"
    source_asset_id = result.get("source_asset_id") or job.get("source_ref")
    result_asset_id = result.get("result_asset_id")
    asset_url = lambda asset_id: f"/api/v1/image-editor/assets/{asset_id}/content" if asset_id else None
    candidates = [
        {
            **candidate,
            "result_url": asset_url(candidate.get("result_asset_id")),
        }
        for candidate in result.get("candidates", [])
    ]
    return CreatorImageJobResponse(
        id=str(job["job_id"]),
        status=status,
        progress_percent=int(progress.get("percent", 0)),
        progress_stage=progress_stage,
        next_poll_after_ms=3500 if status in {"queued", "processing"} else None,
        retry_allowed=status == "failed",
        cancel_allowed=status in {"queued", "processing"},
        source_url=asset_url(source_asset_id),
        result_url=asset_url(result_asset_id),
        thumbnail_url=asset_url(result_asset_id),
        candidates=candidates,
        error=job.get("error"),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
    )


@router.post("/jobs", response_model=CreatorImageJobResponse, status_code=202)
async def create_creator_image_job_endpoint(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    goal_id: str = Form(...),
    style_id: str = Form(...),
    event_id: str = Form("none"),
    enhancement_ids: str = Form("[]"),
    output_format: str = Form("png"),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> CreatorImageJobResponse:
    """Create one structured, idempotent creator-image generation job."""
    try:
        existing = find_creator_image_job_by_idempotency(account_id=current_user.id, idempotency_key=idempotency_key)
        if existing:
            return _to_response(existing)
        parsed_enhancements = json.loads(enhancement_ids)
        if not isinstance(parsed_enhancements, list) or not all(isinstance(item, str) for item in parsed_enhancements):
            raise ValueError("enhancement_ids must be a JSON array of strings.")
        selection = CreatorImageGenerationSelection(
            goal_id=goal_id, style_id=style_id, event_id=event_id,
            enhancement_ids=parsed_enhancements, output_format=output_format,
        )
        image_bytes, mime_type, filename = await _read_image(image)
        source = await create_original_asset(
            db=db, account_id=current_user.id, filename=filename, mime_type=mime_type, image_bytes=image_bytes,
        )
        job, created = create_creator_image_job(
            account_id=current_user.id, source_asset_id=source.asset_id,
            selection=selection, idempotency_key=idempotency_key,
        )
        if created:
            background_tasks.add_task(
                run_creator_image_job, job_id=job["job_id"], account_id=current_user.id,
                source_asset_id=source.asset_id, selection=selection,
            )
        return _to_response(job)
    except (ValueError, UnidentifiedImageError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/jobs/from-url", response_model=CreatorImageJobResponse, status_code=202)
async def create_creator_image_url_job_endpoint(
    request: CreatorImageUrlJobRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> CreatorImageJobResponse:
    """Create a structured generation job from a validated public image URL."""
    try:
        existing = find_creator_image_job_by_idempotency(account_id=current_user.id, idempotency_key=idempotency_key)
        if existing:
            return _to_response(existing)
        image_bytes, mime_type, filename = await fetch_remote_image(request.source_url)
        source = await create_original_asset(
            db=db, account_id=current_user.id, filename=filename, mime_type=mime_type, image_bytes=image_bytes,
        )
        selection = CreatorImageGenerationSelection.model_validate(request.model_dump(exclude={"source_url"}))
        job, created = create_creator_image_job(
            account_id=current_user.id, source_asset_id=source.asset_id,
            selection=selection, idempotency_key=idempotency_key,
        )
        if created:
            background_tasks.add_task(
                run_creator_image_job, job_id=job["job_id"], account_id=current_user.id,
                source_asset_id=source.asset_id, selection=selection,
            )
        return _to_response(job)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs/{job_id}", response_model=CreatorImageJobResponse)
async def get_creator_image_job_endpoint(
    job_id: str, response: Response,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> CreatorImageJobResponse | Response:
    job = get_creator_image_job(job_id=job_id, account_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    # Job state must never be served from a browser cache.  Conditional 304
    # responses can stop a timer-driven client from observing completion.
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return _to_response(job)


@router.get("/jobs", response_model=list[CreatorImageJobResponse])
async def list_creator_image_jobs_endpoint(
    limit: int = Query(20, ge=1, le=100), skip: int = Query(0, ge=0),
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> list[CreatorImageJobResponse]:
    return [_to_response(job) for job in list_creator_image_jobs(account_id=current_user.id, limit=limit, skip=skip)]


@router.post("/jobs/{job_id}/cancel", response_model=CreatorImageJobResponse)
async def cancel_creator_image_job_endpoint(
    job_id: str, current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> CreatorImageJobResponse:
    job = cancel_creator_image_job(job_id=job_id, account_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    return _to_response(job)


@router.post("/jobs/{job_id}/retry", response_model=CreatorImageJobResponse, status_code=202)
async def retry_creator_image_job_endpoint(
    job_id: str, background_tasks: BackgroundTasks,
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
) -> CreatorImageJobResponse:
    previous = get_creator_image_job(job_id=job_id, account_id=current_user.id)
    if not previous:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    if previous["status"] != "failed":
        raise HTTPException(status_code=409, detail="Only failed generation jobs can be retried.")
    payload = _get_creator_image_job_payload_for_retry(job_id=job_id, account_id=current_user.id) or {}
    try:
        selection = CreatorImageGenerationSelection.model_validate(payload["selection"])
        source_asset_id = str(payload["source_asset_id"])
        job, _ = create_creator_image_job(
            account_id=current_user.id, source_asset_id=source_asset_id, selection=selection,
            idempotency_key=f"retry:{job_id}:{uuid4()}",
        )
        background_tasks.add_task(
            run_creator_image_job, job_id=job["job_id"], account_id=current_user.id,
            source_asset_id=source_asset_id, selection=selection,
        )
        return _to_response(job)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="The saved generation cannot be retried.") from exc
