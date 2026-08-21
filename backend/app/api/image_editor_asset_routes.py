"""Shared image-editor asset storage routes.

Serves the immutable original/derived assets used by the Creator Image
Editor (and any other feature built on ``image_editor_asset_service``). Kept
at its historical ``/api/v1/image-editor`` prefix so existing stored asset
URLs (e.g. in Creator Image Editor job results) keep resolving.
"""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.instagram_auth_routes import AuthenticatedInstagramUser, get_current_instagram_user
from backend.app.domain.image_editor_models import ImageAssetMetadataResponse, UploadImageResponse
from backend.app.infra.database import get_db
from backend.app.services.image_editor_asset_service import (
    build_asset_metadata_response,
    create_original_asset,
    get_asset_or_404,
    read_asset_bytes,
)

router = APIRouter(
    prefix="/api/v1/image-editor",
    tags=["image-editor-assets"],
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


@router.post("/assets", response_model=UploadImageResponse)
async def upload_original_asset(
    image: UploadFile = File(...),
    current_user: AuthenticatedInstagramUser = Depends(get_current_instagram_user),
    db: AsyncSession = Depends(get_db),
) -> UploadImageResponse:
    """Upload and persist an immutable original asset."""
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
