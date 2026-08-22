"""Persistence and local storage helpers for Phase 1 image editor assets."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.image_editor_models import ImageAssetMetadataResponse, UploadImageResponse
from backend.app.infra.models import ImageAsset


_ASSET_ROOT = Path(__file__).resolve().parents[2] / ".image_editor_assets"


def _ensure_asset_root() -> None:
    _ASSET_ROOT.mkdir(parents=True, exist_ok=True)


def _extension_for_mime(mime_type: str) -> str:
    mime = (mime_type or "").lower()
    if mime == "image/png":
        return ".png"
    if mime in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".bin"


def _guess_mime_from_format(fmt: str) -> str:
    normalized = (fmt or "").lower()
    if normalized == "png":
        return "image/png"
    if normalized in {"jpg", "jpeg"}:
        return "image/jpeg"
    if normalized == "webp":
        return "image/webp"
    return "application/octet-stream"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_bytes(account_id: str, asset_id: str, mime_type: str, payload: bytes) -> str:
    _ensure_asset_root()
    account_dir = _ASSET_ROOT / str(account_id)
    account_dir.mkdir(parents=True, exist_ok=True)
    target = account_dir / f"{asset_id}{_extension_for_mime(mime_type)}"
    target.write_bytes(payload)
    return str(target)


async def create_original_asset(
    *,
    db: AsyncSession,
    account_id: str,
    filename: str,
    mime_type: str,
    image_bytes: bytes,
) -> UploadImageResponse:
    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)
    width, height = image.size
    asset_id = str(uuid4())
    storage_path = _write_bytes(account_id, asset_id, mime_type, image_bytes)
    asset = ImageAsset(
        id=asset_id,
        account_id=account_id,
        original_asset_id=None,
        parent_asset_id=None,
        filename=filename or f"{asset_id}{_extension_for_mime(mime_type)}",
        mime_type=mime_type,
        width=width,
        height=height,
        byte_size=len(image_bytes),
        storage_path=storage_path,
        sha256=_sha256_bytes(image_bytes),
        is_original=True,
    )
    db.add(asset)
    await db.commit()
    return UploadImageResponse(
        asset_id=asset.id,
        account_id=asset.account_id,
        filename=asset.filename,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        byte_size=asset.byte_size,
        is_original=True,
    )


async def get_asset_or_404(db: AsyncSession, account_id: str, asset_id: str) -> ImageAsset:
    result = await db.execute(
        select(ImageAsset).where(ImageAsset.id == asset_id, ImageAsset.account_id == account_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise ValueError("Image asset not found.")
    return asset


def build_asset_metadata_response(asset: ImageAsset) -> ImageAssetMetadataResponse:
    return ImageAssetMetadataResponse(
        asset_id=asset.id,
        account_id=asset.account_id,
        original_asset_id=asset.original_asset_id,
        parent_asset_id=asset.parent_asset_id,
        filename=asset.filename,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        byte_size=asset.byte_size,
        is_original=asset.is_original,
        created_at=asset.created_at.isoformat() if asset.created_at else None,
    )


def read_asset_bytes(asset: ImageAsset) -> bytes:
    path = Path(asset.storage_path)
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("Image asset data is no longer available. Please upload the source again.") from exc
    except OSError as exc:
        raise ValueError("Image asset data could not be read. Please try again.") from exc


async def create_derived_asset(
    *,
    db: AsyncSession,
    account_id: str,
    original_asset_id: str,
    parent_asset_id: str,
    output_format: str,
    image_bytes: bytes,
    width: int,
    height: int,
) -> ImageAsset:
    mime_type = _guess_mime_from_format(output_format)
    asset_id = str(uuid4())
    storage_path = _write_bytes(account_id, asset_id, mime_type, image_bytes)
    asset = ImageAsset(
        id=asset_id,
        account_id=account_id,
        original_asset_id=original_asset_id,
        parent_asset_id=parent_asset_id,
        filename=f"{asset_id}{_extension_for_mime(mime_type)}",
        mime_type=mime_type,
        width=width,
        height=height,
        byte_size=len(image_bytes),
        storage_path=storage_path,
        sha256=_sha256_bytes(image_bytes),
        is_original=False,
    )
    db.add(asset)
    await db.flush()
    return asset
