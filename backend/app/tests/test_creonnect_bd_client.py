"""Tests for the creonnect-bd API client."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qs, urlparse

from backend.app.account_sources.creonnect_bd_client import CreonnectBDClient


def test_client_includes_access_token_from_env(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        status = 200

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001, ANN002, ANN003
            return None

        def read(self) -> bytes:
            return json.dumps({"success": True, "data": {"connections": []}}).encode("utf-8")

    def _fake_urlopen(request, timeout: float):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        return _FakeResponse()

    monkeypatch.setenv("CREONNECT_BD_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setattr("backend.app.account_sources.creonnect_bd_client.urlopen", _fake_urlopen)

    client = CreonnectBDClient(base_url="https://bd.example")
    connections = asyncio.run(client.list_connections())

    assert connections == []
    assert captured["timeout"] == 30.0

    parsed = urlparse(captured["url"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/api/social/instagram/connections"
    assert query["includeDisconnected"] == ["false"]
    assert "access_token" not in query
    assert captured["authorization"] == "Bearer test-access-token"
