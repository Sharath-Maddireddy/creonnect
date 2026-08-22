"""Persistence workflow for backend-owned image editor AI-edit requests/results."""

from __future__ import annotations

import hashlib
import io
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image

from backend.app.infra.models import ImageEditRequestRecord, ImageEditResultRecord
from backend.app.services.image_editor_asset_service import create_derived_asset, get_asset_or_404, read_asset_bytes
from backend.app.services.image_editor_ai_service import generate_ai_image


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
                json.dumps(request.settings, sort_keys=True, separators=(",", ":"), default=str).encode(),
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
