"""Background-job orchestration for image editor filter operations."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from backend.app.domain.image_editor_models import ApplyFilterRequest, PersistedFilterResponse
from backend.app.infra.database import get_async_sessionmaker
from backend.app.infra.job_state_store import (
    find_reusable_background_job,
    get_job_state,
    initialize_job_state,
    update_job_state,
)
from backend.app.services.image_editor_persistence_service import apply_filter_from_original_asset
from backend.app.utils.logger import logger


IMAGE_EDITOR_FILTER_QUEUE = "image-editor-filters"


def build_image_editor_payload_hash(*, account_id: str, original_asset_id: str, request: ApplyFilterRequest) -> str:
    payload = (
        f"account_id={account_id}|original_asset_id={original_asset_id}|"
        f"style_id={request.style_id}|intensity_id={request.intensity_id}|"
        f"quality_preset_id={request.quality_preset_id}|"
        f"enabled_control_ids={','.join(sorted(request.enabled_control_ids))}|"
        f"output_format={request.output_format or ''}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def enqueue_filter_apply_job(*, account_id: str, original_asset_id: str, request: ApplyFilterRequest) -> dict[str, str]:
    payload_hash = build_image_editor_payload_hash(
        account_id=account_id,
        original_asset_id=original_asset_id,
        request=request,
    )
    reusable_job_id, reusable_status = find_reusable_background_job(
        queue_name=IMAGE_EDITOR_FILTER_QUEUE,
        account_id=account_id,
        post_limit=None,
        payload_hash=payload_hash,
    )
    if reusable_job_id and reusable_status:
        return {"job_id": reusable_job_id, "status": reusable_status}

    job_id = str(uuid4())
    initialize_job_state(
        job_id=job_id,
        queue_name=IMAGE_EDITOR_FILTER_QUEUE,
        job_name="apply-filter",
        payload={
            "original_asset_id": original_asset_id,
            "request": request.model_dump(mode="python"),
        },
        account_id=account_id,
        source_ref=original_asset_id,
        payload_hash=payload_hash,
    )
    return {"job_id": job_id, "status": "queued"}


async def run_filter_apply_job(*, job_id: str, account_id: str, original_asset_id: str, request: ApplyFilterRequest) -> None:
    update_job_state(
        job_id,
        status="started",
        started_at=datetime.now(timezone.utc).isoformat(),
        progress={"step": "processing", "message": "Applying deterministic filter"},
    )
    async_session = get_async_sessionmaker()
    try:
        async with async_session() as db:
            response = await apply_filter_from_original_asset(
                db=db,
                account_id=account_id,
                original_asset_id=original_asset_id,
                request=request,
            )
        update_job_state(
            job_id,
            status="succeeded",
            finished_at=datetime.now(timezone.utc).isoformat(),
            progress={"step": "completed", "message": "Filter applied"},
            result=_serialize_persisted_response(response),
        )
    except (ValueError, SQLAlchemyError, OSError, RuntimeError) as exc:
        logger.exception("[ImageEditorJob] Filter job failed job_id=%s", job_id)
        update_job_state(
            job_id,
            status="failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error={"message": str(exc)},
        )


def get_image_editor_job_status(job_id: str) -> dict[str, object] | None:
    return get_job_state(job_id)


def _serialize_persisted_response(response: PersistedFilterResponse) -> dict[str, object]:
    return {
        "request_id": response.request_id,
        "result_asset_id": response.result_asset_id,
        "original_asset_id": response.original_asset_id,
        "request_hash": response.request_hash,
        "deduplicated": response.deduplicated,
        "response": response.response.model_dump(mode="python"),
    }
