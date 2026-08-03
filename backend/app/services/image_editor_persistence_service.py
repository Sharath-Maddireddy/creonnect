"""Persistence workflow for backend-owned image editor requests/results."""

from __future__ import annotations

import base64
import hashlib
import io
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image

from backend.app.domain.image_editor_models import (
    ApplyFilterRequest,
    ApplyFilterResponse,
    ImageEditRecordResponse,
    PersistedFilterResponse,
)
from backend.app.infra.models import ImageEditRequestRecord, ImageEditResultRecord
from backend.app.services.image_editor_asset_service import create_derived_asset, get_asset_or_404, read_asset_bytes
from backend.app.services.image_editor_config_service import get_image_editor_public_config
from backend.app.services.image_editor_filter_service import apply_filter_to_image, build_filter_request_hash
from backend.app.services.image_editor_ai_service import generate_ai_image


async def apply_filter_from_original_asset(
    *,
    db: AsyncSession,
    account_id: str,
    original_asset_id: str,
    request: ApplyFilterRequest,
) -> PersistedFilterResponse:
    original_asset = await get_asset_or_404(db, account_id, original_asset_id)
    original_bytes = read_asset_bytes(original_asset)
    request_hash = build_filter_request_hash(request, original_asset.width, original_asset.height)

    existing_request_result = await db.execute(
        select(ImageEditRequestRecord, ImageEditResultRecord)
        .join(ImageEditResultRecord, ImageEditResultRecord.request_id == ImageEditRequestRecord.id)
        .where(
            ImageEditRequestRecord.account_id == account_id,
            ImageEditRequestRecord.original_asset_id == original_asset_id,
            ImageEditRequestRecord.request_hash == request_hash,
        )
        .order_by(ImageEditRequestRecord.created_at.desc())
    )
    existing_pair = existing_request_result.first()
    if existing_pair is not None:
        existing_request, existing_result = existing_pair
        result_asset = await get_asset_or_404(db, account_id, existing_result.result_asset_id)
        persisted_response = _build_apply_response_from_persisted(
            result_asset=result_asset,
            request_row=existing_request,
        )
        return PersistedFilterResponse(
            request_id=existing_request.id,
            result_asset_id=result_asset.id,
            original_asset_id=original_asset_id,
            request_hash=request_hash,
            deduplicated=True,
            response=persisted_response,
        )

    applied = apply_filter_to_image(original_bytes, request)
    derived_bytes = base64.b64decode(applied.image_base64)

    result_asset = await create_derived_asset(
        db=db,
        account_id=account_id,
        original_asset_id=original_asset_id,
        parent_asset_id=original_asset_id,
        output_format=applied.output_format,
        image_bytes=derived_bytes,
        width=applied.width,
        height=applied.height,
    )

    request_id = str(uuid4())
    request_row = ImageEditRequestRecord(
        id=request_id,
        account_id=account_id,
        original_asset_id=original_asset_id,
        source_asset_id=original_asset_id,
        mode=applied.mode,
        engine=applied.engine,
        config_version=applied.config_version,
        request_hash=request_hash,
        style_id=request.style_id,
        intensity_id=request.intensity_id,
        quality_preset_id=request.quality_preset_id,
        enabled_control_ids=list(request.enabled_control_ids),
        output_format=request.output_format,
        applied_profile_json=applied.applied_profile,
        warnings_json=[warning.model_dump() for warning in applied.warnings],
    )
    result_row = ImageEditResultRecord(
        id=str(uuid4()),
        request_id=request_id,
        result_asset_id=result_asset.id,
        mime_type=result_asset.mime_type,
        width=result_asset.width,
        height=result_asset.height,
        output_format=applied.output_format,
    )
    db.add(request_row)
    db.add(result_row)
    await db.commit()

    return PersistedFilterResponse(
        request_id=request_row.id,
        result_asset_id=result_asset.id,
        original_asset_id=original_asset_id,
        request_hash=request_hash,
        deduplicated=False,
        response=applied,
    )


async def apply_ai_edit_from_original_asset(
    *,
    db: AsyncSession,
    account_id: str,
    request,
) -> dict:
    """Generate and persist an explicit AI edit, deduplicating exact requests."""
    original_asset = await get_asset_or_404(db, account_id, request.original_asset_id)
    original_bytes = read_asset_bytes(original_asset)
    request_hash = hashlib.sha256(
        b"|".join(
            [
                original_asset.sha256.encode(),
                request.provider.encode(),
                (request.filter_id or "custom").encode(),
                request.prompt.strip().encode(),
            ]
        )
    ).hexdigest()
    existing = await db.execute(
        select(ImageEditRequestRecord, ImageEditResultRecord)
        .join(ImageEditResultRecord, ImageEditResultRecord.request_id == ImageEditRequestRecord.id)
        .where(
            ImageEditRequestRecord.account_id == account_id,
            ImageEditRequestRecord.original_asset_id == request.original_asset_id,
            ImageEditRequestRecord.request_hash == request_hash,
        )
    )
    existing_pair = existing.first()
    if existing_pair is not None:
        existing_request, existing_result = existing_pair
        return {
            "request_id": existing_request.id,
            "result_asset_id": existing_result.result_asset_id,
            "provider": existing_request.applied_profile_json.get("provider"),
            "model": existing_request.applied_profile_json.get("model"),
            "deduplicated": True,
        }

    generated_bytes, provider, model = await generate_ai_image(
        request=request,
        image_bytes=original_bytes,
        mime_type=original_asset.mime_type,
    )
    image = Image.open(io.BytesIO(generated_bytes))
    output_format = (image.format or "PNG").lower()
    if output_format == "jpeg":
        output_format = "jpg"
    result_asset = await create_derived_asset(
        db=db,
        account_id=account_id,
        original_asset_id=request.original_asset_id,
        parent_asset_id=request.original_asset_id,
        output_format=output_format,
        image_bytes=generated_bytes,
        width=image.width,
        height=image.height,
    )
    request_id = str(uuid4())
    request_row = ImageEditRequestRecord(
        id=request_id,
        account_id=account_id,
        original_asset_id=request.original_asset_id,
        source_asset_id=request.original_asset_id,
        mode="ai-edit",
        engine=provider,
        config_version="ai-provider-v1",
        request_hash=request_hash,
        style_id="ai-prompt",
        intensity_id="provider-default",
        quality_preset_id="provider-default",
        enabled_control_ids=[],
        output_format=output_format,
        prompt=request.prompt,
        applied_profile_json={
            "provider": provider,
            "model": model,
            "filter_id": request.filter_id,
            "settings": request.settings,
        },
        warnings_json=[],
    )
    result_row = ImageEditResultRecord(
        id=str(uuid4()),
        request_id=request_id,
        result_asset_id=result_asset.id,
        mime_type=result_asset.mime_type,
        width=result_asset.width,
        height=result_asset.height,
        output_format=output_format,
    )
    db.add(request_row)
    db.add(result_row)
    await db.commit()
    return {
        "request_id": request_id,
        "result_asset_id": result_asset.id,
        "provider": provider,
        "model": model,
        "deduplicated": False,
    }


async def regenerate_filter_request(
    *,
    db: AsyncSession,
    account_id: str,
    request_id: str,
) -> PersistedFilterResponse:
    result = await db.execute(
        select(ImageEditRequestRecord).where(
            ImageEditRequestRecord.id == request_id,
            ImageEditRequestRecord.account_id == account_id,
        )
    )
    request_row = result.scalar_one_or_none()
    if not request_row:
        raise ValueError("Image edit request not found.")

    request = ApplyFilterRequest(
        style_id=request_row.style_id,
        intensity_id=request_row.intensity_id,
        quality_preset_id=request_row.quality_preset_id,
        enabled_control_ids=list(request_row.enabled_control_ids or []),
        output_format=request_row.output_format,
    )
    return await apply_filter_from_original_asset(
        db=db,
        account_id=account_id,
        original_asset_id=request_row.original_asset_id,
        request=request,
    )


async def get_edit_record_or_404(
    *,
    db: AsyncSession,
    account_id: str,
    request_id: str,
) -> ImageEditRecordResponse:
    result = await db.execute(
        select(ImageEditRequestRecord, ImageEditResultRecord)
        .join(ImageEditResultRecord, ImageEditResultRecord.request_id == ImageEditRequestRecord.id)
        .where(
            ImageEditRequestRecord.id == request_id,
            ImageEditRequestRecord.account_id == account_id,
        )
    )
    pair = result.first()
    if pair is None:
        raise ValueError("Image edit request not found.")
    request_row, result_row = pair
    return ImageEditRecordResponse(
        request_id=request_row.id,
        account_id=request_row.account_id,
        original_asset_id=request_row.original_asset_id,
        result_asset_id=result_row.result_asset_id,
        style_id=request_row.style_id,
        intensity_id=request_row.intensity_id,
        quality_preset_id=request_row.quality_preset_id,
        enabled_control_ids=list(request_row.enabled_control_ids or []),
        request_hash=request_row.request_hash,
        mode=request_row.mode,
        engine=request_row.engine,
        config_version=request_row.config_version,
        created_at=request_row.created_at.isoformat() if request_row.created_at else None,
    )


def _build_apply_response_from_persisted(*, result_asset, request_row: ImageEditRequestRecord) -> ApplyFilterResponse:
    image_base64 = base64.b64encode(read_asset_bytes(result_asset)).decode("ascii")
    public_config = get_image_editor_public_config()
    return ApplyFilterResponse(
        config_version=request_row.config_version or public_config.config_version,
        mode=request_row.mode,
        engine=request_row.engine,
        request_hash=request_row.request_hash,
        mime_type=result_asset.mime_type,
        width=result_asset.width,
        height=result_asset.height,
        output_format=request_row.output_format or "png",
        image_base64=image_base64,
        warnings=[],
        applied_profile=dict(request_row.applied_profile_json or {}),
    )
