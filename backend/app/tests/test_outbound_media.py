from __future__ import annotations

import asyncio
import io
import socket

import pytest
from PIL import Image

from backend.app.infra import outbound_media
from backend.app.services import creator_image_source_service


PUBLIC_IPV4 = "93.184.216.34"


def _address(ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    endpoint = (ip, 0, 0, 0) if family == socket.AF_INET6 else (ip, 0)
    return family, socket.SOCK_STREAM, 6, "", endpoint


def test_resolver_rejects_credentials_and_mixed_dns(monkeypatch) -> None:
    with pytest.raises(ValueError, match="valid public HTTP or HTTPS"):
        outbound_media.resolve_public_http_url(
            "https://user:secret@example.com/image.jpg", field_name="media_url"
        )

    monkeypatch.setattr(
        outbound_media.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [_address(PUBLIC_IPV4), _address("10.0.0.5")],
    )
    with pytest.raises(ValueError, match="only to public addresses"):
        outbound_media.resolve_public_http_url(
            "https://example.com/image.jpg", field_name="media_url"
        )


def test_resolver_pins_public_ip_but_preserves_host_and_sni(monkeypatch) -> None:
    calls = 0

    def rebinding_dns(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return [_address(PUBLIC_IPV4 if calls == 1 else "169.254.169.254")]

    monkeypatch.setattr(outbound_media.socket, "getaddrinfo", rebinding_dns)
    target = outbound_media.resolve_public_http_url(
        "https://cdn.example:8443/path/image.jpg?size=large#ignored",
        field_name="media_url",
    )

    assert calls == 1
    assert target.public_url == "https://cdn.example:8443/path/image.jpg?size=large"
    assert target.connect_url == f"https://{PUBLIC_IPV4}:8443/path/image.jpg?size=large"
    assert target.request_headers == {"Host": "cdn.example:8443"}
    assert target.request_extensions == {"sni_hostname": "cdn.example"}


def test_known_media_proxy_is_unwrapped_without_bypassing_later_validation() -> None:
    wrapped = (
        "https://media.fastdl.app/get?__sig=abc&"
        "uri=https%3A%2F%2Fscontent.example.com%2Fimage.jpg%3Fx%3D1&filename=image.jpg"
    )

    assert outbound_media.unwrap_supported_media_proxy_url(wrapped) == "https://scontent.example.com/image.jpg?x=1"
    assert outbound_media.unwrap_supported_media_proxy_url("https://other.example/get?uri=https%3A%2F%2Fcdn.example%2Fx.jpg") == "https://other.example/get?uri=https%3A%2F%2Fcdn.example%2Fx.jpg"


def test_known_media_proxy_requires_one_valid_inner_url() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        outbound_media.unwrap_supported_media_proxy_url("https://media.fastdl.app/get?filename=image.jpg")


class _AsyncImageResponse:
    status_code = 200
    headers = {"content-type": "image/png"}

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def aiter_bytes(self):
        yield self.payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _AsyncImageClient:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.request = None

    def stream(self, method, url, *, headers, extensions):
        self.request = (method, url, headers, extensions)
        return _AsyncImageResponse(self.payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


def test_creator_fetch_connects_to_pinned_ip(monkeypatch) -> None:
    image_buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(image_buffer, format="PNG")
    client = _AsyncImageClient(image_buffer.getvalue())
    monkeypatch.setattr(
        outbound_media.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [_address(PUBLIC_IPV4)],
    )

    def client_factory(*, timeout, follow_redirects, trust_env):
        assert follow_redirects is False
        assert trust_env is False
        return client

    monkeypatch.setattr(creator_image_source_service.httpx, "AsyncClient", client_factory)
    payload, content_type, filename = asyncio.run(
        creator_image_source_service.fetch_remote_image(
            "https://images.example/source/avatar.png"
        )
    )

    assert payload == image_buffer.getvalue()
    assert content_type == "image/png"
    assert filename == "avatar.png"
    assert client.request == (
        "GET",
        f"https://{PUBLIC_IPV4}/source/avatar.png",
        {"Host": "images.example", "Accept": "image/*"},
        {"sni_hostname": "images.example"},
    )
