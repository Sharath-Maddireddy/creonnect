"""Internal client for creonnect-bd social APIs."""

from __future__ import annotations

import json
import hashlib
import hmac
import os
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT_SECONDS = 30.0


class CreonnectBDClient:
    """Small typed client for the creonnect-bd social API surface."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        actor_user_id: str | None = None,
        actor_user_email: str | None = None,
    ) -> None:
        resolved_base_url = (base_url or os.getenv("CREONNECT_BD_BASE_URL") or "").strip().rstrip("/")
        if not resolved_base_url:
            raise ValueError("CREONNECT_BD_BASE_URL must be set to use source='creonnect_bd'.")
        self.base_url = resolved_base_url
        self.timeout_seconds = float(timeout_seconds or os.getenv("CREONNECT_BD_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
        self.access_token = (os.getenv("CREONNECT_BD_ACCESS_TOKEN") or "").strip() or None
        self.actor_user_id = (actor_user_id or "").strip() or None
        self.actor_user_email = (actor_user_email or "").strip() or None
        self.internal_service_id = (os.getenv("CREONNECT_INTERNAL_SERVICE_ID") or "creonnect-python").strip()
        self.internal_hmac_secret = (os.getenv("CREONNECT_INTERNAL_HMAC_SECRET") or "").strip() or None

    def _build_hmac_headers(
        self,
        *,
        method: str,
        path_with_query: str,
        payload_bytes: bytes | None,
    ) -> dict[str, str]:
        if not (self.internal_hmac_secret and self.actor_user_id and self.actor_user_email):
            return {}
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        body_hash = hashlib.sha256(payload_bytes or b"").hexdigest()
        canonical = "\n".join(
            [
                method.upper(),
                path_with_query,
                timestamp,
                nonce,
                self.actor_user_id,
                self.actor_user_email,
                body_hash,
            ]
        )
        signature = hmac.new(
            self.internal_hmac_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-Service-Id": self.internal_service_id,
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-User-Id": self.actor_user_id,
            "X-User-Email": self.actor_user_email,
            "X-Signature": signature,
        }

    async def _request_json(
        self,
        path: str,
        *,
        method: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_params = {key: value for key, value in (params or {}).items() if value is not None}
        query = urlencode(sorted(request_params.items(), key=lambda item: item[0]))
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        path_with_query = f"{path}?{query}" if query else path
        headers: dict[str, str] = {}
        payload_bytes: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload_bytes = json.dumps(body).encode("utf-8")
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        else:
            headers.update(
                self._build_hmac_headers(
                    method=method,
                    path_with_query=path_with_query,
                    payload_bytes=payload_bytes,
                )
            )
        request = Request(url, headers=headers, data=payload_bytes, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                status_code = int(getattr(response, "status", 200))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
            except ValueError:
                payload = {"message": body}
            message = payload.get("message") if isinstance(payload, dict) else None
            raise ValueError(
                f"creonnect-bd request failed for {path}: HTTP {exc.code} {message or ''}".strip()
            ) from exc
        except URLError as exc:
            raise ValueError(f"creonnect-bd request failed for {path}: {exc.reason}") from exc
        except ValueError as exc:
            raise ValueError(f"creonnect-bd returned non-JSON response for {path}") from exc

        if status_code != 200:
            message = None
            if isinstance(payload, dict):
                message = payload.get("message") or payload.get("error")
            raise ValueError(f"creonnect-bd request failed for {path}: HTTP {status_code} {message or ''}".strip())

        if not isinstance(payload, dict):
            raise ValueError(f"creonnect-bd returned invalid response envelope for {path}")
        if payload.get("success") is False:
            raise ValueError(f"creonnect-bd request reported failure for {path}: {payload.get('message') or 'unknown error'}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"creonnect-bd response data for {path} must be an object")
        return data

    async def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request_json(path, method="GET", params=params)

    async def list_connections(self, *, platform: str = "instagram", include_disconnected: bool = False) -> list[dict[str, Any]]:
        data = await self._get_json(
            f"/api/social/{platform}/connections",
            params={"includeDisconnected": str(include_disconnected).lower()},
        )
        connections = data.get("connections")
        if not isinstance(connections, list):
            raise ValueError("creonnect-bd connections response must include a connections list")
        return [item for item in connections if isinstance(item, dict)]

    async def list_posts_page(
        self,
        *,
        platform: str = "instagram",
        connection_id: str,
        page: int,
        limit: int,
    ) -> dict[str, Any]:
        return await self._get_json(
            f"/api/social/{platform}/posts",
            params={
                "connectionId": connection_id,
                "page": page,
                "limit": limit,
            },
        )

    async def get_creator_profile(self) -> dict[str, Any]:
        """Fetch creator profile for the authenticated/impersonated user context."""
        return await self._get_json("/api/creator/profile")

    async def update_connection_ai_analysis(
        self,
        *,
        platform: str = "instagram",
        connection_id: str,
        ai_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request_json(
            f"/api/social/{platform}/connections/{connection_id}/ai-analysis",
            method="PATCH",
            body={"ai_analysis": ai_analysis},
        )

    async def update_posts_ai_analysis(
        self,
        *,
        platform: str = "instagram",
        connection_id: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._request_json(
            f"/api/social/{platform}/posts/ai-analysis",
            method="PATCH",
            body={"connection_id": connection_id, "items": items},
        )
