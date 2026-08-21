"""Safe remote-image ingestion for the Creator Image Editor."""

from __future__ import annotations

import io
from urllib.parse import urlparse

import httpx
from PIL import Image

from backend.app.infra.outbound_media import resolve_public_http_url


MAX_SOURCE_BYTES = 25 * 1024 * 1024


def _validate_public_url(value: str) -> str:
    try:
        return resolve_public_http_url(value, field_name="source_url").public_url
    except ValueError as exc:
        if "resolve only to public addresses" in str(exc):
            raise ValueError("source_url must not resolve to a private or local address.") from exc
        raise


async def fetch_remote_image(source_url: str) -> tuple[bytes, str, str]:
    """Fetch and validate a public image without allowing SSRF or large bodies."""
    target = resolve_public_http_url(source_url, field_name="source_url")
    source_url = target.public_url
    timeout = httpx.Timeout(15.0, connect=5.0)
    headers = {**target.request_headers, "Accept": "image/*"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        async with client.stream(
            "GET",
            target.connect_url,
            headers=headers,
            extensions=target.request_extensions,
        ) as response:
            if response.status_code != 200:
                raise ValueError("source_url did not return an image.")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if not content_type.startswith("image/"):
                raise ValueError("source_url did not return an image content type.")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise ValueError("Remote image exceeds the 25 MB limit.")
                chunks.append(chunk)
    payload = b"".join(chunks)
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
    except Exception as exc:
        raise ValueError("source_url did not contain a readable image.") from exc
    filename = (urlparse(source_url).path.rsplit("/", 1)[-1] or "remote-image")[:160]
    return payload, content_type, filename
